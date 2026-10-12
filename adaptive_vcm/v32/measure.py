"""V32 real-codec measurement engine integrating upgraded preprocessing actions."""
from __future__ import annotations

from dataclasses import asdict, replace
from fractions import Fraction
import copy
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np

from ..codec import locate_ffmpeg
from ..v31.measure import (
    CandidateEncodingError,
    _metadata,
    _ScopedModels,
    _provenance,
    prepare_support,
)
from ..v31.measure_models import (
    ObservationCache,
    build_models,
    json_value,
    model_hashes,
    predict,
)
from ..v31.measure_store import (
    atomic_json,
    condition_path,
    read_condition,
    sha,
    write_source_artifact,
)
from .actions import action_registry_v32, execute_actions_v32
from .codec import V32Codec, PacketV32
from .protocol import CODECS, QPS, SCHEMA, canonical_hash, validate_config_v32
from .transport import pack_recipe_v32


def write_packet_v32(store: Path, packet: PacketV32) -> dict:
    """Store packet elementary stream and RecipeV32 wire format."""
    streams_dir = store / "streams"
    streams_dir.mkdir(parents=True, exist_ok=True)
    stream_name = f"{packet.packet_hash}.es"
    recipe_name = f"{packet.packet_hash}.v32recipe"
    stream_path = streams_dir / stream_name
    recipe_path = streams_dir / recipe_name

    packed = pack_recipe_v32(packet.recipe)
    if not stream_path.exists():
        stream_path.write_bytes(packet.encoded)
    if not recipe_path.exists():
        recipe_path.write_bytes(packed)

    return {
        "recipe": asdict(packet.recipe),
        "stream_path": str(stream_path),
        "recipe_path": str(recipe_path),
        "stream_sha256": sha(packet.encoded),
        "recipe_sha256": sha(packed),
        "packet_hash": packet.packet_hash,
        "decoded_sha256": sha(packet.decoded.tobytes()),
        "elementary_bytes": packet.elementary_bytes,
        "total_bytes": packet.total_bytes,
        "seconds": packet.seconds,
    }


def measure_source_v32(sample: dict, registry: tuple, codec_name: str, qp: int,
                       models, cfg: dict | None, store: Path | str) -> dict:
    """Measure one source across the V32 action registry with real codecs."""
    effective = validate_config_v32(cfg)
    task = effective.get("task")
    if task != sample.get("task") or tuple(registry) != action_registry_v32(task, effective["v32_arm"]):
        raise ValueError("measurement task/V32 action registry mismatch")
    if codec_name not in CODECS or type(qp) is not int or qp not in QPS:
        raise ValueError("unsupported measurement codec/QP")

    rgb = sample["rgb"]
    if sample.get("source_sha256") != sha(rgb.tobytes()):
        raise ValueError("source pixel hash identity mismatch")

    hashes = model_hashes(models, task, effective)
    provenance = models.provenance if isinstance(models, _ScopedModels) else _provenance()
    source_meta = _metadata(sample)

    identity = {
        "schema": SCHEMA,
        "source_id": sample["id"],
        "source": source_meta,
        "ground_truth_hash": canonical_hash(sample.get("ground_truth", {})),
        "split": sample.get("split", "fit"),
        "task": task,
        "codec": codec_name,
        "qp": qp,
        "config_hash": canonical_hash(effective),
        "registry": [asdict(a) for a in registry],
        "model_hashes": hashes,
        "code_manifest_hash": provenance["manifest_hash"],
    }

    store = Path(store)
    path = condition_path(store, sample["id"], codec_name, qp)
    if path.exists():
        return read_condition(path, identity, store)

    cache = models.observations if isinstance(models, _ScopedModels) else ObservationCache()
    source_predictions = predict(models, hashes, rgb, task, sample, cache)

    controls, support = prepare_support(
        rgb, task, source_predictions["teachers"],
        models[task]["teachers"], cache, effective["od_score_threshold"]
    )
    support_hash = canonical_hash({
        key: sha(np.asarray(support[key]).tobytes())
        for key in ("protection", "motion", "cuts")
    })
    source_artifact = write_source_artifact(store, rgb, controls, support)
    conditioned = {**sample, "codec": codec_name, "control_protection": controls}

    render_key = (source_artifact["sha256"], canonical_hash(source_meta), qp, identity["config_hash"])
    rendered = models.rendered if isinstance(models, _ScopedModels) else {}
    if render_key not in rendered:
        templates = execute_actions_v32(conditioned, tuple(registry), qp, support)
        for template in templates:
            if template["rgb"] is not None:
                template["rgb"].setflags(write=False)
        rendered[render_key] = templates

    executions = []
    for template in rendered[render_key]:
        execution = dict(template)
        if execution["available"]:
            execution["rgb"] = execution["rgb"].copy()
            execution["recipe_v32"] = replace(execution["recipe_v32"], codec=codec_name)
        executions.append(execution)

    actions, packets = [], {}
    for descriptor, execution in zip(registry, executions):
        indices = list(execution["sample_indices"]) if execution["sample_indices"] is not None else []
        observation = {
            "descriptor": asdict(descriptor),
            "available": execution["available"],
            "reason": execution["reason"],
            "sample_indices": indices,
            "coded_shape": json_value(execution["coded_shape"]),
            "rgb_sha256": execution["rgb_sha256"],
            "recipe": None,
            "stream_path": None,
            "recipe_path": None,
            "stream_sha256": None,
            "recipe_sha256": None,
            "packet_hash": None,
            "decoded_sha256": None,
            "elementary_bytes": None,
            "total_bytes": None,
            "seconds": None,
            "predictions": None,
            "rate": None,
            "error": None,
        }
        if execution["available"]:
            recipe = execution["recipe_v32"]
            packet_key = (execution["rgb_sha256"], pack_recipe_v32(recipe), codec_name, qp, identity["config_hash"])
            if packet_key not in packets:
                codec = V32Codec(codec_name, qp, effective["preset"], recipe.fps)
                try:
                    packets[packet_key] = codec.roundtrip(execution["rgb"], recipe)
                except CandidateEncodingError as error:
                    if descriptor.name == "identity":
                        raise
                    packets[packet_key] = str(error)[:1000]
            packet = packets[packet_key]
            if isinstance(packet, str):
                observation.update(available=False, reason="candidate_encoding_failure", error=packet)
            else:
                observation.update(write_packet_v32(store, packet))
                observation["predictions"] = predict(models, hashes, packet.decoded, task, sample, cache)
                denominator = float(sample["duration"]) if task == "ar" else float(np.prod(sample["original_shape"]))
                observation["rate"] = packet.total_bytes * 8 / denominator
        actions.append(observation)

    row = {
        "schema": SCHEMA,
        "task": task,
        "source_id": sample["id"],
        "split": sample.get("split", "fit"),
        "codec": codec_name,
        "qp": qp,
        "config_hash": identity["config_hash"],
        "model_hashes": hashes,
        "code_manifest_hash": provenance["manifest_hash"],
        "source": source_meta,
        "source_predictions": source_predictions,
        "anchor_predictions": copy.deepcopy(actions[0]["predictions"]),
        "actions": actions,
        "support_sha256": support_hash,
        "control_protection_sha256": sha(controls.tobytes()),
        "source_artifact": source_artifact,
        "ground_truth": json_value(sample.get("ground_truth", {})),
        "counts": {
            "registered": len(actions),
            "available": sum(a["available"] for a in actions),
            "unavailable": sum(not a["available"] for a in actions),
            "unavailable_reasons": {
                reason: sum(a["reason"] == reason for a in actions)
                for reason in sorted({a["reason"] for a in actions if not a["available"]})
            },
        },
    }
    atomic_json(path, {"identity": identity, "row_hash": canonical_hash(row), "row": row})
    return row
