from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


SchemaVersion = Literal["1.0"]
PersistenceState = Literal["ephemeral", "retained"]
ValidationStatus = Literal["observed", "validated"]


class ReflexRegistryEntry(BaseModel):
    registry_id: str
    origin: str
    failure_class: str
    activation_condition: str
    behavioral_effect: str
    persistence_state: PersistenceState
    validation_status: ValidationStatus
    decision_effect: Optional[Literal["ALLOW", "CONSTRAIN", "VETO"]] = None
    adjustment_factor: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    public_reason: str


class ReflexProof(BaseModel):
    schema_version: SchemaVersion = "1.0"
    intervention_class: str
    failure_class: str
    decision_before_reflex: str
    decision_after_reflex: str
    decision_altered: bool
    triggered_registry_id: Optional[str] = None
    why_intervention_happened: str


class ReflexMemoryState(BaseModel):
    schema_version: SchemaVersion = "1.0"
    enabled: bool = True
    mode: str = "retained_discipline"
    persistence_state: PersistenceState
    validation_status: ValidationStatus
    registered_entries: list[ReflexRegistryEntry]
    active_registry_id: Optional[str] = None
    triggered: bool = False
    influence_applied: bool = False
    decision_before_reflex: str
    decision_after_reflex: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    proof: Optional[ReflexProof] = None
