"""V32 action registry and execution engine unifying baseline and upgraded actions."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import numpy as np

from ..v31.actions import (
    Action,
    action_registry,
    _execute_action,
    _geometry,
    _shape,
    map_detections,
)
from ..v31.upgrades import (
    upgraded_action_registry,
    execute_upgraded_action,
)
from .transport import RecipeV32
from .protocol import V32_ARMS


def action_registry_v32(task: str, arm: str = "v32_upgraded") -> tuple[Action, ...]:
    """Return frozen action tuple for V32 arms, seamlessly combining baseline and research upgrades."""
    if arm not in V32_ARMS:
        raise ValueError(f"unsupported V32 arm: {arm}")
    base_actions = list(action_registry(task, "b"))
    upgraded = list(upgraded_action_registry(task))

    if arm == "v32_baseline":
        return tuple(base_actions)
    elif arm == "v32_upgraded":
        return tuple(base_actions + upgraded)
    elif arm == "v32_ablation_dynamic":
        subset = [a for a in upgraded if a.kind == "dyn_drop2"]
        return tuple(base_actions + subset)
    elif arm == "v32_ablation_sensitivity":
        subset = [a for a in upgraded if a.kind == "sensitivity"]
        return tuple(base_actions + subset)
    elif arm == "v32_ablation_quant":
        subset = [a for a in upgraded if a.kind == "quant_adaptive"]
        return tuple(base_actions + subset)
    elif arm == "v32_ablation_edge":
        subset = [a for a in upgraded if a.kind == "edge_guided"]
        return tuple(base_actions + subset)
    return tuple(base_actions + upgraded)


def execute_action_v32(source: dict, action: Action, qp: int, support: dict, banks: dict | None = None) -> dict:
    """Execute a single V32 action, routing to upgraded engine or baseline renderer as appropriate."""
    if banks is None:
        banks = {}

    upgraded_kinds = {"dyn_drop2", "sensitivity", "quant_adaptive", "edge_guided"}
    if action.kind in upgraded_kinds:
        result = execute_upgraded_action(source, action, qp, support)
    else:
        result = _execute_action(source, action, qp, support, banks)

    # Attach RecipeV32 if available
    if result.get("recipe") is not None:
        r = result["recipe"]
        indices = result.get("sample_indices")
        sample_indices = tuple(indices) if indices is not None else ()
        result["recipe_v32"] = RecipeV32(
            r.task, r.codec, r.width, r.height, r.coded_frames, r.analyzer_frames,
            r.duration_num, r.duration_den, r.repeat_factor, sample_indices
        )
    return result


def execute_actions_v32(source: dict, registry: tuple[Action, ...], qp: int, support: dict) -> list[dict]:
    """Execute full V32 registry with caching banks scoped to this source."""
    if not isinstance(registry, tuple) or not registry or len(set(registry)) != len(registry):
        raise ValueError("expected nonempty unique frozen action tuple")
    banks = {}
    return [execute_action_v32(source, action, qp, support, banks) for action in registry]
