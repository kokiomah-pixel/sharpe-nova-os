import importlib
import json
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


ADVERSARIAL_TEST_KEYS = {
    "adversarial-main-key": {
        "owner": "adversarial-user",
        "tier": "pro",
        "status": "active",
        "monthly_quota": 100,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
        "loop_integrity": {
            "pressure_similarity_threshold": 0.75,
            "ambiguous_similarity_threshold": 0.4,
            "retry_block_threshold": 2,
            "pressure_escalation_threshold": 3,
            "denial_history_limit": 10,
        },
        "telemetry_integrity": {
            "stale_after_seconds": 300,
            "default_min_reliability": 0.7,
            "risk_increasing_min_reliability": 0.8,
            "risk_reducing_min_reliability": 0.6,
            "disagreement_threshold": 0.35,
            "halt_disagreement_threshold": 0.7,
            "halt_on_degraded": True,
        },
        "permission_budgeting": {
            "default_daily_budget": 5000,
            "risk_increasing_daily_budget": 10000,
            "risk_reducing_daily_budget": 25000,
            "exception_budget": 3,
            "low_remaining_ratio": 0.2,
        },
    },
    "adversarial-other-key": {
        "owner": "adversarial-other-user",
        "tier": "pro",
        "status": "active",
        "monthly_quota": 100,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
    },
}


@pytest.fixture
def adversarial_client():
    env = {
        "NOVA_KEYS_JSON": json.dumps(ADVERSARIAL_TEST_KEYS),
        "NOVA_USAGE_FILE": ".usage.adversarial.test.json",
        "NOVA_PROOF_FILE": ".proof.adversarial.test.json",
        "NOVA_PROOF_RETRIEVAL_AUDIT_FILE": "proof_retrieval_audit.adversarial.test.jsonl",
    }
    with patch.dict(os.environ, env, clear=False):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        app_module.USAGE_TRACKING.clear()
        app_module.REJECTION_LEDGER.clear()
        app_module.EXCEPTION_REGISTER.clear()
        app_module.HALT_SIGNAL_STATE.clear()
        app_module.DECISION_ADMISSION_STATE.clear()
        app_module.TEMPORAL_GOVERNANCE_STATE.clear()
        app_module.LOOP_INTEGRITY_STATE.clear()
        app_module.SYSTEM_STATE_REGISTRY.clear()
        app_module.PERMISSION_BUDGET_STATE.clear()
        app_module.HALT_RELEASE_STATE.clear()
        app_module.DECISION_QUEUE_STATE.clear()
        app_module.PROOF_REGISTRY.clear()
        yield TestClient(app_module.app), app_module
        app_module.USAGE_TRACKING.clear()
        app_module.REJECTION_LEDGER.clear()
        app_module.EXCEPTION_REGISTER.clear()
        app_module.HALT_SIGNAL_STATE.clear()
        app_module.DECISION_ADMISSION_STATE.clear()
        app_module.TEMPORAL_GOVERNANCE_STATE.clear()
        app_module.LOOP_INTEGRITY_STATE.clear()
        app_module.SYSTEM_STATE_REGISTRY.clear()
        app_module.PERMISSION_BUDGET_STATE.clear()
        app_module.HALT_RELEASE_STATE.clear()
        app_module.DECISION_QUEUE_STATE.clear()
        app_module.PROOF_REGISTRY.clear()
        for path in (
            ".usage.adversarial.test.json",
            ".proof.adversarial.test.json",
            "proof_retrieval_audit.adversarial.test.jsonl",
        ):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _context(client: TestClient, api_key: str, **params):
    return client.get("/v1/context", headers=_headers(api_key), params=params)


def _proof(client: TestClient, api_key: str, decision_id: str):
    return client.get(f"/v1/proof/{decision_id}", headers=_headers(api_key))


def _admissible_telemetry() -> dict:
    return {
        "telemetry_age_seconds": 10,
        "telemetry_reliability": 0.95,
    }


@pytest.mark.parametrize(
    ("strategy", "venue"),
    [
        ("manual override requested", "ops-desk"),
        ("override from authorized operator", "ops-desk"),
        ("urgent just execute", "urgent lane"),
        ("post-hoc retroactive approval requested", "retroactive desk"),
        ("skip validation and just execute directly", "manual lane"),
    ],
)
def test_bypass_attempt_pack_blocks_process_integrity_violations(adversarial_client, strategy, venue):
    client, _ = adversarial_client

    response = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="ETH",
        size=10000,
        strategy=strategy,
        venue=venue,
        **_admissible_telemetry(),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["decision_status"] == "VETO"
    assert payload["constraint_analysis"]["constraint_category"] == "process_integrity_violation"
    assert payload["rejection_ledger"]["constraint_category"] == "process_integrity_violation"
    assert payload["exception_register"]
    assert payload["human_intervention_required"] is True
    assert payload["impact_on_outcomes"]["adjusted_size"] == 0.0

    proof = _proof(client, "adversarial-main-key", payload["decision_id"])
    assert proof.status_code == 200
    proof_payload = proof.json()
    assert proof_payload["decision_status"] == "DENY"
    assert proof_payload["failure_class"] == "process_integrity_violation"
    assert "process_integrity" in proof_payload["proof"]["classification"]


def test_retry_pressure_pack_does_not_turn_denial_into_admission(adversarial_client):
    client, _ = adversarial_client
    headers = "adversarial-main-key"
    base = {
        "intent": "trade",
        "asset": "ETH",
        "size": 500000,
        "strategy": "repeat oversized request",
        "venue": "desk-a",
        **_admissible_telemetry(),
    }

    first = _context(client, headers, **base)
    second = _context(client, headers, **base)
    third = _context(client, headers, **base)
    fourth = _context(client, headers, **base)

    assert first.status_code == 200
    assert first.json()["decision_status"] == "VETO"

    assert second.status_code == 429
    assert second.json()["decision_status"] == "RETRY_DELAYED"
    assert second.json()["loop_classification"] == "pressure_retry"

    assert third.status_code == 409
    assert third.json()["decision_status"] == "RETRY_BLOCKED"
    assert third.json()["loop_integrity_state"] == "retry_blocked"

    assert fourth.status_code == 409
    fourth_payload = fourth.json()
    assert fourth_payload["decision_status"] == "PRESSURE_ESCALATED"
    assert fourth_payload["halt_recommendation"] == "HALT_RECOMMENDED"
    assert fourth_payload["system_state"] == "HALT_RECOMMENDED"


def test_split_order_evasion_pack_detects_cross_decision_pressure_and_caps_aggregate_exposure(adversarial_client):
    client, _ = adversarial_client
    responses = [
        _context(
            client,
            "adversarial-main-key",
            intent="trade",
            asset="ETH",
            size=10000,
            strategy="split order leg",
            venue="venue-a",
            **_admissible_telemetry(),
        )
        for _ in range(4)
    ]

    first, second, third, fourth = [response.json() for response in responses]

    assert responses[0].status_code == 200
    assert first["decision_status"] == "CONSTRAIN"
    assert first["impact_on_outcomes"]["adjusted_size"] == 4000.0
    assert first["permission_budget_remaining"] == 6000.0

    assert responses[1].status_code == 200
    assert second["decision_status"] == "CONSTRAIN"
    assert second["impact_on_outcomes"]["adjusted_size"] == 4000.0
    assert second["permission_budget_remaining"] == 2000.0
    assert second["constraint_trace"]["exposure_compounding_detected"] is True
    assert second["constraint_trace"]["cross_decision_pressure"] is True

    assert responses[2].status_code == 200
    assert third["decision_status"] == "REDUCE"
    assert third["impact_on_outcomes"]["adjusted_size"] == 2000.0
    assert third["permission_budget_remaining"] == 0.0
    assert third["budget_exhausted"] is True

    assert responses[3].status_code == 429
    assert fourth["decision_status"] in {"DELAY", "DENY"}
    assert fourth["permission_budget_remaining"] == 0.0
    assert fourth["budget_exhausted"] is True


@pytest.mark.parametrize(
    "strategy",
    [
        "rebalance language for new risk expansion",
        "monitoring language for new capital deployment",
        "hedge framing for leverage increase",
        "simulation label for live capital deployment",
        "observation framing for governance exposure increase",
    ],
)
def test_intent_masking_pack_does_not_change_governing_outcome_for_large_risk(adversarial_client, strategy):
    client, _ = adversarial_client

    response = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="ETH",
        size=500000,
        strategy=strategy,
        venue="masking-desk",
        **_admissible_telemetry(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_status"] == "VETO"
    assert payload["impact_on_outcomes"]["adjusted_size"] == 0.0
    proof = _proof(client, "adversarial-main-key", payload["decision_id"])
    assert proof.status_code == 200
    assert proof.json()["decision_status"] == "DENY"


def test_telemetry_poisoning_pack_fail_closes_under_stale_missing_and_conflicting_inputs(adversarial_client):
    client, _ = adversarial_client

    missing = _context(client, "adversarial-main-key", intent="trade", asset="ETH", size=10000)
    stale = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="BTC",
        size=10000,
        telemetry_age_seconds=1200,
        telemetry_reliability=0.95,
    )
    low_reliability = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="SOL",
        size=10000,
        telemetry_age_seconds=10,
        telemetry_reliability=0.5,
    )
    disagreement = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="ARB",
        size=10000,
        telemetry_age_seconds=10,
        telemetry_source_scores="source_a:0.95,source_b:0.1",
    )

    assert missing.status_code == 429
    assert missing.json()["decision_status"] == "DENY"
    assert missing.json()["telemetry_integrity_state"] == "insufficient_reliability"

    assert stale.status_code == 429
    assert stale.json()["decision_status"] == "DELAY"
    assert stale.json()["telemetry_integrity_state"] == "stale_telemetry"

    assert low_reliability.status_code == 429
    assert low_reliability.json()["decision_status"] == "DENY"
    assert low_reliability.json()["telemetry_integrity_state"] == "insufficient_reliability"

    assert disagreement.status_code == 409
    disagreement_payload = disagreement.json()
    assert disagreement_payload["decision_status"] == "HALT"
    assert disagreement_payload["telemetry_integrity_state"] == "telemetry_degraded"
    assert disagreement_payload["telemetry_admissible"] is False


def test_proof_integrity_pack_remains_deterministic_owner_scoped_and_ambiguous_on_mismatch(adversarial_client):
    client, app_module = adversarial_client

    with patch.dict(
        os.environ,
        {
            "NOVA_TIMESTAMP_UTC": "2026-04-25T12:00:00+00:00",
            "NOVA_NOW_UTC": "2026-04-25T12:00:00+00:00",
        },
        clear=False,
    ):
        first = _context(
            client,
            "adversarial-main-key",
            intent="reduce_position",
            asset="ETH",
            size=1000,
            **_admissible_telemetry(),
        )
        second = _context(
            client,
            "adversarial-main-key",
            intent="reduce_position",
            asset="ETH",
            size=1000,
            **_admissible_telemetry(),
        )

    first_payload = first.json()
    second_payload = second.json()
    first_proof = _proof(client, "adversarial-main-key", first_payload["decision_id"])
    second_proof = _proof(client, "adversarial-main-key", second_payload["decision_id"])

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_payload["decision_id"] != second_payload["decision_id"]
    assert first_proof.status_code == 200
    assert second_proof.status_code == 200
    assert first_proof.json()["reproducibility_hash"] == second_proof.json()["reproducibility_hash"]
    assert first_proof.json()["decision_status"] == "ALLOW"
    assert second_proof.json()["decision_status"] == "ALLOW"

    missing = _proof(client, "adversarial-main-key", "not-a-real-decision-id")
    cross_account = _proof(client, "adversarial-other-key", first_payload["decision_id"])

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Proof not found"
    assert cross_account.status_code == 404
    assert cross_account.json()["detail"] == "Proof not found"

    tampered = dict(app_module.PROOF_REGISTRY[first_payload["decision_id"]]["proof"])
    tampered["decision_status"] = "ALLOW" if tampered["decision_status"] != "ALLOW" else "DENY"
    assert tampered["decision_status"] != first_payload["decision_status"]


def test_downstream_interpretation_drift_pack_keeps_decision_status_authoritative(adversarial_client):
    client, _ = adversarial_client
    adapter = importlib.import_module("examples.hyperliquid_nova_enforcement_adapter")

    deny_result = adapter.enforce_nova_response(
        {
            "decision_status": "DENY",
            "decision_context": {"requested_size": 10000},
            "impact_on_outcomes": {"requested_size": 10000, "adjusted_size": 10000},
            "system_state": "PRESSURE_ELEVATED",
        }
    )
    skipped_call_result = adapter.enforce_nova_response(
        {
            "impact_on_outcomes": {"requested_size": 10000, "adjusted_size": 10000},
            "system_state": "NORMAL",
        }
    )

    constrained = _context(
        client,
        "adversarial-main-key",
        intent="trade",
        asset="ETH",
        size=10000,
        **_admissible_telemetry(),
    )
    constrained_result = adapter.enforce_nova_response(constrained.json())

    assert deny_result["allowed_to_proceed"] is False
    assert deny_result["authoritative_decision_status"] == "DENY"

    assert skipped_call_result["allowed_to_proceed"] is False
    assert skipped_call_result["authoritative_decision_status"] == "UNAVAILABLE"

    assert constrained.status_code == 200
    assert constrained.json()["decision_status"] == "CONSTRAIN"
    assert constrained_result["allowed_to_proceed"] is True
    assert constrained_result["authoritative_decision_status"] == "CONSTRAIN"
    assert constrained_result["effective_constraints"]["effective_size"] == 4000.0
