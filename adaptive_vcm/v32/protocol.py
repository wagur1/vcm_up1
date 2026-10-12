"""V32 protocol specification, configuration and action arm definitions."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from ..v31.protocol import (
    QPS,
    CODECS,
    canonical_hash,
    SOURCE_COUNTS,
)
from . import SCHEMA

V32_ARMS = (
    "v32_baseline",
    "v32_upgraded",
    "v32_ablation_dynamic",
    "v32_ablation_sensitivity",
    "v32_ablation_quant",
    "v32_ablation_edge",
)

_LOCKED_CONFIG_V32 = {
    "schema": 32,
    "seed": 303201,
    "qps": list(QPS),
    "codecs": list(CODECS),
    "preset": "medium",
    "frames": 16,
    "temporal_stride": 2,
    "ar_size": 128,
    "od_size": 320,
    "v32_arm": "v32_upgraded",
    "ar_teachers": ["r3d_18", "mc3_18"],
    "ar_evaluators": ["r2plus1d_18", "r3d_18"],
    "od_teacher": "mobilenet",
    "od_evaluator": "resnet50",
    "ar_kl_slack": 0.1,
    "ar_confidence": 0.6,
    "od_distance_slack": 0.03,
    "od_score_threshold": 0.25,
    "min_savings": 0.01,
    "bootstrap_draws": 2000,
    "target_bd_rate_pct": -10,
    "epochs": 8,
    "width": 64,
    "proposal_k": 3,
    "optimizer": {
        "name": "Adam",
        "lr": 0.001,
        "batch_size": 32,
        "early_stopping": False,
        "scheduler": None,
    },
}


def validate_config_v32(cfg: dict | None) -> dict:
    """Validate and return effective V32 configuration."""
    base = copy.deepcopy(_LOCKED_CONFIG_V32)
    if cfg is None:
        return base
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a dictionary")
    effective = {**base, **cfg}
    if effective.get("v32_arm") not in V32_ARMS:
        raise ValueError(f"unsupported V32 arm: {effective.get('v32_arm')}")
    if tuple(effective.get("qps", ())) != QPS:
        raise ValueError("V32 requires standard 4-point QPS (30, 35, 40, 45)")
    return effective
