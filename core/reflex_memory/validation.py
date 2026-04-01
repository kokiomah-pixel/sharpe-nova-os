from __future__ import annotations

from .schema import ReflexMemoryState


def validate_reflex_memory_state(state: ReflexMemoryState) -> ReflexMemoryState:
    if state.proof and not state.triggered:
        raise ValueError("Reflex proof cannot exist without a triggered state.")
    if state.influence_applied and not state.triggered:
        raise ValueError("Reflex influence cannot be applied when no registry entry triggered.")
    if state.decision_after_reflex not in {"ALLOW", "CONSTRAIN", "VETO"}:
        raise ValueError("Unexpected decision_after_reflex value.")
    return state
