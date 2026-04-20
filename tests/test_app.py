import importlib
import json
import os
from datetime import datetime, timezone
import pytest
import sys
from fastapi.testclient import TestClient
from unittest.mock import patch

TEST_KEYS = {
    "admin-key": {
        "owner": "internal",
        "tier": "admin",
        "status": "active",
        "monthly_quota": 100,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
            "/v1/usage/reset",
        ],
    },
    "pro-key": {
        "owner": "pro-user",
        "tier": "pro",
        "status": "active",
        "monthly_quota": 10,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
    },
    "free-low-quota-key": {
        "owner": "free-user",
        "tier": "free",
        "status": "active",
        "monthly_quota": 1,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
    },
    "inactive-key": {
        "owner": "inactive-user",
        "tier": "pro",
        "status": "inactive",
        "monthly_quota": 10,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
    },
    "suspended-key": {
        "owner": "suspended-user",
        "tier": "pro",
        "status": "suspended",
        "monthly_quota": 10,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
        ],
    },
    "pro-reset-key": {
        "owner": "pro-reset-user",
        "tier": "pro",
        "status": "active",
        "monthly_quota": 10,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/usage",
            "/v1/usage/reset",
        ],
    },
    "temporal-key": {
        "owner": "temporal-user",
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
        "temporal_governance": {
            "window_seconds": 60,
            "max_requests_per_window": 2,
            "deny_cooldown_seconds": 120,
            "halt_cooldown_seconds": 300,
            "retry_spacing_seconds": 30,
            "halt_threshold": 3,
        },
    },
    "temporal-halt-key": {
        "owner": "temporal-halt-user",
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
        "temporal_governance": {
            "window_seconds": 60,
            "max_requests_per_window": 0,
            "deny_cooldown_seconds": 0,
            "halt_cooldown_seconds": 300,
            "retry_spacing_seconds": 0,
            "halt_threshold": 2,
        },
    },
    "loop-key": {
        "owner": "loop-user",
        "tier": "pro",
        "status": "active",
        "monthly_quota": 100,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
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
    },
    "full-governance-key": {
        "owner": "full-governance-user",
        "tier": "enterprise",
        "status": "active",
        "monthly_quota": 1000,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/proof/{decision_id}",
            "/v1/key-info",
            "/v1/governance-profile",
            "/v1/usage",
        ],
        "temporal_governance": {
            "window_seconds": 60,
            "max_requests_per_window": 2,
            "deny_cooldown_seconds": 180,
            "halt_cooldown_seconds": 600,
            "retry_spacing_seconds": 45,
            "halt_threshold": 3,
        },
        "loop_integrity": {
            "pressure_similarity_threshold": 0.75,
            "ambiguous_similarity_threshold": 0.4,
            "retry_block_threshold": 2,
            "pressure_escalation_threshold": 3,
            "denial_history_limit": 10,
        },
        "telemetry_integrity": {
            "stale_after_seconds": 180,
            "default_min_reliability": 0.8,
            "risk_increasing_min_reliability": 0.9,
            "risk_reducing_min_reliability": 0.7,
            "disagreement_threshold": 0.3,
            "halt_disagreement_threshold": 0.65,
            "halt_on_degraded": True,
        },
        "system_state": {
            "profile": "full_governance",
        },
        "permission_budgeting": {
            "default_daily_budget": 50000,
            "risk_increasing_daily_budget": 25000,
            "risk_reducing_daily_budget": 100000,
            "exception_budget": 1,
            "low_remaining_ratio": 0.2,
            "delay_on_exhaustion": False,
            "halt_on_compounded_pressure": True,
        },
        "halt_release_governance": {
            "release_authority": "authorized_operator",
            "required_evidence": ["control_integrity_review", "fresh_telemetry_confirmation"],
            "post_release_cooldown_seconds": 300,
        },
        "human_intervention_taxonomy": {
            "profile": "bounded_auditable",
        },
        "decision_queue_governance": {
            "request_ttl_seconds": 300,
            "expire_on_regime_change": True,
            "expire_on_epoch_change": True,
        },
        "memory_governance": {
            "admissible_reflex_classes": [
                "fragility_escalation",
                "liquidity_deterioration",
                "baseline_monitoring",
            ],
            "memory_age_seconds": 0,
            "stale_after_seconds": 3600,
            "aging_after_ratio": 0.5,
            "confidence_weights": {
                "validated": 1.0,
                "observed": 0.5,
            },
        },
    },
}


@pytest.fixture
def client():
    """Create a test client with mocked NOVA_KEYS_JSON."""
    keys_json = json.dumps(TEST_KEYS)
    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": keys_json,
            "NOVA_USAGE_FILE": ".usage.test.json",
            "NOVA_PROOF_FILE": ".proof.test.json",
            "NOVA_PROOF_RETRIEVAL_AUDIT_FILE": "proof_retrieval_audit.test.jsonl",
        },
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        app = app_module.app
        USAGE_TRACKING = app_module.USAGE_TRACKING
        REJECTION_LEDGER = app_module.REJECTION_LEDGER
        EXCEPTION_REGISTER = app_module.EXCEPTION_REGISTER
        HALT_SIGNAL_STATE = app_module.HALT_SIGNAL_STATE
        DECISION_ADMISSION_STATE = app_module.DECISION_ADMISSION_STATE
        TEMPORAL_GOVERNANCE_STATE = app_module.TEMPORAL_GOVERNANCE_STATE
        LOOP_INTEGRITY_STATE = app_module.LOOP_INTEGRITY_STATE
        SYSTEM_STATE_REGISTRY = app_module.SYSTEM_STATE_REGISTRY
        PERMISSION_BUDGET_STATE = app_module.PERMISSION_BUDGET_STATE
        HALT_RELEASE_STATE = app_module.HALT_RELEASE_STATE
        PROOF_REGISTRY = app_module.PROOF_REGISTRY
        USAGE_TRACKING.clear()
        REJECTION_LEDGER.clear()
        EXCEPTION_REGISTER.clear()
        HALT_SIGNAL_STATE.clear()
        DECISION_ADMISSION_STATE.clear()
        TEMPORAL_GOVERNANCE_STATE.clear()
        LOOP_INTEGRITY_STATE.clear()
        SYSTEM_STATE_REGISTRY.clear()
        PERMISSION_BUDGET_STATE.clear()
        HALT_RELEASE_STATE.clear()
        PROOF_REGISTRY.clear()
        yield TestClient(app)
        USAGE_TRACKING.clear()
        REJECTION_LEDGER.clear()
        EXCEPTION_REGISTER.clear()
        HALT_SIGNAL_STATE.clear()
        DECISION_ADMISSION_STATE.clear()
        TEMPORAL_GOVERNANCE_STATE.clear()
        LOOP_INTEGRITY_STATE.clear()
        SYSTEM_STATE_REGISTRY.clear()
        PERMISSION_BUDGET_STATE.clear()
        HALT_RELEASE_STATE.clear()
        PROOF_REGISTRY.clear()
        try:
            os.remove(".usage.test.json")
        except FileNotFoundError:
            pass
        try:
            os.remove(".proof.test.json")
        except FileNotFoundError:
            pass
        try:
            os.remove("proof_retrieval_audit.test.jsonl")
        except FileNotFoundError:
            pass


# Test A: /health is open
def test_health_is_public(client):
    """Verify /health requires no auth and returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_context_includes_guardrail_action_policy(client):
    """Verify /v1/context always includes canonical guardrail.action_policy keys."""
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    assert response.status_code == 200

    payload = response.json()
    assert "guardrail" in payload
    assert "action_policy" in payload["guardrail"]

    action_policy = payload["guardrail"]["action_policy"]
    assert "allow_new_risk" in action_policy
    assert "allow_risk_reduction" in action_policy
    assert "allow_position_increase" in action_policy
    assert "allow_position_decrease" in action_policy
    assert payload["decision_context"]["intent"] == "trade"
    assert "why_this_happened" in payload["constraint_analysis"]
    assert "why_this_happened" in payload["impact_on_outcomes"]
    assert payload["adjustment"]
    assert payload["decision_status"] in {"ALLOW", "CONSTRAIN", "VETO"}
    assert "reflex_memory" in payload
    assert payload["decision_context"]["reflex_influence_applied"] is True
    assert "decision_id" in payload


def test_context_method_is_preserved_as_get(client):
    post_response = client.post(
        "/v1/context",
        headers={"Authorization": "Bearer admin-key"},
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    assert post_response.status_code == 405


def test_proof_retrieval_is_owner_scoped_and_authorized(client):
    response = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer pro-key"},
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    assert response.status_code == 200
    decision_id = response.json()["decision_id"]

    allowed = client.get(f"/v1/proof/{decision_id}", headers={"Authorization": "Bearer pro-key"})
    denied = client.get(f"/v1/proof/{decision_id}", headers={"Authorization": "Bearer admin-key"})

    assert allowed.status_code == 200
    assert allowed.json()["decision_id"] == decision_id
    assert denied.status_code == 404
    assert denied.json()["detail"] == "Proof not found"


def test_proof_hash_is_deterministic_for_identical_normalized_inputs(client, monkeypatch):
    monkeypatch.setenv("NOVA_TIMESTAMP_UTC", "2026-04-20T10:00:00+00:00")
    monkeypatch.setenv("NOVA_NOW_UTC", "2026-04-20T10:00:00+00:00")
    first = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer pro-key"},
        params={"intent": "reduce_position", "asset": "ETH", "size": 1000},
    )
    first_proof = client.get(
        f"/v1/proof/{first.json()['decision_id']}",
        headers={"Authorization": "Bearer pro-key"},
    )

    monkeypatch.setenv("NOVA_TIMESTAMP_UTC", "2026-04-20T11:15:00+00:00")
    monkeypatch.setenv("NOVA_NOW_UTC", "2026-04-20T11:15:00+00:00")
    second = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer pro-key"},
        params={"intent": "reduce_position", "asset": "ETH", "size": 1000},
    )
    second_proof = client.get(
        f"/v1/proof/{second.json()['decision_id']}",
        headers={"Authorization": "Bearer pro-key"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_proof.status_code == 200
    assert second_proof.status_code == 200
    assert (
        first_proof.json()["validation"]["reproducibility_hash"]
        == second_proof.json()["validation"]["reproducibility_hash"]
    )


def test_proof_exposure_boundary_stays_outcome_based(client):
    response = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer admin-key"},
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    proof = client.get(
        f"/v1/proof/{response.json()['decision_id']}",
        headers={"Authorization": "Bearer admin-key"},
    )

    assert proof.status_code == 200
    payload = proof.json()
    serialized = json.dumps(payload)

    assert "decision_context" in payload
    assert "nova_evaluation" in payload
    assert "proof" in payload
    assert "validation" in payload
    assert "reflex_memory" not in serialized
    assert "confidence_weight" not in serialized
    assert "constraint_trace" not in serialized
    assert "triggered_registry_id" not in serialized


def test_proof_classification_covers_market_process_telemetry_and_billing(client):
    market = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer admin-key"},
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    market_proof = client.get(
        f"/v1/proof/{market.json()['decision_id']}",
        headers={"Authorization": "Bearer admin-key"},
    )
    assert "market_system_risk" in market_proof.json()["proof"]["classification"]

    process = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer admin-key"},
        params={"intent": "trade", "asset": "ETH"},
    )
    process_proof = client.get(
        f"/v1/proof/{process.json()['decision_id']}",
        headers={"Authorization": "Bearer admin-key"},
    )
    assert "process_integrity" in process_proof.json()["proof"]["classification"]

    telemetry = client.get(
        "/v1/context",
        headers={"Authorization": "Bearer full-governance-key"},
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 10000,
            "telemetry_age_seconds": 1200,
            "telemetry_reliability": 0.95,
        },
    )
    telemetry_proof = client.get(
        f"/v1/proof/{telemetry.json()['decision_id']}",
        headers={"Authorization": "Bearer full-governance-key"},
    )
    assert "telemetry_integrity" in telemetry_proof.json()["proof"]["classification"]


def test_billing_enforcement_proof_classification_is_closed():
    keys = {
        "billing-key": {
            "owner": "billing-user",
            "tier": "pro",
            "status": "active",
            "monthly_quota": 100,
            "prepaid_balance": 0.0,
            "allowed_endpoints": [
                "/v1/context",
                "/v1/proof/{decision_id}",
                "/v1/usage",
                "/v1/billing",
                "/v1/balance",
                "/v1/funding-instructions",
            ],
        }
    }

    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(keys),
            "NOVA_USAGE_FILE": ".usage.billing-proof.test.json",
            "NOVA_PROOF_FILE": ".proof.billing.test.json",
            "NOVA_RUNTIME_MODE": "test",
            "NOVA_ENABLE_BILLING_ENFORCEMENT": "1",
            "NOVA_DEFAULT_PREPAID_BALANCE": "0.0",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)

        response = test_client.get(
            "/v1/context",
            headers={"Authorization": "Bearer billing-key"},
            params={"intent": "reduce_position", "asset": "ETH", "size": 1000},
        )
        assert response.status_code == 402
        proof = test_client.get(
            f"/v1/proof/{response.json()['decision_id']}",
            headers={"Authorization": "Bearer billing-key"},
        )

        assert proof.status_code == 200
        assert proof.json()["proof"]["classification"] == ["billing_enforcement"]

    for path in [".usage.billing-proof.test.json", ".proof.billing.test.json"]:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# Test B: Billable endpoints increment usage
def test_billable_endpoints_increment_usage(client):
    """Verify billable endpoints (/v1/context, /v1/regime, /v1/epoch) increment usage."""
    billable_endpoints = ["/v1/context", "/v1/regime", "/v1/epoch"]
    
    for endpoint in billable_endpoints:
        # Reset usage before test
        from app import USAGE_TRACKING
        USAGE_TRACKING.clear()
        
        # Make a call to the billable endpoint
        headers = {"Authorization": "Bearer admin-key"}
        if endpoint == "/v1/context":
            response = client.get(endpoint, headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
        else:
            response = client.get(endpoint, headers=headers)
        assert response.status_code == 200, f"Endpoint {endpoint} failed with status {response.status_code}"
        
        # Verify usage was tracked
        response = client.get("/v1/usage", headers=headers)
        assert response.status_code == 200
        usage_data = response.json()
        assert usage_data["usage"]["total_calls"] == 1, f"Usage not incremented for {endpoint}"


# Test C: Non-billable endpoints do not increment usage
def test_non_billable_endpoints_no_increment(client):
    """Verify non-billable endpoints (/v1/key-info, /v1/usage) do not increment usage."""
    from app import USAGE_TRACKING
    
    headers = {"Authorization": "Bearer admin-key"}
    
    # Get initial usage
    USAGE_TRACKING.clear()
    response = client.get("/v1/usage", headers=headers)
    assert response.status_code == 200
    initial_usage = response.json()["usage"]["total_calls"]
    
    # Call non-billable endpoint /v1/key-info
    response = client.get("/v1/key-info", headers=headers)
    assert response.status_code == 200
    
    # Verify usage did not change
    response = client.get("/v1/usage", headers=headers)
    assert response.status_code == 200
    new_usage = response.json()["usage"]["total_calls"]
    assert new_usage == initial_usage, "Non-billable endpoint /v1/key-info incremented usage"
    
    # Call /v1/usage itself (should not increment)
    response = client.get("/v1/usage", headers=headers)
    assert response.status_code == 200
    
    # Verify usage still did not change
    response = client.get("/v1/usage", headers=headers)
    assert response.status_code == 200
    final_usage = response.json()["usage"]["total_calls"]
    assert final_usage == initial_usage, "Non-billable endpoint /v1/usage incremented usage"


# Test D: /v1/usage/reset is admin-only
def test_usage_reset_admin_only(client):
    """Verify /v1/usage/reset requires admin tier."""
    # Admin should succeed
    response = client.post("/v1/usage/reset", headers={"Authorization": "Bearer admin-key"})
    assert response.status_code == 200
    
    # Pro user should fail
    response = client.post("/v1/usage/reset", headers={"Authorization": "Bearer pro-key"})
    assert response.status_code == 403
    
    # Free user should fail
    response = client.post("/v1/usage/reset", headers={"Authorization": "Bearer free-low-quota-key"})
    assert response.status_code == 403


# Test E: Quota only applies to billable endpoints
def test_quota_only_for_billable_endpoints(client):
    """Verify low-quota key: non-billable calls don't consume quota, billable calls do."""
    from app import USAGE_TRACKING
    USAGE_TRACKING.clear()
    
    # Use free key with quota of 1
    headers = {"Authorization": "Bearer free-low-quota-key"}
    
    # Make multiple non-billable calls - should not consume quota
    for _ in range(5):
        response = client.get("/v1/key-info", headers=headers)
        assert response.status_code == 200, "Non-billable /v1/key-info should not be rate-limited"
    
    for _ in range(5):
        response = client.get("/v1/usage", headers=headers)
        assert response.status_code == 200, "Non-billable /v1/usage should not be rate-limited"
    
    # Make one billable call - should succeed (quota is 1)
    response = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
    assert response.status_code == 200, "First billable call should succeed"
    
    # Make another billable call - should fail (quota exceeded)
    response = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
    assert response.status_code == 429, "Second billable call should fail with 429 quota exceeded"


# Test F: Invalid/inactive key behavior
def test_invalid_inactive_key_behavior(client):
    """Verify invalid/inactive key rejection and disallowed endpoint rejection."""
    # Invalid key should fail
    response = client.get("/v1/context", headers={"Authorization": "Bearer invalid-key"})
    assert response.status_code == 403
    
    # Pro key calling /v1/usage/reset (not in allowed_endpoints) should fail
    response = client.post("/v1/usage/reset", headers={"Authorization": "Bearer pro-key"})
    assert response.status_code == 403


# Test G: Inactive key rejection
def test_inactive_key_rejected(client):
    """Verify inactive keys are rejected even if structurally valid."""
    response = client.get("/v1/context", headers={"Authorization": "Bearer inactive-key"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Inactive API key"


# Test H: Admin-only restriction even when endpoint allowed
def test_usage_reset_requires_admin_tier_even_if_endpoint_allowed(client):
    """Verify reset is blocked for non-admin keys even when endpoint permission exists."""
    response = client.post("/v1/usage/reset", headers={"Authorization": "Bearer pro-reset-key"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin tier required for this endpoint"


def test_suspended_key_rejected_with_specific_message(client):
    response = client.get("/v1/context", headers={"Authorization": "Bearer suspended-key"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Suspended API key"


def test_key_info_surfaces_active_governance_layers(client):
    response = client.get("/v1/key-info", headers={"Authorization": "Bearer full-governance-key"})

    assert response.status_code == 200
    payload = response.json()
    assert "active_governance_layers" in payload
    assert set(payload["active_governance_layers"]) == {
        "temporal",
        "loop",
        "telemetry",
        "system_state",
        "permission_budgeting",
        "halt_release",
        "human_intervention",
        "queue",
        "memory",
    }


def test_governance_profile_endpoint_returns_enabled_layers_and_environment(client):
    response = client.get("/v1/governance-profile", headers={"Authorization": "Bearer full-governance-key"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment_classification"] == "full_governance"
    assert set(payload["active_governance_layers"]) == {
        "temporal",
        "loop",
        "telemetry",
        "system_state",
        "permission_budgeting",
        "halt_release",
        "human_intervention",
        "queue",
        "memory",
    }
    assert "thresholds" in payload
    assert payload["thresholds"]["temporal"]["max_requests_per_window"] == 2
    assert payload["thresholds"]["queue"]["request_ttl_seconds"] == 300
    assert payload["proving_ground"] is False


def test_governance_profile_endpoint_marks_hyperliquid_proving_ground(client):
    app_module = importlib.import_module("app")
    keys = json.loads(json.dumps(TEST_KEYS))
    keys["hyperliquid-key"] = {
        **keys["full-governance-key"],
        "owner": "hyperliquid-user",
        "proving_ground": "hyperliquid",
    }

    with patch.dict(os.environ, {"NOVA_KEYS_JSON": json.dumps(keys), "NOVA_USAGE_FILE": ".usage.test.json"}):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)
        response = test_client.get("/v1/governance-profile", headers={"Authorization": "Bearer hyperliquid-key"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment_classification"] == "hyperliquid_proving_ground"
    assert payload["proving_ground"] is True
    assert payload["proving_ground_name"] == "hyperliquid"


def test_context_changes_with_large_size(client):
    headers = {"Authorization": "Bearer admin-key"}
    baseline = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    oversized = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 500000},
    )

    assert baseline.status_code == 200
    assert oversized.status_code == 200

    baseline_payload = baseline.json()
    oversized_payload = oversized.json()

    assert baseline_payload["decision_status"] == "CONSTRAIN"
    assert oversized_payload["decision_status"] == "VETO"
    assert baseline_payload["impact_on_outcomes"]["adjusted_size"] == 4000.0
    assert oversized_payload["impact_on_outcomes"]["adjusted_size"] == 0.0


def test_reflex_memory_state_present_in_canonical_path(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    assert response.status_code == 200
    payload = response.json()
    reflex_memory = payload["reflex_memory"]

    assert reflex_memory["schema_version"] == "1.0"
    assert reflex_memory["mode"] == "retained_discipline"
    assert reflex_memory["persistence_state"] == "retained"
    assert reflex_memory["validation_status"] == "validated"
    assert reflex_memory["active_registry_id"] == "elevated_fragility_size_brake"
    assert reflex_memory["triggered"] is True
    assert reflex_memory["influence_applied"] is True
    assert reflex_memory["decision_before_reflex"] == "CONSTRAIN"
    assert reflex_memory["decision_after_reflex"] == "CONSTRAIN"
    assert isinstance(reflex_memory["registered_entries"], list)


def test_reflex_influence_changes_decision_output(client, monkeypatch):
    app_module = importlib.import_module("app")
    headers = {"Authorization": "Bearer admin-key"}

    monkeypatch.setattr(app_module, "DEFAULT_REGIME", "Elevated Fragility")
    constrained = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    monkeypatch.setattr(app_module, "DEFAULT_REGIME", "Stable")
    baseline = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    constrained_payload = constrained.json()
    baseline_payload = baseline.json()

    assert constrained.status_code == 200
    assert baseline.status_code == 200
    assert constrained_payload["impact_on_outcomes"]["adjusted_size"] == 4000.0
    assert baseline_payload["impact_on_outcomes"]["adjusted_size"] == 10000.0
    assert constrained_payload["adjustment"] != baseline_payload["adjustment"]
    assert constrained_payload["reflex_memory"]["influence_applied"] is True
    assert baseline_payload["reflex_memory"]["influence_applied"] is False


def test_reflex_proof_emits_coherently(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    assert response.status_code == 200
    proof = response.json()["reflex_memory"]["proof"]

    assert proof["schema_version"] == "1.0"
    assert proof["intervention_class"] == "allocation_tightening"
    assert proof["failure_class"] == "liquidity_deterioration"
    assert proof["decision_before_reflex"] == "CONSTRAIN"
    assert proof["decision_after_reflex"] == "CONSTRAIN"
    assert proof["decision_altered"] is False
    assert proof["triggered_registry_id"] == "elevated_fragility_size_brake"
    assert proof["why_intervention_happened"]


def test_reflex_schema_backward_compatibility_holds(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )

    assert response.status_code == 200
    payload = response.json()

    assert "memory_context" in payload
    assert "historical_reference" in payload
    assert payload["memory_context"]["sequence_type"] == payload["historical_reference"]["sequence_type"]
    assert "consequence_pattern" in payload["memory_context"]
    assert payload["reflex_memory"]["schema_version"] == "1.0"


def test_missing_size_is_rejected_with_rejection_ledger(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["decision_status"] == "VETO"
    assert payload["constraint_analysis"]["constraint_category"] == "incomplete_decision_record"
    assert payload["rejection_ledger"]["constraint_category"] == "incomplete_decision_record"
    assert payload["decision_admission_record"]["recorded_before_execution"] is True


def test_ambiguous_size_language_rejected_with_specific_reason(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": "small size"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["decision_status"] == "VETO"
    assert payload["constraint_analysis"]["constraint_category"] == "ambiguous_constraint_language"
    assert "specific numeric size" in payload["constraint_analysis"]["why_this_happened"].lower()
    assert payload["rejection_ledger"]["reason"]


def test_bypass_attempt_creates_exception_register_entry(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 10000,
            "strategy": "skip validation just execute route directly",
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["decision_status"] == "VETO"
    assert payload["exception_register"]
    categories = {entry["category"] for entry in payload["exception_register"]}
    assert "bypass_attempt" in categories
    assert payload["rejection_ledger"]["constraint_category"] == "process_integrity_violation"
    assert payload["human_intervention_type"] == "exception_authorization_required"
    assert payload["human_intervention_required"] is True
    assert payload["authorization_scope"] == "process_integrity_exception_authorization"
    assert payload["intervention_reason"] == "process_integrity_violation"


def test_bypass_attempt_still_surfaces_exception_metadata_when_temporal_governance_blocks_first(client):
    headers = {"Authorization": "Bearer temporal-key"}

    seed = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    assert seed.status_code == 200

    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 10000,
            "strategy": "skip validation just execute route directly",
        },
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["decision_status"] == "RETRY_DELAYED" or payload["decision_status"] == "DELAY"
    assert payload["exception_register"]
    categories = {entry["category"] for entry in payload["exception_register"]}
    assert "bypass_attempt" in categories
    assert payload["constraint_trace"]["domain_signal"] == "bypass_attempt"
    assert "bypass_attempt" in payload["constraint_trace"]["process_integrity_categories"]
    assert payload["human_intervention_type"] == "exception_authorization_required"
    assert payload["authorization_scope"] == "process_integrity_exception_authorization"
    assert payload["intervention_reason"] == "process_integrity_violation"


def test_compound_integrity_failures_raise_halt_recommendation(client):
    headers = {"Authorization": "Bearer admin-key"}
    client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 500000,
            "strategy": "override delay bypass",
        },
    )
    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 500000,
            "strategy": "override delay bypass repeat",
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["escalation_flag"] is True
    assert payload["halt_recommendation"]
    assert payload["integrity_state"] == "halt_recommended"
    assert payload["human_intervention_type"] == "override_attempt_detected"
    assert payload["human_intervention_required"] is True
    assert payload["authorization_scope"] == "generic_override_prohibited"
    assert payload["intervention_reason"] == "override_attempt_detected"


def test_stablecoin_trace_enrichment_present(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "increase_position", "asset": "USDC", "size": 20000, "strategy": "peg_instability"},
    )

    assert response.status_code == 200
    trace = response.json()["constraint_trace"]
    assert trace["constraint_category"] == "stablecoin"
    assert trace["reflex_memory_class"] == "stablecoin_defense"
    assert trace["domain_signal"] == "peg_instability"
    assert trace["prevented_risk_type"] == "depeg_exposure"


def test_validator_trace_enrichment_present(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "increase_position", "asset": "stETH", "size": 20000, "strategy": "validator_uptime_drop"},
    )

    assert response.status_code == 200
    trace = response.json()["constraint_trace"]
    assert trace["constraint_category"] == "validator"
    assert trace["reflex_memory_class"] == "validator_reflex"
    assert trace["domain_signal"] == "uptime_degradation"
    assert trace["telemetry_domain"] == "validator_telemetry"


def test_governance_trace_enrichment_present(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "increase_position", "asset": "LDO", "size": 20000, "strategy": "delegate_concentration"},
    )

    assert response.status_code == 200
    trace = response.json()["constraint_trace"]
    assert trace["constraint_category"] == "governance"
    assert trace["reflex_memory_class"] == "governance_reflex"
    assert trace["domain_signal"] == "delegate_concentration"
    assert trace["prevented_risk_type"] == "governance_capture"


def test_macro_trace_enrichment_present(client):
    headers = {"Authorization": "Bearer admin-key"}
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000, "strategy": "macro rate shock"},
    )

    assert response.status_code == 200
    trace = response.json()["constraint_trace"]
    assert trace["constraint_category"] == "macro"
    assert trace["reflex_memory_class"] == "macro_reflex"
    assert trace["domain_signal"] == "rate_shock"
    assert trace["regime_context_applied"] is True


def test_cross_decision_pressure_is_visible(client):
    headers = {"Authorization": "Bearer admin-key"}
    client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 10000},
    )
    response = client.get(
        "/v1/context",
        headers=headers,
        params={"intent": "trade", "asset": "ETH", "size": 20000},
    )

    assert response.status_code == 200
    trace = response.json()["constraint_trace"]
    assert trace["cross_decision_pressure"] is True
    assert trace["related_prior_decisions"]
    assert trace["accumulated_constraint_category"] == "exposure_compounding"
    assert trace["exposure_compounding_detected"] is True


def test_temporal_retry_spacing_delays_valid_decision(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer temporal-key"}
    params = {"intent": "trade", "asset": "ETH", "size": 10000}

    first = client.get("/v1/context", headers=headers, params=params)
    second = client.get("/v1/context", headers=headers, params=params)

    assert first.status_code == 200
    assert first.json()["temporal_constraint_triggered"] is False
    assert second.status_code == 429
    payload = second.json()
    assert payload["decision_status"] == "DELAY"
    assert payload["cooldown_active"] is True
    assert payload["cooldown_state"]["reason"] == "retry_spacing_active"
    assert payload["temporal_constraint_triggered"] is True
    assert payload["retry_cooldown_expiry"] is not None


def test_temporal_request_rate_limit_sets_deny_cooldown(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer temporal-key"}

    first = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 46, tzinfo=timezone.utc)
    second = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "BTC", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc)
    third = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "SOL", "size": 10000})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    payload = third.json()
    assert payload["decision_status"] == "DENY"
    assert payload["decision_count_window"]["request_count"] == 3
    assert payload["decision_count_window"]["max_requests"] == 2
    assert payload["cooldown_state"]["reason"] == "deny_cooldown_active"
    assert payload["temporal_constraint_triggered"] is True


def test_temporal_cooldown_expiry_resets_behavior(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer temporal-key"}

    client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 46, tzinfo=timezone.utc)
    client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "BTC", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc)
    denied = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "SOL", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 5, 1, tzinfo=timezone.utc)
    allowed = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ADA", "size": 10000})

    assert denied.status_code == 429
    assert denied.json()["decision_status"] == "DENY"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["temporal_constraint_triggered"] is False
    assert payload["cooldown_active"] is False


def test_temporal_checks_run_before_core_admission_logic(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer temporal-key"}
    client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})

    def fail_guardrail(*args, **kwargs):
        raise AssertionError("build_guardrail should not run when temporal governance blocks first")

    monkeypatch.setattr(app_module, "build_guardrail", fail_guardrail)
    blocked = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})

    assert blocked.status_code == 429
    assert blocked.json()["decision_status"] == "DELAY"


def test_temporal_halt_quarantine_blocks_further_admission(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer temporal-halt-key"}
    client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "ETH", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 20, tzinfo=timezone.utc)
    client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "BTC", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 40, tzinfo=timezone.utc)
    halted = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "SOL", "size": 10000})
    current_time = datetime(2026, 1, 1, 12, 0, 50, tzinfo=timezone.utc)
    quarantined = client.get("/v1/context", headers=headers, params={"intent": "trade", "asset": "XRP", "size": 10000})

    assert halted.status_code == 409
    assert halted.json()["decision_status"] == "HALT"
    assert halted.json()["post_halt_quarantine_expiry"] is not None
    assert quarantined.status_code == 409
    assert quarantined.json()["decision_status"] == "HALT"
    assert quarantined.json()["cooldown_state"]["reason"] == "halt_quarantine_active"


def test_telemetry_deny_seeds_loop_history_for_same_family(client):
    headers = {"Authorization": "Bearer full-governance-key"}

    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ETH",
            "size": 10000,
            "strategy": "telemetry_deny_seed",
            "telemetry_reliability": 0.4,
            "telemetry_age_seconds": 10,
            "telemetry_source_scores": "book:0.42,oi:0.38",
        },
    )

    assert response.status_code == 429
    assert response.json()["decision_status"] == "DENY"

    from app import LOOP_INTEGRITY_STATE

    family_denials = LOOP_INTEGRITY_STATE["full-governance-key"]["family_denials"]["trade:eth"]
    assert family_denials
    assert family_denials[-1]["constraint_category"] == "telemetry_integrity"


def test_telemetry_halt_seeds_loop_history_for_same_family(client):
    headers = {"Authorization": "Bearer full-governance-key"}

    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "ARB",
            "size": 10000,
            "strategy": "telemetry_halt_seed",
            "telemetry_age_seconds": 10,
            "telemetry_source_scores": "book:0.99,oi:0.20",
        },
    )

    assert response.status_code == 409
    assert response.json()["decision_status"] == "HALT"

    from app import LOOP_INTEGRITY_STATE

    family_denials = LOOP_INTEGRITY_STATE["full-governance-key"]["family_denials"]["trade:arb"]
    assert family_denials
    assert family_denials[-1]["constraint_category"] == "telemetry_integrity"


def test_telemetry_delay_does_not_seed_loop_history(client):
    headers = {"Authorization": "Bearer full-governance-key"}

    response = client.get(
        "/v1/context",
        headers=headers,
        params={
            "intent": "trade",
            "asset": "BTC",
            "size": 10000,
            "strategy": "telemetry_delay_seed",
            "telemetry_reliability": 0.95,
            "telemetry_age_seconds": 600,
            "telemetry_source_scores": "book:0.96,oi:0.94",
        },
    )

    assert response.status_code == 429
    assert response.json()["decision_status"] == "DELAY"

    from app import LOOP_INTEGRITY_STATE

    assert LOOP_INTEGRITY_STATE["full-governance-key"]["family_denials"].get("trade:btc") is None


def test_same_family_retry_after_telemetry_deny_surfaces_loop_fields(client, monkeypatch):
    app_module = importlib.import_module("app")
    current_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module, "get_current_datetime", lambda: current_time)

    headers = {"Authorization": "Bearer full-governance-key"}
    seed_params = {
        "intent": "trade",
        "asset": "ETH",
        "size": 10000,
        "strategy": "telemetry_retry_seed",
        "telemetry_reliability": 0.4,
        "telemetry_age_seconds": 10,
        "telemetry_source_scores": "book:0.42,oi:0.38",
    }
    retry_params = {
        "intent": "trade",
        "asset": "ETH",
        "size": 10000,
        "strategy": "telemetry_retry_seed",
        "telemetry_reliability": 0.95,
        "telemetry_age_seconds": 10,
        "telemetry_source_scores": "book:0.96,oi:0.94",
    }

    seed = client.get("/v1/context", headers=headers, params=seed_params)
    current_time = datetime(2026, 1, 1, 12, 0, 46, tzinfo=timezone.utc)
    retry = client.get("/v1/context", headers=headers, params=retry_params)

    assert seed.status_code == 429
    assert seed.json()["decision_status"] == "DENY"
    assert retry.status_code == 429
    payload = retry.json()
    assert payload["decision_status"] == "RETRY_DELAYED"
    assert payload["retry_count_by_family"] == 1
    assert payload["semantic_similarity_to_prior_denial"] > 0
    assert payload["loop_classification"] == "pressure_retry"
    assert payload["pressure_score"] > 0
    assert payload["loop_integrity_state"] == "retry_delayed"
    assert payload["telemetry_integrity_state"] == "not_evaluated"


def test_context_billing_object_debits_allow_and_constrain_only(client):
    app_module = importlib.import_module("app")
    headers = {"Authorization": "Bearer admin-key"}

    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(TEST_KEYS),
            "NOVA_USAGE_FILE": ".usage.billing-explicit.test.json",
            "NOVA_RUNTIME_MODE": "test",
            "NOVA_ENABLE_BILLING_ENFORCEMENT": "1",
            "NOVA_DEFAULT_PREPAID_BALANCE": "1000.0",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)

        allow_response = test_client.get(
            "/v1/context",
            headers=headers,
            params={"intent": "reduce_position", "asset": "ETH", "size": 1000},
        )
        assert allow_response.status_code == 200
        allow_payload = allow_response.json()
        assert allow_payload["decision_status"] == "ALLOW"
        assert allow_payload["billing"]["billable_event"] is True
        assert allow_payload["billing"]["cost_this_request"] == 0.01
        assert allow_payload["billing"]["remaining_balance"] == 999.99
        assert allow_payload["billing"]["currency"] == "USDC"
        assert allow_payload["billing"]["pricing_version"] == "v1"
        assert allow_payload["billing"]["enforcement_active"] is True

        veto_response = test_client.get(
            "/v1/context",
            headers=headers,
            params={"intent": "trade", "asset": "ETH", "size": 1000000},
        )
        assert veto_response.status_code == 200
        veto_payload = veto_response.json()
        assert veto_payload["decision_status"] == "VETO"
        assert veto_payload["billing"]["billable_event"] is False
        assert veto_payload["billing"]["cost_this_request"] == 0.0
        assert veto_payload["billing"]["remaining_balance"] == 999.99

    try:
        os.remove(".usage.billing-explicit.test.json")
    except FileNotFoundError:
        pass


def test_context_billing_denies_when_balance_is_insufficient():
    app_module = importlib.import_module("app")
    keys = {
        "billing-key": {
            "owner": "billing-user",
            "tier": "pro",
            "status": "active",
            "monthly_quota": 100,
            "prepaid_balance": 0.0,
            "allowed_endpoints": [
                "/v1/context",
                "/v1/usage",
                "/v1/billing",
                "/v1/balance",
                "/v1/funding-instructions",
            ],
        }
    }

    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(keys),
            "NOVA_USAGE_FILE": ".usage.billing-enforcement.test.json",
            "NOVA_RUNTIME_MODE": "test",
            "NOVA_ENABLE_BILLING_ENFORCEMENT": "1",
            "NOVA_DEFAULT_PREPAID_BALANCE": "0.0",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)

        response = test_client.get(
            "/v1/context",
            headers={"Authorization": "Bearer billing-key"},
            params={"intent": "reduce_position", "asset": "ETH", "size": 1000},
        )

        assert response.status_code == 402
        payload = response.json()
        assert payload["decision_status"] == "DENY"
        assert payload["constraint_analysis"]["constraint_category"] == "billing"
        assert payload["constraint_analysis"]["why_this_happened"] == "insufficient_balance"
        assert payload["billing"]["billable_event"] is False
        assert payload["billing"]["remaining_balance"] == 0.0
        assert payload["billing"]["currency"] == "USDC"

        balance = test_client.get("/v1/balance", headers={"Authorization": "Bearer billing-key"})
        assert balance.status_code == 200
        balance_payload = balance.json()
        assert balance_payload["balance"] == 0.0
        assert any(item["type"] == "billing_denial" for item in balance_payload["transaction_history"])

    try:
        os.remove(".usage.billing-enforcement.test.json")
    except FileNotFoundError:
        pass


def test_billing_and_balance_endpoints_surface_wallet_first_metadata():
    keys = {
        "wallet-key": {
            "owner": "wallet-user",
            "tier": "pro",
            "status": "active",
            "monthly_quota": 100,
            "prepaid_balance": 25.0,
            "allowed_endpoints": [
                "/v1/context",
                "/v1/usage",
                "/v1/billing",
                "/v1/balance",
                "/v1/funding-instructions",
            ],
        }
    }

    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(keys),
            "NOVA_USAGE_FILE": ".usage.billing-read.test.json",
            "NOVA_RUNTIME_MODE": "test",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)

        billing = test_client.get("/v1/billing", headers={"Authorization": "Bearer wallet-key"})
        assert billing.status_code == 200
        billing_payload = billing.json()
        assert billing_payload["payment_method"] == "wallet"
        assert billing_payload["currency"] == "USDC"
        assert billing_payload["network"] == "base"
        assert billing_payload["balance"] == 25.0
        assert billing_payload["pricing_version"] == "v1"
        assert billing_payload["runtime_mode"] == "test"
        assert billing_payload["billing_enforcement_active"] is False
        assert billing_payload["persistent_ledger_configured"] is False
        assert billing_payload["billable_policy"]["allow_billable"] is True
        assert billing_payload["billable_policy"]["deny_billable"] is False
        assert billing_payload["funding_instructions"]["destination_wallet"] == "0xb29b02130138a6fF8e0f6D7812bDa8D436001BE4"

        balance = test_client.get("/v1/balance", headers={"Authorization": "Bearer wallet-key"})
        assert balance.status_code == 200
        balance_payload = balance.json()
        assert balance_payload["billing_identity_type"] == "wallet"
        assert balance_payload["balance"] == 25.0
        assert balance_payload["currency"] == "USDC"
        assert balance_payload["transaction_history"] == []

        funding = test_client.get("/v1/funding-instructions", headers={"Authorization": "Bearer wallet-key"})
        assert funding.status_code == 200
        funding_payload = funding.json()
        assert funding_payload["destination_wallet"] == "0xb29b02130138a6fF8e0f6D7812bDa8D436001BE4"
        assert funding_payload["asset"] == "USDC"
        assert funding_payload["network"] == "base"
        assert funding_payload["billing_mode"] == "prepaid"
        assert funding_payload["billing_enforcement_active"] is False

    try:
        os.remove(".usage.billing-read.test.json")
    except FileNotFoundError:
        pass


def test_production_runtime_requires_persistent_billing_store():
    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(TEST_KEYS),
            "NOVA_RUNTIME_MODE": "production",
            "NOVA_BILLING_FILE": "",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        with pytest.raises(RuntimeError, match="NOVA_BILLING_FILE"):
            importlib.import_module("app")


def test_production_runtime_rejects_positive_default_prepaid_balance(tmp_path):
    billing_path = tmp_path / "billing.json"
    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(TEST_KEYS),
            "NOVA_RUNTIME_MODE": "production",
            "NOVA_BILLING_FILE": str(billing_path),
            "NOVA_DEFAULT_PREPAID_BALANCE": "1.0",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        with pytest.raises(RuntimeError, match="zero default prepaid balance"):
            importlib.import_module("app")


def test_governance_ordering_is_unchanged_when_billing_balance_is_zero():
    keys = {
        "ordering-key": {
            "owner": "ordering-user",
            "tier": "pro",
            "status": "active",
            "monthly_quota": 100,
            "prepaid_balance": 0.0,
            "allowed_endpoints": [
                "/v1/context",
                "/v1/usage",
                "/v1/billing",
                "/v1/balance",
            ],
            "telemetry_integrity": {
                "stale_after_seconds": 300,
                "default_min_reliability": 0.7,
                "risk_increasing_min_reliability": 0.8,
                "risk_reducing_min_reliability": 0.6,
                "disagreement_threshold": 0.35,
                "halt_disagreement_threshold": 0.7,
                "halt_on_degraded": True,
            },
        }
    }

    with patch.dict(
        os.environ,
        {
            "NOVA_KEYS_JSON": json.dumps(keys),
            "NOVA_USAGE_FILE": ".usage.billing-ordering.test.json",
            "NOVA_RUNTIME_MODE": "test",
            "NOVA_ENABLE_BILLING_ENFORCEMENT": "1",
        },
        clear=False,
    ):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        test_client = TestClient(app_module.app)

        response = test_client.get(
            "/v1/context",
            headers={"Authorization": "Bearer ordering-key"},
            params={
                "intent": "trade",
                "asset": "ETH",
                "size": 10000,
                "telemetry_age_seconds": 1200,
                "telemetry_reliability": 0.95,
            },
        )

        assert response.status_code == 429
        payload = response.json()
        assert payload["decision_status"] == "DELAY"
        assert payload["constraint_analysis"]["constraint_category"] == "telemetry_integrity"
        assert payload["billing"]["billable_event"] is False
        assert payload["billing"]["remaining_balance"] == 0.0

    try:
        os.remove(".usage.billing-ordering.test.json")
    except FileNotFoundError:
        pass
