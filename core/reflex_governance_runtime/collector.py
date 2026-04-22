from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


REQUIRED_FIELDS = {
    "decision_id",
    "normalized_signature",
    "decision_status",
    "intervention_type",
    "classification",
    "reproducibility_hash",
    "reflex_ids",
    "account_id",
}


def _normalized_signature_from_request(normalized_request: Dict[str, Any]) -> str:
    canonical = {
        "asset": normalized_request.get("asset"),
        "intent": normalized_request.get("intent"),
        "requested_action": normalized_request.get("requested_action"),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def _reflex_ids_from_payload(payload: Dict[str, Any], reflex_log: Optional[Dict[str, Any]]) -> List[str]:
    reflex_memory = payload.get("reflex_memory", {})
    if not isinstance(reflex_memory, dict):
        reflex_memory = {}

    ids: List[str] = []
    active_registry_id = reflex_memory.get("active_registry_id")
    if active_registry_id:
        ids.append(str(active_registry_id))

    if reflex_memory.get("triggered"):
        proof = reflex_memory.get("proof", {})
        if isinstance(proof, dict) and proof.get("triggered_registry_id"):
            ids.append(str(proof["triggered_registry_id"]))

    if isinstance(reflex_log, dict):
        raw_ids = reflex_log.get("reflex_ids", [])
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        ids.extend(str(item) for item in raw_ids if str(item).strip())

    return sorted(set(ids))


def collect_governance_record(
    *,
    context_payload: Dict[str, Any],
    proof_record: Dict[str, Any],
    reflex_log: Optional[Dict[str, Any]] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    proof_payload = proof_record.get("proof", {})
    if not isinstance(proof_payload, dict):
        proof_payload = {}

    proof_body = proof_payload.get("proof", {})
    if not isinstance(proof_body, dict):
        proof_body = {}

    validation = proof_payload.get("validation", {})
    if not isinstance(validation, dict):
        validation = {}

    normalized_request = proof_record.get("normalized_request", {})
    if not isinstance(normalized_request, dict):
        normalized_request = {}

    classification = proof_body.get("classification", [])
    if not isinstance(classification, list):
        classification = [classification]

    record = {
        "decision_id": str(proof_record.get("decision_id") or context_payload.get("decision_id") or ""),
        "observed_at": str(context_payload.get("timestamp_utc") or ""),
        "normalized_signature": _normalized_signature_from_request(normalized_request),
        "decision_status": str(proof_payload.get("decision_status") or ""),
        "context_decision_status": str(context_payload.get("decision_status") or ""),
        "intervention_type": str(proof_payload.get("intervention_type") or "none"),
        "classification": sorted(str(item) for item in classification if str(item).strip()),
        "reproducibility_hash": str(
            proof_record.get("reproducibility_hash")
            or validation.get("reproducibility_hash")
            or proof_payload.get("reproducibility_hash")
            or ""
        ),
        "reflex_ids": _reflex_ids_from_payload(context_payload, reflex_log),
        "registered_reflex_ids": sorted(
            str(entry.get("registry_id"))
            for entry in (context_payload.get("reflex_memory", {}).get("registered_entries", []) or [])
            if isinstance(entry, dict) and str(entry.get("registry_id") or "").strip()
        ),
        "account_id": str(account_id or proof_record.get("owner") or ""),
        "proof_decision_status": str(proof_payload.get("decision_status") or ""),
        "memory_influence_present": bool(
            proof_payload.get("memory_influence", {}).get("influence_present")
            if isinstance(proof_payload.get("memory_influence"), dict)
            else context_payload.get("memory_influence_invoked")
        ),
        "outcome_influenced": str(proof_payload.get("decision_status") or "").upper() != "ALLOW",
    }

    missing = REQUIRED_FIELDS.difference(record.keys())
    if missing:
        raise ValueError(f"collector record missing fields: {sorted(missing)}")

    return record
