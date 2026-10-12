"""V32 codec adapter supporting RecipeV32 and dynamic temporal cadence restoration."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import numpy as np

from ..codec import StandardCodec
from .protocol import SCHEMA
from .transport import RecipeV32, RECIPE_V32_BYTES, pack_recipe_v32, restore_samples_v32

_DECODER_CONTRACT_V32 = {
    "schema": SCHEMA,
    "pixel_format": "rgb24",
    "threads": 2,
    "xerror": True,
    "err_detect": "explode",
    "vsync": "0",
}


@dataclass(frozen=True)
class PacketV32:
    """Encoded stream and restored analyzer samples via RecipeV32."""
    encoded: bytes
    recipe: RecipeV32
    decoded: np.ndarray
    seconds: float

    def __post_init__(self) -> None:
        pack_recipe_v32(self.recipe)
        if type(self.encoded) is not bytes or not self.encoded:
            raise ValueError("packet elementary stream must be nonempty bytes")
        shape = (self.recipe.analyzer_frames, self.recipe.height, self.recipe.width, 3)
        if not isinstance(self.decoded, np.ndarray) or self.decoded.dtype != np.uint8 or self.decoded.shape != shape:
            raise ValueError(f"packet decoded analyzer samples must be uint8 RGB {shape}")
        if not isinstance(self.seconds, (int, float)) or isinstance(self.seconds, bool) or not math.isfinite(self.seconds) or self.seconds < 0:
            raise ValueError("packet seconds must be finite and nonnegative")
        samples = self.decoded.copy()
        samples.setflags(write=False)
        object.__setattr__(self, "decoded", samples)

    @property
    def elementary_bytes(self) -> int:
        return len(self.encoded)

    @property
    def total_bytes(self) -> int:
        return self.elementary_bytes + RECIPE_V32_BYTES

    @property
    def packet_hash(self) -> str:
        return hashlib.sha256(pack_recipe_v32(self.recipe) + self.encoded).hexdigest()


class V32Codec:
    def __init__(self, codec: str, qp: int, preset: str, fps: Fraction,
                 gop_settings: dict | None = None):
        if not isinstance(fps, Fraction) or fps <= 0:
            raise ValueError("V32 requires a known positive rational Fraction FPS")
        self._codec = StandardCodec(codec, qp, preset=preset, fps=fps,
                                    gop_settings=gop_settings)

    def roundtrip(self, rgb: np.ndarray, recipe: RecipeV32) -> PacketV32:
        pack_recipe_v32(recipe)
        if recipe.codec != self._codec.codec:
            raise ValueError("codec/recipe codec mismatch")
        if recipe.fps != self._codec.fps:
            raise ValueError("codec FPS/recipe duration mismatch")
        shape = (recipe.coded_frames, recipe.height, recipe.width, 3)
        if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.shape != shape:
            raise ValueError(f"coded input/recipe geometry or count mismatch: expected {shape}")
        result = self._codec.roundtrip(rgb)
        return PacketV32(result.data, recipe, restore_samples_v32(result.decoded, recipe), result.seconds)
