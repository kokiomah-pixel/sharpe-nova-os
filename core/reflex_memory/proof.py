from __future__ import annotations

from typing import Optional

from .schema import ReflexProof, ReflexRegistryEntry


def build_reflex_proof(
    *,
    entry: Optional[ReflexRegistryEntry],
    decision_before_reflex: str,
    decision_after_reflex: str,
) -> Optional[ReflexProof]:
    if entry is None:
        return None

    intervention_class = "decision_override" if entry.decision_effect == "VETO" else "allocation_tightening"

    return ReflexProof(
        intervention_class=intervention_class,
        failure_class=entry.failure_class,
        decision_before_reflex=decision_before_reflex,
        decision_after_reflex=decision_after_reflex,
        decision_altered=decision_before_reflex != decision_after_reflex,
        triggered_registry_id=entry.registry_id,
        why_intervention_happened=entry.public_reason,
    )
