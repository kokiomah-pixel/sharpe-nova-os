import importlib
import json
import os
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
            "/v1/key-info",
            "/v1/usage",
            "/v1/usage/reset",
        ],
    },
}


@pytest.fixture
def client():
    """Create a test client with mocked NOVA_KEYS_JSON."""
    keys_json = json.dumps(TEST_KEYS)
    with patch.dict(os.environ, {"NOVA_KEYS_JSON": keys_json, "NOVA_USAGE_FILE": ".usage.test.json"}):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        app = app_module.app
        USAGE_TRACKING = app_module.USAGE_TRACKING
        REJECTION_LEDGER = app_module.REJECTION_LEDGER
        EXCEPTION_REGISTER = app_module.EXCEPTION_REGISTER
        HALT_SIGNAL_STATE = app_module.HALT_SIGNAL_STATE
        USAGE_TRACKING.clear()
        REJECTION_LEDGER.clear()
        EXCEPTION_REGISTER.clear()
        HALT_SIGNAL_STATE.clear()
        yield TestClient(app)
        USAGE_TRACKING.clear()
        REJECTION_LEDGER.clear()
        EXCEPTION_REGISTER.clear()
        HALT_SIGNAL_STATE.clear()
        try:
            os.remove(".usage.test.json")
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

