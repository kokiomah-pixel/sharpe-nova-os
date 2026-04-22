import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.reflex_governance_runtime.alert_engine import ReflexGovernanceAlertEngine
from core.reflex_governance_runtime.outputs.alert import render_architect_alert
from core.reflex_governance_runtime.outputs.ledger import build_reflex_ledger
from core.reflex_governance_runtime.outputs.pulse import render_reflex_pulse
from core.reflex_governance_runtime.pattern_engine import detect_structural_patterns


def _record(
    *,
    decision_id: str,
    observed_at: str,
    normalized_signature: str = '{"asset":"ETH","intent":"risk_increasing","requested_action":"trade"}',
    decision_status: str = "CONSTRAIN",
    intervention_type: str = "reduced",
    classification=None,
    reproducibility_hash: str = "hash-a",
    reflex_ids=None,
    account_id: str = "acct-1",
    outcome_influenced: bool = True,
    registered_reflex_ids=None,
):
    return {
        "decision_id": decision_id,
        "observed_at": observed_at,
        "normalized_signature": normalized_signature,
        "decision_status": decision_status,
        "context_decision_status": decision_status,
        "intervention_type": intervention_type,
        "classification": classification if classification is not None else ["market_system_risk"],
        "reproducibility_hash": reproducibility_hash,
        "reflex_ids": reflex_ids if reflex_ids is not None else ["rx-1"],
        "registered_reflex_ids": registered_reflex_ids if registered_reflex_ids is not None else ["rx-1"],
        "account_id": account_id,
        "proof_decision_status": decision_status,
        "memory_influence_present": True,
        "outcome_influenced": outcome_influenced,
    }


def _engine(tmp_path: Path) -> ReflexGovernanceAlertEngine:
    return ReflexGovernanceAlertEngine(
        signals_path=tmp_path / "signals.json",
        escalations_path=tmp_path / "escalations.json",
    )


def test_repeated_pattern_escalation_only(tmp_path):
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    records = [
        _record(decision_id="d1", observed_at="2026-04-20T00:00:00+00:00"),
        _record(decision_id="d2", observed_at="2026-04-21T00:00:00+00:00"),
        _record(decision_id="d3", observed_at="2026-04-22T00:00:00+00:00"),
    ]
    patterns = detect_structural_patterns(records, now=now)
    overactive = next(pattern for pattern in patterns if pattern["flag"] == "overactive_reflex" and pattern["window_days"] == 7)

    result = _engine(tmp_path).observe_patterns([overactive], observed_at="2026-04-22T00:00:00+00:00")

    assert result["signals"][0]["status"] == "escalate"
    assert result["escalations"][0]["state"] == "pending_resolution"


def test_no_alert_on_single_anomaly(tmp_path):
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    records = [
        _record(
            decision_id="d1",
            observed_at="2026-04-22T00:00:00+00:00",
            classification=[],
            reflex_ids=["rx-1"],
        )
    ]
    patterns = detect_structural_patterns(records, now=now)
    result = _engine(tmp_path).observe_patterns(patterns, observed_at="2026-04-22T00:00:00+00:00")

    assert result["escalations"] == []
    assert all(signal["status"] != "escalate" for signal in result["signals"])


def test_mandatory_escalation_disposition_recording_and_hold_resolution(tmp_path):
    engine = _engine(tmp_path)
    pattern = {
        "pattern_key": "classification_inconsistency:sig-1:7",
        "flag": "classification_inconsistency",
        "domain": "classification",
        "scope": "sig-1",
        "window_days": 7,
        "occurrences": 3,
        "evidence": {"normalized_signature": "sig-1"},
        "affects_outcomes": True,
    }
    engine.observe_patterns([pattern], observed_at="2026-04-22T00:00:00+00:00")
    escalation_id = engine.reviewable_escalations()[0]["escalation_id"]

    pending = engine.reviewable_escalations()[0]
    assert pending["resolution"] is None
    assert pending["state"] == "pending_resolution"

    resolved = engine.record_resolution(escalation_id, action="HOLD", resolved_at="2026-04-22T01:00:00+00:00")

    assert resolved["state"] == "resolved"
    assert resolved["resolution"]["action"] == "HOLD"
    assert resolved["resolution"]["pattern_key"] == pattern["pattern_key"]


def test_classification_governance_constraint_recommends_validate(tmp_path):
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    records = [
        _record(decision_id="d1", observed_at="2026-04-20T00:00:00+00:00", classification=["market_system_risk"]),
        _record(decision_id="d2", observed_at="2026-04-21T00:00:00+00:00", classification=["process_integrity"]),
        _record(decision_id="d3", observed_at="2026-04-22T00:00:00+00:00", classification=["telemetry_integrity"]),
    ]
    patterns = detect_structural_patterns(records, now=now)
    inconsistency = next(pattern for pattern in patterns if pattern["flag"] == "classification_inconsistency")

    result = _engine(tmp_path).observe_patterns([inconsistency], observed_at="2026-04-22T00:00:00+00:00")

    assert result["signals"][0]["recommended_posture"] == "VALIDATE"
    assert result["escalations"][0]["recommended_posture"] == "VALIDATE"


def test_active_watch_and_resolved_states_remain_reviewable(tmp_path):
    engine = _engine(tmp_path)
    pattern = {
        "pattern_key": "overactive_reflex:rx-1:30",
        "flag": "overactive_reflex",
        "domain": "reflex",
        "scope": "rx-1",
        "window_days": 30,
        "occurrences": 3,
        "evidence": {"reflex_id": "rx-1"},
        "affects_outcomes": True,
    }
    engine.observe_patterns([pattern], observed_at="2026-04-22T00:00:00+00:00")
    escalation_id = engine.reviewable_escalations()[0]["escalation_id"]

    engine.mark_active_watch(escalation_id, noted_at="2026-04-22T00:05:00+00:00")
    watch_state = engine.reviewable_escalations()[0]
    assert watch_state["state"] == "active_watch"
    assert watch_state["watch"]["pattern_key"] == pattern["pattern_key"]

    engine.record_resolution(escalation_id, action="VALIDATE", resolved_at="2026-04-22T01:00:00+00:00")
    resolved_state = engine.reviewable_escalations()[0]
    assert resolved_state["state"] == "resolved"
    assert engine.reviewable_resolution_history()[0]["action"] == "VALIDATE"


def test_strong_governance_actions_require_persistent_multi_window_impact(tmp_path):
    engine = _engine(tmp_path)
    weak_pattern = {
        "pattern_key": "classification_compression:market_system_risk:7",
        "flag": "classification_compression",
        "domain": "classification",
        "scope": "market_system_risk",
        "window_days": 7,
        "occurrences": 3,
        "evidence": {},
        "affects_outcomes": True,
    }
    engine.observe_patterns([weak_pattern], observed_at="2026-04-22T00:00:00+00:00")
    escalation_id = engine.reviewable_escalations()[0]["escalation_id"]

    with pytest.raises(ValueError):
        engine.record_resolution(escalation_id, action="FORMALIZE")


APP_TEST_KEYS = {
    "runtime-key": {
        "owner": "runtime-user",
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
def runtime_client(tmp_path):
    env = {
        "NOVA_KEYS_JSON": json.dumps(APP_TEST_KEYS),
        "NOVA_USAGE_FILE": str(tmp_path / ".usage.runtime.json"),
        "NOVA_PROOF_FILE": str(tmp_path / ".proof.runtime.json"),
        "NOVA_PROOF_RETRIEVAL_AUDIT_FILE": str(tmp_path / "proof_retrieval.runtime.jsonl"),
        "NOVA_REFLEX_GOVERNANCE_RECORDS_FILE": str(tmp_path / ".reflex.records.jsonl"),
        "NOVA_REFLEX_GOVERNANCE_SIGNALS_FILE": str(tmp_path / ".reflex.signals.json"),
        "NOVA_REFLEX_GOVERNANCE_ESCALATIONS_FILE": str(tmp_path / ".reflex.escalations.json"),
    }
    with patch.dict(os.environ, env, clear=False):
        sys.modules.pop("app", None)
        app_module = importlib.import_module("app")
        app_module.USAGE_TRACKING.clear()
        app_module.PROOF_REGISTRY.clear()
        app_module.REFLEX_GOVERNANCE_RECORDS.clear()
        app_module.REFLEX_GOVERNANCE_ALERT_ENGINE.signals.clear()
        app_module.REFLEX_GOVERNANCE_ALERT_ENGINE.escalations.clear()
        yield TestClient(app_module.app), app_module, tmp_path


def _headers():
    return {"Authorization": "Bearer runtime-key"}


def test_runtime_is_observational_and_does_not_interfere_with_context_or_proof(runtime_client):
    client, app_module, tmp_path = runtime_client
    response = client.get(
        "/v1/context",
        headers=_headers(),
        params={"intent": "trade", "asset": "ETH", "size": "10000"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_status"] == "CONSTRAIN"
    assert payload["impact_on_outcomes"]["adjusted_size"] == 4000.0

    proof = client.get(f"/v1/proof/{payload['decision_id']}", headers=_headers())
    assert proof.status_code == 200
    proof_payload = proof.json()
    assert proof_payload["decision_status"] == "CONSTRAIN"
    assert "signature" in proof_payload

    records_path = tmp_path / ".reflex.records.jsonl"
    assert records_path.exists()
    assert len(app_module.REFLEX_GOVERNANCE_RECORDS) == 1


def test_runtime_outputs_are_structured_and_minimal(tmp_path):
    engine = _engine(tmp_path)
    pattern = {
        "pattern_key": "classification_inconsistency:sig-1:30",
        "flag": "classification_inconsistency",
        "domain": "classification",
        "scope": "sig-1",
        "window_days": 30,
        "occurrences": 3,
        "evidence": {"normalized_signature": "sig-1"},
        "affects_outcomes": True,
    }
    observed = engine.observe_patterns([pattern], observed_at="2026-04-22T00:00:00+00:00")
    escalation = observed["escalations"][0]
    engine.mark_active_watch(escalation["escalation_id"], noted_at="2026-04-22T00:10:00+00:00")
    pulse = render_reflex_pulse(observed["signals"])
    ledger = build_reflex_ledger(signals=observed["signals"], escalations=engine.reviewable_escalations())
    alert = render_architect_alert(engine.reviewable_escalations()[0])

    assert "REFLEX PULSE OPS" in pulse
    assert "Alert posture: escalate" in pulse
    assert "classification_anomalies" in ledger
    assert "active_watch_backlog" in ledger
    assert "REFLEX ALERT" in alert
    assert "Recommended posture: validate" in alert
