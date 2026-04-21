"""Adapter tests may inspect supporting fields, but consumer authority remains
bound to primary decision fields and proof outcomes."""

from __future__ import annotations

import importlib


adapter = importlib.import_module("examples.hyperliquid_nova_enforcement_adapter")


def _nova_response(*, decision_status: str, requested_size: float = 10000, adjusted_size: float | None = None, **overrides):
    if adjusted_size is None:
        adjusted_size = requested_size
    payload = {
        "decision_status": decision_status,
        "decision_context": {
            "requested_size": requested_size,
        },
        "impact_on_outcomes": {
            "requested_size": requested_size,
            "adjusted_size": adjusted_size,
        },
        "adjustment": "Nova-controlled adjustment",
        "system_state": "NORMAL",
        "cooldown_state": {"active": False, "reason": "none"},
        "retry_cooldown_expiry": None,
        "post_halt_quarantine_expiry": None,
        "queue_priority": "normal",
        "queue_position": 1,
        "batch_review_required": False,
    }
    payload.update(overrides)
    return payload


def test_deny_blocks_downstream_continuation():
    result = adapter.enforce_nova_response(
        _nova_response(decision_status="DENY", adjusted_size=0.0, system_state="PRESSURE_ELEVATED")
    )

    assert result["allowed_to_proceed"] is False
    assert result["authoritative_decision_status"] == "DENY"
    assert result["effective_constraints"]["effective_size"] == 0.0


def test_halt_blocks_downstream_continuation():
    result = adapter.enforce_nova_response(
        _nova_response(decision_status="HALT", adjusted_size=0.0, system_state="HALT_ACTIVE")
    )

    assert result["allowed_to_proceed"] is False
    assert result["authoritative_decision_status"] == "HALT"
    assert result["effective_constraints"]["system_state"] == "HALT_ACTIVE"


def test_delay_blocks_downstream_continuation():
    result = adapter.enforce_nova_response(
        _nova_response(
            decision_status="DELAY",
            adjusted_size=0.0,
            cooldown_state={"active": True, "reason": "retry_spacing_active"},
            retry_cooldown_expiry="2026-04-13T12:01:00+00:00",
        )
    )

    assert result["allowed_to_proceed"] is False
    assert result["authoritative_decision_status"] == "DELAY"
    assert result["effective_constraints"]["retry_cooldown_expiry"] == "2026-04-13T12:01:00+00:00"


def test_reduce_only_allows_constrained_values_through():
    result = adapter.enforce_nova_response(
        _nova_response(decision_status="REDUCE", requested_size=10000, adjusted_size=6000)
    )

    assert result["allowed_to_proceed"] is True
    assert result["authoritative_decision_status"] == "REDUCE"
    assert result["effective_constraints"]["requested_size"] == 10000
    assert result["effective_constraints"]["effective_size"] == 6000


def test_metadata_cannot_bypass_authoritative_decision_status():
    result = adapter.enforce_nova_response(
        _nova_response(
            decision_status="DENY",
            adjusted_size=0.0,
            guardrail={"action_policy": {"allow_new_risk": True}},
            queue_priority="high",
            batch_review_required=False,
        )
    )

    assert result["allowed_to_proceed"] is False
    assert result["authoritative_decision_status"] == "DENY"


def test_no_auto_retry_or_fallback_path_exists(monkeypatch):
    calls = []

    def fake_fetch(**kwargs):
        calls.append(kwargs)
        return _nova_response(decision_status="DELAY", adjusted_size=0.0)

    monkeypatch.setattr(adapter, "fetch_nova_response", fake_fetch)
    result = adapter.evaluate_hyperliquid_decision_candidate(intent="trade", asset="ETH", size=10000)

    assert len(calls) == 1
    assert result["allowed_to_proceed"] is False
    assert result["authoritative_decision_status"] == "DELAY"
