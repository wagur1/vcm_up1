"""Unit tests for V32 protocol, action routing, wire transport, and benchmarks."""
from fractions import Fraction
import numpy as np
import pytest

from adaptive_vcm.v32.protocol import V32_ARMS, validate_config_v32
from adaptive_vcm.v32.transport import (
    RecipeV32,
    pack_recipe_v32,
    unpack_recipe_v32,
    restore_samples_v32,
)
from adaptive_vcm.v32.actions import (
    action_registry_v32,
    execute_action_v32,
    execute_actions_v32,
)
from adaptive_vcm.v32.benchmark import (
    benchmark_mot_tube_protection,
    benchmark_segmentation_luma_filter,
    compute_ablation_bd_rate,
)
from adaptive_vcm.v31.tracking import TrackletBox
from tests.v31_fixture import action_source


def test_v32_arms_and_registry_expansion():
    # Baseline arm has same count as V31 arm "b"
    from adaptive_vcm.v31.actions import action_registry
    base_ar = action_registry("ar", "b")
    v32_base_ar = action_registry_v32("ar", "v32_baseline")
    assert len(base_ar) == len(v32_base_ar)

    # Upgraded arm expands registry with 9 new actions
    v32_upgraded_ar = action_registry_v32("ar", "v32_upgraded")
    assert len(v32_upgraded_ar) == len(base_ar) + 9

    # Ablation arms only include their specific additions
    ablation_dyn = action_registry_v32("ar", "v32_ablation_dynamic")
    assert len(ablation_dyn) == len(base_ar) + 3
    assert all(a.kind in ("control", "profile", "drop2", "temporal", "dyn_drop2") for a in ablation_dyn)


def test_v32_recipe_pack_unpack_roundtrip():
    # Recipe with non-uniform indices
    sample_indices = (0, 3, 5, 7, 9, 11, 13, 15)
    r = RecipeV32(
        task="ar", codec="h264", width=128, height=128,
        coded_frames=8, analyzer_frames=16, duration_num=16, duration_den=25,
        repeat_factor=2, sample_indices=sample_indices
    )
    packed = pack_recipe_v32(r)
    assert len(packed) == 32
    unpacked = unpack_recipe_v32(packed)

    assert unpacked.task == "ar"
    assert unpacked.codec == "h264"
    assert unpacked.width == 128
    assert unpacked.height == 128
    assert unpacked.coded_frames == 8
    assert unpacked.analyzer_frames == 16
    assert unpacked.sample_indices == sample_indices


def test_v32_execute_action_routes_correctly():
    source_ar, support_ar = action_source("ar")
    source_ar["source_fps"] = Fraction(25, 1)

    # 1. Standard action
    reg_base = action_registry_v32("ar", "v32_baseline")
    res_base = execute_action_v32(source_ar, reg_base[0], qp=35, support=support_ar)
    assert res_base["available"]
    assert res_base["recipe_v32"] is not None

    # 2. Upgraded dynamic decimation action
    reg_upgraded = action_registry_v32("ar", "v32_upgraded")
    dyn_action = [a for a in reg_upgraded if a.kind == "dyn_drop2"][0]
    res_dyn = execute_action_v32(source_ar, dyn_action, qp=35, support=support_ar)
    assert res_dyn["available"]
    assert res_dyn["recipe_v32"] is not None
    assert len(res_dyn["recipe_v32"].sample_indices) == 8

    # 3. Test restoration via restore_samples_v32
    decoded_dummy = np.zeros((8, 128, 128, 3), dtype=np.uint8)
    restored = restore_samples_v32(decoded_dummy, res_dyn["recipe_v32"])
    assert restored.shape == (16, 128, 128, 3)


def test_v32_benchmark_mot_and_segmentation_runs():
    # Synthetic 4-frame clip
    clip = np.random.randint(40, 220, (4, 64, 64, 3), dtype=np.uint8)
    tracklets = [
        TrackletBox(track_id=1, frame_idx=0, box=(10., 10., 30., 30.), score=0.9),
        TrackletBox(track_id=1, frame_idx=2, box=(20., 20., 40., 40.), score=0.9),
    ]
    mot_res = benchmark_mot_tube_protection(clip, tracklets, codec="h264", qp=35)
    assert "rate_saving_pct" in mot_res
    assert mot_res["raw_bytes"] > 0
    assert mot_res["pre_bytes"] > 0

    # Segmentation test
    frame = np.random.randint(40, 220, (64, 64, 3), dtype=np.uint8)
    seg_map = np.zeros((64, 64), dtype=np.int32)
    seg_map[20:40, 20:40] = 1
    seg_res = benchmark_segmentation_luma_filter(frame, seg_map, codec="h264", qp=35)
    assert "rate_saving_pct" in seg_res
    assert seg_res["raw_bytes"] > 0
    assert seg_res["pre_bytes"] > 0


def test_v32_compute_ablation_bd_rate_side_by_side():
    # Synthetic rate-distortion points
    raw_rates = [1000.0, 500.0, 250.0, 100.0]
    raw_metrics = [0.85, 0.75, 0.60, 0.40]
    pre_rates = [900.0, 450.0, 220.0, 90.0]
    pre_metrics = [0.85, 0.74, 0.59, 0.39]

    res = compute_ablation_bd_rate(raw_rates, raw_metrics, pre_rates, pre_metrics)
    assert "cubic_bd_rate" in res
    assert "pchip_bd_rate" in res
    assert isinstance(res["cubic_bd_rate"], float)
    assert isinstance(res["pchip_bd_rate"], float)
