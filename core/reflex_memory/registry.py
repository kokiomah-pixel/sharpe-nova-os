from __future__ import annotations

from typing import Optional

from .schema import ReflexRegistryEntry


def build_registry(regime: str) -> list[ReflexRegistryEntry]:
    entries: list[ReflexRegistryEntry] = []

    if regime == "Stress":
        entries.append(
            ReflexRegistryEntry(
                registry_id="stress_new_risk_block",
                origin="historical_validation",
                failure_class="fragility_escalation",
                activation_condition="regime=Stress and risk-increasing intent",
                behavioral_effect="blocks new risk and forces zero-allocation output",
                persistence_state="retained",
                validation_status="validated",
                decision_effect="VETO",
                adjustment_factor=0.0,
                public_reason="Retained discipline blocks new risk when stress conditions are already escalated.",
            )
        )

    if regime == "Elevated Fragility":
        entries.append(
            ReflexRegistryEntry(
                registry_id="elevated_fragility_size_brake",
                origin="historical_validation",
                failure_class="liquidity_deterioration",
                activation_condition="regime=Elevated Fragility and risk-increasing intent with positive requested size",
                behavioral_effect="tightens allowed participation before execution",
                persistence_state="retained",
                validation_status="validated",
                decision_effect="CONSTRAIN",
                adjustment_factor=0.4,
                public_reason="Retained discipline trims exposure because elevated fragility historically worsens under unrestricted participation.",
            )
        )

    if regime == "Stable":
        entries.append(
            ReflexRegistryEntry(
                registry_id="stable_monitoring_reference",
                origin="historical_validation",
                failure_class="baseline_monitoring",
                activation_condition="regime=Stable",
                behavioral_effect="records stable operating discipline without intervention",
                persistence_state="retained",
                validation_status="observed",
                decision_effect=None,
                adjustment_factor=None,
                public_reason="Retained discipline is present, but no intervention is required under stable conditions.",
            )
        )

    return entries


def select_active_entry(
    *,
    registry: list[ReflexRegistryEntry],
    intent: Optional[str],
    size: Optional[float],
) -> Optional[ReflexRegistryEntry]:
    normalized_intent = (intent or "").strip().lower()
    requested_size = float(size) if size is not None else None
    is_risk_increasing = normalized_intent in {
        "trade",
        "deploy_liquidity",
        "open_position",
        "increase_position",
    }

    for entry in registry:
        if entry.registry_id == "stress_new_risk_block" and is_risk_increasing:
            return entry
        if (
            entry.registry_id == "elevated_fragility_size_brake"
            and is_risk_increasing
            and requested_size is not None
            and requested_size > 0
        ):
            return entry

    return None
