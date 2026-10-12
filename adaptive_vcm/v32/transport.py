"""Transport layer for V32: supports dynamic temporal decimation indexing on wire."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import struct

import numpy as np

from ..v31.protocol import CODECS
from ..v31.transport import _TASKS
from ..v31.upgrades import restore_dynamic_temporal_samples

_WIRE_V32 = struct.Struct(">4sBBBBHHHHQIHH")
RECIPE_V32_BYTES = _WIRE_V32.size  # Exactly 32 bytes


@dataclass(frozen=True)
class RecipeV32:
    task: str
    codec: str
    width: int
    height: int
    coded_frames: int
    analyzer_frames: int
    duration_num: int
    duration_den: int
    repeat_factor: int
    sample_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.task not in _TASKS or self.codec not in CODECS:
            raise ValueError("unknown transport task/codec")
        for field, bits in (("width", 16), ("height", 16), ("coded_frames", 16),
                            ("analyzer_frames", 16), ("duration_num", 64), ("duration_den", 32)):
            value = getattr(self, field)
            if type(value) is not int or not 0 < value < 2**bits:
                raise ValueError(f"invalid transport {field}")
        if type(self.repeat_factor) is not int or self.repeat_factor not in (1, 2):
            raise ValueError("transport repeat factor must be 1 or 2")
        if self.coded_frames * self.repeat_factor != self.analyzer_frames:
            raise ValueError("transport coded/analyzer count mismatch")
        if math.gcd(self.duration_num, self.duration_den) != 1:
            raise ValueError("transport duration must be a reduced positive rational")
        if self.sample_indices:
            if len(self.sample_indices) != self.coded_frames:
                raise ValueError(f"sample_indices count ({len(self.sample_indices)}) must match coded_frames ({self.coded_frames})")
            if any(type(idx) is not int or idx < 0 or idx >= self.analyzer_frames for idx in self.sample_indices):
                raise ValueError("sample indices must be integers within [0, analyzer_frames - 1]")

    @property
    def duration(self) -> Fraction:
        return Fraction(self.duration_num, self.duration_den)

    @property
    def fps(self) -> Fraction:
        return self.coded_frames / self.duration


def pack_recipe_v32(recipe: RecipeV32) -> bytes:
    if not isinstance(recipe, RecipeV32):
        raise ValueError("expected transport RecipeV32")
    # Bitmask encoding: support up to 16 analyzer frames in standard 16-bit field
    bitmask = 0
    if recipe.sample_indices and recipe.analyzer_frames <= 16:
        for idx in recipe.sample_indices:
            bitmask |= (1 << idx)
    return _WIRE_V32.pack(
        b"VC32", 1, _TASKS.index(recipe.task), CODECS.index(recipe.codec),
        recipe.repeat_factor, recipe.width, recipe.height, recipe.coded_frames,
        recipe.analyzer_frames, recipe.duration_num, recipe.duration_den,
        bitmask, 0
    )


def unpack_recipe_v32(data: bytes) -> RecipeV32:
    if type(data) is not bytes or len(data) != RECIPE_V32_BYTES:
        raise ValueError(f"transport header must be exactly {RECIPE_V32_BYTES} bytes")
    magic, version, task, codec, repeat, width, height, coded, analyzer, num, den, bitmask, reserved = _WIRE_V32.unpack(data)
    if magic != b"VC32" or version != 1 or reserved != 0:
        raise ValueError("unsupported transport magic/version/reserved field")
    if task >= len(_TASKS) or codec >= len(CODECS):
        raise ValueError("unknown transport task/codec code")

    sample_indices: tuple[int, ...] = ()
    if bitmask > 0 and analyzer <= 16:
        sample_indices = tuple(i for i in range(analyzer) if (bitmask & (1 << i)))

    return RecipeV32(
        _TASKS[task], CODECS[codec], width, height, coded, analyzer,
        num, den, repeat, sample_indices
    )


def restore_samples_v32(decoded: np.ndarray, recipe: RecipeV32) -> np.ndarray:
    """Restore decoded coded samples into analyzer positions.

    If non-uniform sample_indices are recorded, uses nearest-temporal-neighbor mapping
    to faithfully restore physical cadence. Otherwise falls back to uniform repeat.
    """
    pack_recipe_v32(recipe)
    shape = (recipe.coded_frames, recipe.height, recipe.width, 3)
    if not isinstance(decoded, np.ndarray) or decoded.dtype != np.uint8 or decoded.shape != shape:
        raise ValueError(f"decoded samples must be uint8 RGB {shape}")

    if recipe.sample_indices and len(recipe.sample_indices) == recipe.coded_frames:
        return restore_dynamic_temporal_samples(decoded, recipe.sample_indices, target_frames=recipe.analyzer_frames)
    return np.repeat(decoded, recipe.repeat_factor, axis=0)
