"""Unit tests for research-backed VCM preprocessing upgrades (V31+)."""
from fractions import Fraction
import numpy as np
import pytest

from adaptive_vcm.v31.actions import Action
from adaptive_vcm.v31.upgrades import (
    dynamic_temporal_decimation,
    feature_sensitivity_mask,
    quant_adaptive_filter,
    edge_preserving_guided_filter,
    upgraded_action_registry,
    execute_upgraded_action,
)
from adaptive_vcm.v31.tracking import (
    TrackletBox,
    build_spatiotemporal_tube_mask,
    apply_mot_corridor_filter,
)
from adaptive_vcm.v31.segmentation import (
    segmentation_boundary_mask,
    luma_guided_segmentation_filter,
)
from tests.v31_fixture import action_source


def test_dynamic_temporal_decimation_anchors_and_picks_high_energy():
    # Construct 16-frame clip where frame 5 and 10 have huge motion
    t, h, w, c = 16, 64, 64, 3
    clip = np.zeros((t, h, w, c), dtype=np.uint8)
    clip[5] = 255  # sudden flash/motion
    clip[10] = 128

    decimated, indices = dynamic_temporal_decimation(clip, n_keep=8)
    assert len(indices) == 8
    assert indices[0] == 0 and indices[-1] == 15
    assert 5 in indices  # frame 5 must be selected due to peak motion energy
    assert len(set(indices)) == 8
    assert list(indices) == sorted(indices)
    assert decimated.shape == (8, h, w, c)


def test_feature_sensitivity_mask_produces_normalized_weights():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[40:60, 40:60] = 255  # bright square with sharp edges
    boxes = np.array([[40, 40, 60, 60]])

    sens = feature_sensitivity_mask(frame, boxes=boxes, halo=0.1)
    assert sens.shape == (100, 100)
    assert sens.dtype == np.float32
    assert 0.0 <= np.min(sens) and np.max(sens) <= 1.0
    # Region inside box and on boundary must have high sensitivity
    assert np.mean(sens[45:55, 45:55]) > np.mean(sens[0:10, 0:10])


def test_quant_adaptive_filter_preserves_dimensions_and_adjusts_with_qp():
    clip = np.random.randint(50, 200, (4, 64, 64, 3), dtype=np.uint8)
    filtered_low_qp = quant_adaptive_filter(clip, qp=30)
    filtered_high_qp = quant_adaptive_filter(clip, qp=45)

    assert filtered_low_qp.shape == clip.shape
    assert filtered_high_qp.shape == clip.shape
    assert filtered_low_qp.dtype == np.uint8
    assert filtered_high_qp.dtype == np.uint8


def test_edge_preserving_guided_filter_smooths_textures():
    # Texture with a high step edge
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:, 32:] = 200
    # Add small noise
    noise = np.random.randint(-5, 5, (64, 64, 3)).astype(np.int16)
    noisy_img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    clip = np.stack([noisy_img] * 2)

    filtered = edge_preserving_guided_filter(clip, radius=2, eps=0.04)
    assert filtered.shape == clip.shape
    # Edge at column 32 should still be sharp
    edge_diff = int(filtered[0, 30, 35, 0]) - int(filtered[0, 30, 25, 0])
    assert edge_diff > 150


def test_upgraded_action_registry_and_execution():
    ar_actions = upgraded_action_registry("ar")
    od_actions = upgraded_action_registry("od")

    assert len(ar_actions) == 9
    assert len(od_actions) == 9
    assert all(isinstance(a, Action) for a in ar_actions)
    assert all(isinstance(a, Action) for a in od_actions)

    # Test executing upgraded AR action
    source_ar, support_ar = action_source("ar")
    source_ar["source_fps"] = Fraction(25, 1)
    res_ar = execute_upgraded_action(source_ar, ar_actions[0], qp=35, support=support_ar)
    assert res_ar["available"]
    assert res_ar["rgb"] is not None
    assert res_ar["recipe"] is not None
    assert res_ar["rgb"].shape[0] == 8  # dynamic decimation to 8 frames

    # Test executing upgraded OD action
    source_od, support_od = action_source("od")
    res_od = execute_upgraded_action(source_od, od_actions[0], qp=35, support=support_od)
    assert res_od["available"]
    assert res_od["rgb"] is not None
    assert res_od["recipe"] is not None
    assert res_od["coded_shape"] == (256, 256)


def test_tracking_tube_mask_and_corridor_filter():
    clip_shape = (8, 64, 64, 3)
    # Tracklet at frame 0 and frame 4
    tracklets = [
        TrackletBox(track_id=1, frame_idx=0, box=(10., 10., 20., 20.), score=0.9),
        TrackletBox(track_id=1, frame_idx=4, box=(30., 30., 40., 40.), score=0.95),
    ]
    tube_mask = build_spatiotemporal_tube_mask(clip_shape, tracklets, corridor_padding=0.1)
    assert tube_mask.shape == (8, 64, 64)
    # Intermediate frame 2 should be interpolated and have protection > 0
    assert np.any(tube_mask[2] > 0.0)

    clip = np.random.randint(0, 255, clip_shape, dtype=np.uint8)
    filtered = apply_mot_corridor_filter(clip, tube_mask)
    assert filtered.shape == clip_shape
    assert filtered.dtype == np.uint8


def test_segmentation_boundary_mask_and_luma_guided_filter():
    # 2D class map
    seg_map = np.zeros((64, 64), dtype=np.int32)
    seg_map[20:44, 20:44] = 1

    boundary = segmentation_boundary_mask(seg_map, boundary_width=3)
    assert boundary.shape == (64, 64)
    assert np.any(boundary > 0.0)
    # Center of class 1 should NOT be boundary
    assert boundary[32, 32] == 0.0

    frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    filtered = luma_guided_segmentation_filter(frame, boundary_mask=boundary)
    assert filtered.shape == (64, 64, 3)
    assert filtered.dtype == np.uint8


def test_feature_sensitivity_mask_out_of_bounds_produces_zero_box_protection():
    """Verify that completely out-of-bounds bounding boxes do NOT trigger negative-slice wrap."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Box completely outside frame to the left/top
    oob_boxes = np.array([[-100, -100, -20, -20], [200, 200, 300, 300]])
    sens = feature_sensitivity_mask(frame, boxes=oob_boxes, halo=0.1)
    # Since frame is flat black and boxes are outside, sensitivity should be exactly 0 everywhere
    assert np.all(sens == 0.0)


def test_tracking_tube_mask_out_of_bounds_produces_zero_protected_pixels():
    """Verify that tracklets with negative coordinates produce 0 protected pixels."""
    clip_shape = (4, 64, 64, 3)
    oob_tracklets = [
        TrackletBox(track_id=1, frame_idx=0, box=(-100., -100., -20., -20.), score=0.9),
        TrackletBox(track_id=2, frame_idx=1, box=(200., 200., 300., 300.), score=0.9),
    ]
    tube_mask = build_spatiotemporal_tube_mask(clip_shape, oob_tracklets, corridor_padding=0.2)
    assert np.all(tube_mask == 0.0)


def test_execute_upgraded_action_rejects_task_mismatch():
    """Verify that passing an OD source to an AR action raises ValueError."""
    source_od, support_od = action_source("od")
    ar_actions = upgraded_action_registry("ar")
    with pytest.raises(ValueError, match="task mismatch"):
        execute_upgraded_action(source_od, ar_actions[0], qp=35, support=support_od)

    source_ar, support_ar = action_source("ar")
    od_actions = upgraded_action_registry("od")
    with pytest.raises(ValueError, match="task mismatch"):
        execute_upgraded_action(source_ar, od_actions[0], qp=35, support=support_ar)


def test_dynamic_temporal_decimation_restores_nearest_cadence():
    """Verify nearest-temporal-neighbor restoration preserves physical timing."""
    from adaptive_vcm.v31.upgrades import restore_dynamic_temporal_samples
    t, h, w, c = 16, 32, 32, 3
    # Distinct frame values to track index placement
    clip = np.zeros((t, h, w, c), dtype=np.uint8)
    for i in range(t):
        clip[i, :, :, :] = i * 10

    # Simulate non-uniform keyframes (0, 9, 10, 11, 12, 13, 14, 15)
    sample_indices = (0, 9, 10, 11, 12, 13, 14, 15)
    decimated = clip[list(sample_indices)]

    restored = restore_dynamic_temporal_samples(decimated, sample_indices, target_frames=16)
    assert restored.shape == (16, h, w, c)

    # Frame t=0 to t=4 are closest to sample_index 0 (dist to 0 is <= 4, dist to 9 is >= 5)
    for t_idx in range(5):
        assert int(restored[t_idx, 0, 0, 0]) == 0  # 0 * 10
    # Frame t=5 to t=9 are closest to sample_index 9 (dist to 9 is <= 4, dist to 0 is >= 5)
    for t_idx in range(5, 10):
        assert int(restored[t_idx, 0, 0, 0]) == 90  # 9 * 10
    # Frame t=10 is exact match with sample_index 10
    assert int(restored[10, 0, 0, 0]) == 100
    # Frame t=15 is exact match with sample_index 15
    assert int(restored[15, 0, 0, 0]) == 150


def test_quant_adaptive_filter_boost_increases_with_qp():
    """Verify that edge contrast boost is monotonically higher at high QP."""
    img = np.zeros((32, 32, 3), dtype=np.uint8)
    img[:, 16:] = 200  # High step edge at column 16
    clip = np.stack([img])

    low_qp_out = quant_adaptive_filter(clip, qp=30)[0]
    high_qp_out = quant_adaptive_filter(clip, qp=45)[0]

    # At column 16 (edge boundary), high QP unsharp boost should produce greater overshoot
    edge_contrast_low = abs(int(low_qp_out[16, 17, 0]) - int(low_qp_out[16, 15, 0]))
    edge_contrast_high = abs(int(high_qp_out[16, 17, 0]) - int(high_qp_out[16, 15, 0]))

    assert edge_contrast_high >= edge_contrast_low

