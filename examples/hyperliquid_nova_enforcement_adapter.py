"""Private proving-ground adapter that treats Nova decision_status as binding.

This adapter is intentionally small. It submits a decision candidate to Nova,
reads the full governed response, and converts that response into a
machine-readable consumer contract without adding execution, retries, or local
heuristics.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


DEFAULT_API_URL = os.getenv("NOVA_API_URL", "https://nova-api-ipz6.onrender.com")
DEFAULT_API_KEY = os.getenv("NOVA_API_KEY", "")

PERMIT_STATUSES = {"ALLOW", "PERMIT"}
REDUCED_PERMISSION_STATUSES = {"CONSTRAIN", "REDUCE"}
BLOCKED_STATUSES = {
    "DELAY",
    "DENY",
    "HALT",
    "VETO",
    "RETRY_DELAYED",
    "RETRY_BLOCKED",
    "PRESSURE_ESCALATED",
}


def fetch_nova_response(
    *,
    intent: str,
    asset: str,
    size: float,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_url = (api_url or DEFAULT_API_URL).rstrip("/")
    resolved_key = api_key if api_key is not None else DEFAULT_API_KEY
    if not resolved_key:
        raise ValueError("Missing API key. Set NOVA_API_KEY or pass api_key.")

    endpoint = f"{resolved_url}/v1/context"
    headers = {"Authorization": f"Bearer {resolved_key}"}
    params = {"intent": intent, "asset": asset, "size": size}

    with httpx.Client(timeout=20.0) as client:
        response = client.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def fetch_nova_proof(
    *,
    decision_id: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_url = (api_url or DEFAULT_API_URL).rstrip("/")
    resolved_key = api_key if api_key is not None else DEFAULT_API_KEY
    if not resolved_key:
        raise ValueError("Missing API key. Set NOVA_API_KEY or pass api_key.")

    endpoint = f"{resolved_url}/v1/proof/{decision_id}"
    headers = {"Authorization": f"Bearer {resolved_key}"}

    with httpx.Client(timeout=20.0) as client:
        response = client.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()


def _effective_constraints(nova_response: Dict[str, Any]) -> Dict[str, Any]:
    proof = nova_response.get("proof_surface") or {}
    impact = nova_response.get("impact_on_outcomes") or {}
    # Proof-layer fields carry authority. impact_on_outcomes remains
    # supporting detail for effective size handling.
    return {
        "decision_id": nova_response.get("decision_id"),
        "requested_size": (nova_response.get("decision_context") or {}).get("requested_size"),
        "effective_size": impact.get("adjusted_size"),
        "system_state": nova_response.get("system_state"),
        "constraint_effect": proof.get("constraint_effect"),
        "intervention_type": proof.get("intervention_type"),
        "failure_class": proof.get("failure_class"),
        "cooldown_state": nova_response.get("cooldown_state"),
        "retry_cooldown_expiry": nova_response.get("retry_cooldown_expiry"),
        "post_halt_quarantine_expiry": nova_response.get("post_halt_quarantine_expiry"),
        "queue_priority": nova_response.get("queue_priority"),
        "queue_position": nova_response.get("queue_position"),
        "batch_review_required": nova_response.get("batch_review_required"),
    }


def enforce_nova_response(nova_response: Dict[str, Any]) -> Dict[str, Any]:
    decision_status = str(nova_response.get("decision_status") or "").strip().upper()
    effective_constraints = _effective_constraints(nova_response)

    if decision_status in PERMIT_STATUSES:
        return {
            "allowed_to_proceed": True,
            "authoritative_decision_status": decision_status,
            "effective_constraints": effective_constraints,
            "nova_response": nova_response,
        }

    if decision_status in REDUCED_PERMISSION_STATUSES:
        return {
            "allowed_to_proceed": True,
            "authoritative_decision_status": decision_status,
            "effective_constraints": effective_constraints,
            "nova_response": nova_response,
        }

    if decision_status in BLOCKED_STATUSES or not decision_status:
        return {
            "allowed_to_proceed": False,
            "authoritative_decision_status": decision_status or "UNAVAILABLE",
            "effective_constraints": effective_constraints,
            "nova_response": nova_response,
        }

    # Unknown decision states default to blocked so the consumer cannot
    # invent an execution path that Nova did not authorize.
    return {
        "allowed_to_proceed": False,
        "authoritative_decision_status": decision_status,
        "effective_constraints": effective_constraints,
        "nova_response": nova_response,
    }


def evaluate_hyperliquid_decision_candidate(
    *,
    intent: str,
    asset: str,
    size: float,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    nova_response = fetch_nova_response(
        intent=intent,
        asset=asset,
        size=size,
        api_url=api_url,
        api_key=api_key,
    )
    decision_id = nova_response.get("decision_id")
    if decision_id:
        nova_response["proof_surface"] = fetch_nova_proof(
            decision_id=decision_id,
            api_url=api_url,
            api_key=api_key,
        )
    return enforce_nova_response(nova_response)


if __name__ == "__main__":
    result = evaluate_hyperliquid_decision_candidate(intent="trade", asset="ETH", size=10000)
    print(result)
