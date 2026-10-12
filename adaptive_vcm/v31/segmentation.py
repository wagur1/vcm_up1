"""Video Semantic and Instance Segmentation preprocessing extensions for VCM.

Foundational literature:
1. Różek et al., "Luma-Guided Pre-Compression for Semantic Image Segmentation"
   (MDPI Electronics 2024):
   Preserves high-frequency luma (Y) boundary gradients where segmentation masks
   require pixel accuracy, while aggressively lowpassing chroma (Cb/Cr) and non-boundary regions.
2. Boundary-aware mask gradient weighting for segmentation task preservation under high compression.
"""
from __future__ import annotations

import cv2
import numpy as np


def segmentation_boundary_mask(segmentation_mask: np.ndarray, boundary_width: int = 5) -> np.ndarray:
    """Extract boundary transition zone from ground truth or pseudo segmentation masks.

    Boundary pixels require the highest fidelity for intersection-over-union (mIoU).
    """
    if segmentation_mask.ndim != 2:
        raise ValueError("segmentation_mask must be 2D integer class map")
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (boundary_width, boundary_width))
    dilated = cv2.dilate(segmentation_mask.astype(np.uint8), kernel)
    eroded = cv2.erode(segmentation_mask.astype(np.uint8), kernel)
    boundary = (dilated != eroded).astype(np.float32)
    return boundary


def luma_guided_segmentation_filter(frame: np.ndarray,
                                   boundary_mask: np.ndarray | None = None,
                                   chroma_blur_sigma: float = 3.5,
                                   background_blur_sigma: float = 2.5) -> np.ndarray:
    """Preprocess frame for machine segmentation using Luma-guided preservation (Różek et al., 2024).

    1. Transforms to YCrCb.
    2. Applies aggressive smoothing to chroma channels (Cr, Cb) since segmentation backbones
       are predominantly sensitive to luma boundary edges.
    3. Smooths non-boundary luma regions while preserving sharp transitions along boundaries.
    """
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be (H, W, 3) RGB")
    h, w = frame.shape[:2]

    # Convert RGB to YCrCb
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_RGB2YCrCb)
    y = ycrcb[:, :, 0].astype(np.float32)
    cr = ycrcb[:, :, 1].astype(np.float32)
    cb = ycrcb[:, :, 2].astype(np.float32)

    # Aggressive chroma smoothing
    cr_smooth = cv2.GaussianBlur(cr, (0, 0), sigmaX=chroma_blur_sigma, sigmaY=chroma_blur_sigma)
    cb_smooth = cv2.GaussianBlur(cb, (0, 0), sigmaX=chroma_blur_sigma, sigmaY=chroma_blur_sigma)

    # Luma handling
    if boundary_mask is not None:
        if boundary_mask.shape != (h, w):
            boundary_mask = cv2.resize(boundary_mask.astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
        y_blur = cv2.GaussianBlur(y, (0, 0), sigmaX=background_blur_sigma, sigmaY=background_blur_sigma)
        b_expanded = cv2.GaussianBlur(boundary_mask, (5, 5), 1.5)
        y_out = y * b_expanded + y_blur * (1.0 - b_expanded)
    else:
        # Edge-guided unsharp preservation on luma
        y_blur = cv2.GaussianBlur(y, (0, 0), sigmaX=background_blur_sigma, sigmaY=background_blur_sigma)
        grad_x = cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3)
        edge_weight = np.clip(np.sqrt(grad_x ** 2 + grad_y ** 2) / 64.0, 0.0, 1.0)
        y_out = y * edge_weight + y_blur * (1.0 - edge_weight)

    reconstructed = np.stack([
        np.clip(y_out, 0, 255).astype(np.uint8),
        np.clip(cr_smooth, 0, 255).astype(np.uint8),
        np.clip(cb_smooth, 0, 255).astype(np.uint8)
    ], axis=2)

    return cv2.cvtColor(reconstructed, cv2.COLOR_YCrCb2RGB)
