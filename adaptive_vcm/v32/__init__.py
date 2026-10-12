"""V32 preprocessing engine: Research-backed upgrades with full protocol integration."""
from __future__ import annotations

SCHEMA = "adaptive-vcm-actions-v32"

from .actions import action_registry_v32, execute_action_v32, execute_actions_v32
from .protocol import V32_ARMS, QPS, CODECS
from .transport import RecipeV32, pack_recipe_v32, unpack_recipe_v32, restore_samples_v32
