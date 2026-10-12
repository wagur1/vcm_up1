"""Benchmark and ablation harness for VCM V32 research preprocessing modules."""
from __future__ import annotations

from fractions import Fraction
import numpy as np

from ..codec import StandardCodec
from ..metrics import bd_rate, pchip_bd
from ..v31.tracking import TrackletBox, build_spatiotemporal_tube_mask, apply_mot_corridor_filter
from ..v31.segmentation import segmentation_boundary_mask, luma_guided_segmentation_filter
from ..v31.upgrades import (
    dynamic_temporal_decimation,
    restore_dynamic_temporal_samples,
    feature_sensitivity_mask,
    quant_adaptive_filter,
    edge_preserving_guided_filter,
)


def benchmark_mot_tube_protection(
    clip: np.ndarray,
    tracklets: list[TrackletBox],
    codec: str = "h264",
    qp: int = 35,
    fps: Fraction = Fraction(25, 1),
) -> dict:
    """Benchmark MOT spatio-temporal tube protection against raw encoding.

    Returns bitrate savings and fidelity preservation metrics on tracked tubes.
    """
    if clip.ndim != 4:
        raise ValueError("clip must be (T, H, W, C)")
    t, h, w, c = clip.shape
    tube_mask = build_spatiotemporal_tube_mask(clip.shape, tracklets)

    encoder = StandardCodec(codec, qp=qp, fps=fps)

    # 1. Raw baseline
    raw_res = encoder.roundtrip(clip)
    raw_bytes = len(raw_res.data)

    # 2. Preprocessed with tube filter
    filtered = apply_mot_corridor_filter(clip, tube_mask, background_blur_sigma=3.0)
    pre_res = encoder.roundtrip(filtered)
    pre_bytes = len(pre_res.data)

    # Calculate bitrate saving
    rate_saving_pct = ((raw_bytes - pre_bytes) / raw_bytes) * 100.0

    # Calculate tube-region MSE
    tube_3d = np.repeat(tube_mask[..., np.newaxis], 3, axis=-1)
    tube_pixels = np.sum(tube_3d > 0.5)

    if tube_pixels > 0:
        raw_tube_mse = float(np.sum(((raw_res.decoded.astype(np.float32) - clip.astype(np.float32)) ** 2) * tube_3d) / tube_pixels)
        pre_tube_mse = float(np.sum(((pre_res.decoded.astype(np.float32) - clip.astype(np.float32)) ** 2) * tube_3d) / tube_pixels)
    else:
        raw_tube_mse, pre_tube_mse = 0.0, 0.0

    return {
        "codec": codec,
        "qp": qp,
        "raw_bytes": raw_bytes,
        "pre_bytes": pre_bytes,
        "rate_saving_pct": rate_saving_pct,
        "raw_tube_mse": raw_tube_mse,
        "pre_tube_mse": pre_tube_mse,
    }


def benchmark_segmentation_luma_filter(
    frame: np.ndarray,
    seg_map: np.ndarray,
    codec: str = "h264",
    qp: int = 35,
) -> dict:
    """Benchmark Luma-guided filtering for semantic segmentation against raw encoding."""
    if frame.ndim != 3:
        raise ValueError("frame must be (H, W, 3)")
    boundary = segmentation_boundary_mask(seg_map, boundary_width=5)
    filtered = luma_guided_segmentation_filter(frame, boundary_mask=boundary)

    clip_raw = np.stack([frame])
    clip_filtered = np.stack([filtered])

    encoder = StandardCodec(codec, qp=qp, fps=Fraction(25, 1))
    raw_res = encoder.roundtrip(clip_raw)
    pre_res = encoder.roundtrip(clip_filtered)

    raw_bytes = len(raw_res.data)
    pre_bytes = len(pre_res.data)
    rate_saving_pct = ((raw_bytes - pre_bytes) / raw_bytes) * 100.0

    # Check boundary reconstruction error
    boundary_3d = np.repeat(boundary[..., np.newaxis], 3, axis=-1)
    b_count = np.sum(boundary_3d > 0.5)
    if b_count > 0:
        raw_b_mse = float(np.sum(((raw_res.decoded[0].astype(np.float32) - frame.astype(np.float32)) ** 2) * boundary_3d) / b_count)
        pre_b_mse = float(np.sum(((pre_res.decoded[0].astype(np.float32) - frame.astype(np.float32)) ** 2) * boundary_3d) / b_count)
    else:
        raw_b_mse, pre_b_mse = 0.0, 0.0

    return {
        "codec": codec,
        "qp": qp,
        "raw_bytes": raw_bytes,
        "pre_bytes": pre_bytes,
        "rate_saving_pct": rate_saving_pct,
        "raw_boundary_mse": raw_b_mse,
        "pre_boundary_mse": pre_b_mse,
    }


def compute_ablation_bd_rate(
    raw_rates: list[float],
    raw_metrics: list[float],
    pre_rates: list[float],
    pre_metrics: list[float],
) -> dict[str, float]:
    """Compute both Cubic BD-rate and PCHIP BD-rate for rigorous side-by-side comparison."""
    cubic = bd_rate(raw_rates, raw_metrics, pre_rates, pre_metrics)
    pchip = pchip_bd(raw_rates, raw_metrics, pre_rates, pre_metrics)
    return {
        "cubic_bd_rate": float(cubic),
        "pchip_bd_rate": float(pchip),
    }
