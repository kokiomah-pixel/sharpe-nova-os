"""Sequential production-discipline harness for Nova's current API surface.

This script does not pretend unsupported admission artifacts exist.
It pressure-tests the live /v1/context interface, records what Nova
actually returns, and flags where production integrity requirements are
not yet met.
"""

# NOTE:
# This harness inspects full constraint surfaces.
# External integrations must bind only to primary decision fields.

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx


DEFAULT_API_URL = os.getenv("NOVA_API_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.getenv("NOVA_API_KEY", "mytestkey")
DEFAULT_OUTPUT = "nova_production_integrity_report.json"
DEFAULT_KEY_PLAN_JSON = os.getenv("NOVA_HARNESS_KEY_PLAN_JSON", "")

DECISION_STATUS_MAP = {
    "ALLOW": "Allowed",
    "CONSTRAIN": "Constrained",
    "VETO": "Rejected",
}


@dataclass
class RequestSpec:
    path: str = "/v1/context"
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    api_key: Optional[str] = None
    pre_request_delay_seconds: float = 0.0


@dataclass
class TestResult:
    id: str
    title: str
    wave: str
    outcome: str
    normalized_status: str
    http_status: Optional[int]
    request_count: int
    checks: Dict[str, bool]
    observations: List[str]
    gaps: List[str]
    artifacts: Dict[str, bool]
    requests: List[Dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Nova production integrity tests.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Base URL for Nova API.")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for Nova.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to JSON report.")
    parser.add_argument(
        "--key-plan-json",
        default=DEFAULT_KEY_PLAN_JSON,
        help="Optional JSON map assigning isolated API keys per test id or batch label.",
    )
    return parser.parse_args()


def normalize_status(http_status: Optional[int], payload: Optional[Dict[str, Any]]) -> str:
    if payload and payload.get("decision_status") in DECISION_STATUS_MAP:
        return DECISION_STATUS_MAP[payload["decision_status"]]
    if http_status is not None and 400 <= http_status < 500:
        return "Rejected"
    if http_status is not None and http_status >= 500:
        return "Error"
    return "Unknown"


def build_artifact_flags(payload: Optional[Dict[str, Any]], normalized_status: str) -> Dict[str, bool]:
    payload = payload or {}
    decision_admission_record = all(
        key in payload for key in ("decision_context", "timestamp_utc", "signature")
    )
    constraint_trace = False
    if normalized_status in {"Constrained", "Rejected"}:
        constraint_trace = bool(
            payload.get("constraint_analysis")
            and payload.get("impact_on_outcomes")
            and (payload.get("adjustment") or payload.get("reflex_memory", {}).get("proof"))
        )

    # These artifacts do not exist in the current API unless explicit fields appear.
    rejection_ledger_entry = bool(payload.get("rejection_ledger") or payload.get("rejection_record"))
    exception_register_entry = bool(payload.get("exception_register") or payload.get("exceptions"))

    return {
        "decision_admission_record": decision_admission_record,
        "constraint_trace": constraint_trace,
        "rejection_ledger_entry": rejection_ledger_entry,
        "exception_register_entry": exception_register_entry,
    }


def flow_is_preserved(payload: Optional[Dict[str, Any]]) -> bool:
    if not payload:
        return False
    return bool(
        payload.get("decision_context")
        and payload.get("constraint_analysis")
        and payload.get("impact_on_outcomes")
    )


def payload_has_domain_signal(payload: Optional[Dict[str, Any]], terms: List[str]) -> bool:
    if not payload:
        return False
    haystacks = [
        json.dumps(payload.get("constraint_trace", {}), sort_keys=True).lower(),
        json.dumps(payload.get("constraint_analysis", {}), sort_keys=True).lower(),
        json.dumps(payload.get("historical_reference", {}), sort_keys=True).lower(),
        json.dumps(payload.get("memory_context", {}), sort_keys=True).lower(),
        json.dumps(payload.get("reflex_memory", {}), sort_keys=True).lower(),
        str(payload.get("adjustment", "")).lower(),
    ]
    return any(term.lower() in hay for hay in haystacks for term in terms)


def payload_drifts_outcome_first(payload: Optional[Dict[str, Any]]) -> bool:
    if not payload:
        return False
    text = json.dumps(payload, sort_keys=True).lower()
    banned = ["performs best", "sharpe", "returns", "market upside", "best trade"]
    return any(term in text for term in banned)


def request_once(
    client: httpx.Client,
    api_url: str,
    api_key: str,
    spec: RequestSpec,
) -> Dict[str, Any]:
    endpoint = f"{api_url.rstrip('/')}{spec.path}"
    resolved_api_key = spec.api_key or api_key
    headers = {"Authorization": f"Bearer {resolved_api_key}"}
    if spec.pre_request_delay_seconds > 0:
        time.sleep(spec.pre_request_delay_seconds)
    started = time.perf_counter()
    try:
        response = client.get(endpoint, params=spec.params, headers=headers)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            payload = response.json()
        except Exception:
            payload = None
        return {
            "request": asdict(spec),
            "api_key_used": resolved_api_key,
            "http_status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "payload": payload,
            "body_preview": response.text[:500],
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "request": asdict(spec),
            "api_key_used": resolved_api_key,
            "http_status": None,
            "elapsed_ms": elapsed_ms,
            "payload": None,
            "body_preview": "",
            "transport_error": str(exc),
        }


def summarize_primary(result: Dict[str, Any]) -> Tuple[str, Dict[str, bool]]:
    payload = result.get("payload")
    http_status = result.get("http_status")
    normalized_status = normalize_status(http_status, payload)
    artifacts = build_artifact_flags(payload, normalized_status)
    return normalized_status, artifacts


def make_request_record(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = result.get("payload") or {}
    return {
        "description": result["request"]["description"],
        "api_key_used": result.get("api_key_used"),
        "params": result["request"]["params"],
        "http_status": result.get("http_status"),
        "elapsed_ms": result.get("elapsed_ms"),
        "normalized_status": normalize_status(result.get("http_status"), result.get("payload")),
        "decision_status": payload.get("decision_status"),
        "adjustment": payload.get("adjustment"),
        "constraint_trace": payload.get("constraint_trace"),
        "constraint_analysis": payload.get("constraint_analysis"),
        "impact_on_outcomes": payload.get("impact_on_outcomes"),
        "body_preview": result.get("body_preview"),
        "transport_error": result.get("transport_error"),
    }


def _clean_telemetry_params() -> Dict[str, Any]:
    return {
        "telemetry_age_seconds": 10,
        "telemetry_reliability": 0.95,
        "telemetry_source_scores": "book:0.96,oi:0.94",
    }


def with_clean_telemetry(params: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(_clean_telemetry_params())
    merged.update(params)
    return merged


def parse_key_plan(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid --key-plan-json payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("--key-plan-json must decode to an object.")
    return parsed


def resolve_case_key(
    key_plan: Dict[str, Any],
    label: str,
    default_api_key: str,
    *,
    index: int = 0,
) -> str:
    configured = key_plan.get(label)
    if isinstance(configured, list):
        if 0 <= index < len(configured):
            candidate = configured[index]
        else:
            candidate = configured[-1] if configured else default_api_key
        return str(candidate or default_api_key)
    if configured:
        return str(configured)
    return default_api_key


def sequence_delay_seconds(keys: List[str]) -> float:
    unique_keys = {key for key in keys if key}
    return 46.0 if len(unique_keys) <= 1 else 0.0


def evaluate_test_01(primary: Dict[str, Any]) -> TestResult:
    payload = primary.get("payload")
    normalized_status, artifacts = summarize_primary(primary)
    checks = {
        "allowed_possible": normalized_status == "Allowed",
        "record_created": artifacts["decision_admission_record"],
        "flow_preserved": flow_is_preserved(payload),
    }
    observations = []
    gaps = []
    if checks["allowed_possible"]:
        observations.append("Nova admitted the baseline request without forcing a constraint.")
    else:
        gaps.append("Healthy baseline did not resolve to Allowed.")
    if checks["record_created"]:
        observations.append("Decision Admission Record surface is present via decision_context/timestamp/signature.")
    else:
        gaps.append("Decision Admission Record surface is incomplete.")
    if not checks["flow_preserved"]:
        gaps.append("Decision -> Constraint -> Outcome structure is incomplete.")
    outcome = "PASS" if all(checks.values()) else "FAIL"
    return TestResult(
        id="TEST 01",
        title="Healthy Baseline Admission",
        wave="Wave 1 — Baseline Integrity",
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=primary.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(primary)],
    )


def evaluate_test_02(primary: Dict[str, Any]) -> TestResult:
    payload = primary.get("payload")
    normalized_status, artifacts = summarize_primary(primary)
    checks = {
        "rejected": normalized_status == "Rejected",
        "rejection_ledger_entry": artifacts["rejection_ledger_entry"],
        "no_silent_field_inference": not (
            payload and payload.get("decision_context", {}).get("requested_size") is not None
        ),
    }
    observations = []
    gaps = []
    if not checks["rejected"]:
        gaps.append("Incomplete decision was not rejected.")
    if not checks["rejection_ledger_entry"]:
        gaps.append("No explicit Rejection Ledger entry was returned.")
    if checks["no_silent_field_inference"]:
        observations.append("Missing size was not silently filled in by the API.")
    outcome = "PASS" if all(checks.values()) else "FAIL"
    return TestResult(
        id="TEST 02",
        title="Missing Field Rejection",
        wave="Wave 1 — Baseline Integrity",
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=primary.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(primary)],
    )


def evaluate_test_03(primary: Dict[str, Any]) -> TestResult:
    normalized_status, artifacts = summarize_primary(primary)
    payload = primary.get("payload") or {}
    body_preview = primary.get("body_preview", "").lower()
    checks = {
        "rejected_or_returned_for_correction": normalized_status == "Rejected",
        "explicit_ambiguity_flag": (
            payload.get("constraint_analysis", {}).get("constraint_category") == "ambiguous_constraint_language"
            or "ambigu" in body_preview
            or "valid number" in body_preview
        ),
    }
    observations = []
    gaps = []
    if checks["rejected_or_returned_for_correction"]:
        observations.append("Vague size language was not admitted.")
    else:
        gaps.append("Ambiguous language was not rejected.")
    if not checks["explicit_ambiguity_flag"]:
        gaps.append("No explicit ambiguity flag was surfaced.")
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["rejected_or_returned_for_correction"] else "FAIL"
    return TestResult(
        id="TEST 03",
        title="Ambiguous Language Rejection",
        wave="Wave 1 — Baseline Integrity",
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=primary.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(primary)],
    )


def evaluate_test_04(primary: Dict[str, Any]) -> TestResult:
    payload = primary.get("payload") or {}
    normalized_status, artifacts = summarize_primary(primary)
    impact = payload.get("impact_on_outcomes", {})
    requested_size = impact.get("requested_size")
    adjusted_size = impact.get("adjusted_size")
    checks = {
        "constrained": normalized_status == "Constrained",
        "adjusted_size_recorded": adjusted_size is not None and requested_size is not None and adjusted_size < requested_size,
        "constraint_trace_present": artifacts["constraint_trace"],
    }
    observations = []
    gaps = []
    if checks["constrained"]:
        observations.append("Nova applied non-binary constraint logic.")
    else:
        gaps.append("Moderate breach did not resolve to Constrained.")
    if not checks["adjusted_size_recorded"]:
        gaps.append("Adjusted size was not recorded correctly.")
    if not checks["constraint_trace_present"]:
        gaps.append("Constraint Trace is incomplete or absent.")
    outcome = "PASS" if all(checks.values()) else "FAIL"
    return TestResult(
        id="TEST 04",
        title="Constrained Admission",
        wave="Wave 1 — Baseline Integrity",
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=primary.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(primary)],
    )


def evaluate_domain_test(
    primary: Dict[str, Any],
    test_id: str,
    title: str,
    wave: str,
    acceptable_statuses: List[str],
    domain_terms: List[str],
    bypass_expected: bool = False,
    require_exception: bool = False,
) -> TestResult:
    normalized_status, artifacts = summarize_primary(primary)
    payload = primary.get("payload")
    checks = {
        "status_adjusted": normalized_status in acceptable_statuses,
        "domain_signal_visible": payload_has_domain_signal(payload, domain_terms),
        "constraint_trace_present": artifacts["constraint_trace"] if normalized_status in {"Constrained", "Rejected"} else True,
    }
    observations = []
    gaps = []
    if checks["status_adjusted"]:
        observations.append(f"Nova returned {normalized_status} under the tested pressure case.")
    else:
        gaps.append(f"Expected status in {acceptable_statuses}, got {normalized_status}.")
    if not checks["domain_signal_visible"]:
        gaps.append("No explicit domain-specific signal was surfaced.")
    if not checks["constraint_trace_present"]:
        gaps.append("Constraint Trace is missing for constrained or rejected output.")
    if bypass_expected and normalized_status in {"Constrained", "Rejected"}:
        observations.append("Bypass attempt did not unlock an execution path.")
    if require_exception and not artifacts["exception_register_entry"]:
        gaps.append("No Exception Register entry was returned.")
    if require_exception:
        checks["exception_register_entry"] = artifacts["exception_register_entry"]
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["status_adjusted"] else "FAIL"
    return TestResult(
        id=test_id,
        title=title,
        wave=wave,
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=primary.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(primary)],
    )


def evaluate_test_09(results: List[Dict[str, Any]]) -> TestResult:
    records = [make_request_record(item) for item in results]
    payloads = [item.get("payload") or {} for item in results]
    statuses = [normalize_status(item.get("http_status"), item.get("payload")) for item in results]
    prior_reference_visible = any(
        "prior" in json.dumps(payload.get("constraint_analysis", {})).lower()
        or "previous" in json.dumps(payload.get("constraint_analysis", {})).lower()
        for payload in payloads
    )
    checks = {
        "later_decisions_adjusted": any(status in {"Constrained", "Rejected"} for status in statuses[1:]),
        "prior_decisions_referenced": prior_reference_visible,
    }
    observations = []
    gaps = []
    if checks["later_decisions_adjusted"]:
        observations.append("Later decisions were still subject to Nova constraints.")
    else:
        gaps.append("Later decisions were not adjusted under cross-decision pressure.")
    if not checks["prior_decisions_referenced"]:
        gaps.append("No prior-decision reference surfaced in later responses.")
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["later_decisions_adjusted"] else "FAIL"
    return TestResult(
        id="TEST 09",
        title="Cross-Decision Pressure",
        wave="Wave 2 — Constraint & Reflex Pressure",
        outcome=outcome,
        normalized_status=statuses[-1],
        http_status=results[-1].get("http_status"),
        request_count=len(results),
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=build_artifact_flags(results[-1].get("payload"), statuses[-1]),
        requests=records,
    )


def evaluate_test_13(results: List[Dict[str, Any]]) -> TestResult:
    records = [make_request_record(item) for item in results]
    payloads = [item.get("payload") or {} for item in results]
    statuses = [normalize_status(item.get("http_status"), item.get("payload")) for item in results]
    pattern_visible = any(
        "pattern" in json.dumps(payload).lower() or "escalat" in json.dumps(payload).lower()
        for payload in payloads
    )
    consistent_rejection = all(status == "Rejected" for status in statuses)
    checks = {
        "rejection_remains_consistent": consistent_rejection,
        "pattern_flagged": pattern_visible,
    }
    observations = []
    gaps = []
    if checks["rejection_remains_consistent"]:
        observations.append("Rejected decision stayed rejected across repeated submissions.")
    else:
        gaps.append("Repeated rejected decision did not remain consistently rejected.")
    if not checks["pattern_flagged"]:
        gaps.append("No repeated-rejection pattern or escalation signal was returned.")
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["rejection_remains_consistent"] else "FAIL"
    return TestResult(
        id="TEST 13",
        title="Repeated Rejection Pattern",
        wave="Wave 3 — System Integrity & Anti-Bypass",
        outcome=outcome,
        normalized_status=statuses[-1],
        http_status=results[-1].get("http_status"),
        request_count=len(results),
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=build_artifact_flags(results[-1].get("payload"), statuses[-1]),
        requests=records,
    )


def evaluate_test_14(results: List[Dict[str, Any]]) -> TestResult:
    records = [make_request_record(item) for item in results]
    payloads = [item.get("payload") or {} for item in results]
    statuses = [normalize_status(item.get("http_status"), item.get("payload")) for item in results]
    signatures = [payload.get("signature") for payload in payloads if payload]
    checks = {
        "independent_results_present": len(set(statuses)) >= 2,
        "no_cross_contamination_visible": len(signatures) == len([payload for payload in payloads if payload]),
    }
    observations = []
    gaps = []
    if checks["independent_results_present"]:
        observations.append("Mixed batch scenarios produced independent outcomes.")
    else:
        gaps.append("Mixed batch did not show differentiated outcomes.")
    if not checks["no_cross_contamination_visible"]:
        gaps.append("Some mixed batch results were missing per-decision records.")
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["independent_results_present"] else "FAIL"
    return TestResult(
        id="TEST 14",
        title="Mixed Batch",
        wave="Wave 3 — System Integrity & Anti-Bypass",
        outcome=outcome,
        normalized_status=statuses[-1],
        http_status=results[-1].get("http_status"),
        request_count=len(results),
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=build_artifact_flags(results[-1].get("payload"), statuses[-1]),
        requests=records,
    )


def evaluate_test_15(source_result: Dict[str, Any]) -> TestResult:
    payload = source_result.get("payload") or {}
    normalized_status, artifacts = summarize_primary(source_result)
    proof = payload.get("reflex_memory", {}).get("proof") or {}
    proof_text = json.dumps(proof, sort_keys=True).lower()
    checks = {
        "proof_surface_present": bool(proof),
        "prevented_exposure_framing": "failure_class" in proof and "why_intervention_happened" in proof,
        "no_outcome_first_drift": not payload_drifts_outcome_first(payload),
    }
    observations = []
    gaps = []
    if checks["proof_surface_present"]:
        observations.append("Reflex proof surface is available from the constrained or rejected case.")
    else:
        gaps.append("No prevented-outcome proof surface was returned.")
    if checks["prevented_exposure_framing"]:
        observations.append("Proof language stays focused on intervention and failure class.")
    else:
        gaps.append("Proof surface does not clearly frame prevented exposure.")
    if not checks["no_outcome_first_drift"]:
        gaps.append("Proof surface drifted into outcome-first language.")
    outcome = "PASS" if all(checks.values()) else "PARTIAL" if checks["proof_surface_present"] else "FAIL"
    return TestResult(
        id="TEST 15",
        title="Prevented Outcome Report",
        wave="Wave 3 — System Integrity & Anti-Bypass",
        outcome=outcome,
        normalized_status=normalized_status,
        http_status=source_result.get("http_status"),
        request_count=1,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=artifacts,
        requests=[make_request_record(source_result)],
    )


def evaluate_test_17(all_results: List[TestResult]) -> TestResult:
    missing_constraints = [result.id for result in all_results if result.normalized_status in {"Constrained", "Rejected"} and not result.artifacts.get("constraint_trace")]
    missing_rejection_ledgers = [result.id for result in all_results if result.normalized_status == "Rejected" and not result.artifacts.get("rejection_ledger_entry")]
    missing_exceptions = [result.id for result in all_results if any("Exception Register entry" in gap for gap in result.gaps)]
    checks = {
        "full_chain_visible": len(missing_constraints) == 0 and len(missing_rejection_ledgers) == 0,
        "missing_items_surfaced": True,
    }
    observations = [
        f"Missing constraint traces: {missing_constraints or 'none'}",
        f"Missing rejection ledger entries: {missing_rejection_ledgers or 'none'}",
        f"Missing exception register entries: {missing_exceptions or 'none'}",
    ]
    gaps = []
    if missing_rejection_ledgers:
        gaps.append("Rejection ledger coverage is incomplete.")
    if missing_exceptions:
        gaps.append("Exception register coverage is incomplete.")
    outcome = "PASS" if not gaps else "PARTIAL"
    return TestResult(
        id="TEST 17",
        title="Audit Chain Review",
        wave="Wave 3 — System Integrity & Anti-Bypass",
        outcome=outcome,
        normalized_status="Audit",
        http_status=None,
        request_count=0,
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts={},
        requests=[],
    )


def evaluate_test_18(results: List[Dict[str, Any]]) -> TestResult:
    records = [make_request_record(item) for item in results]
    payloads = [item.get("payload") or {} for item in results]
    halt_visible = any("halt" in json.dumps(payload).lower() for payload in payloads)
    exception_visible = any(
        build_artifact_flags(item.get("payload"), normalize_status(item.get("http_status"), item.get("payload"))).get("exception_register_entry")
        for item in results
    )
    checks = {
        "integrity_degradation_flagged": halt_visible or exception_visible,
        "halt_recommendation_or_state": halt_visible,
    }
    observations = []
    gaps = []
    if not checks["integrity_degradation_flagged"]:
        gaps.append("Combined integrity-stress scenario produced no degradation signal.")
    if not checks["halt_recommendation_or_state"]:
        gaps.append("No halt recommendation or halt state surfaced.")
    outcome = "PASS" if all(checks.values()) else "FAIL"
    return TestResult(
        id="TEST 18",
        title="Halt Trigger Scenario",
        wave="Wave 3 — System Integrity & Anti-Bypass",
        outcome=outcome,
        normalized_status=normalize_status(results[-1].get("http_status"), results[-1].get("payload")),
        http_status=results[-1].get("http_status"),
        request_count=len(results),
        checks=checks,
        observations=observations,
        gaps=gaps,
        artifacts=build_artifact_flags(results[-1].get("payload"), normalize_status(results[-1].get("http_status"), results[-1].get("payload"))),
        requests=records,
    )


def run_suite(api_url: str, api_key: str, key_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key_plan = key_plan or {}
    with httpx.Client(timeout=20.0) as client:
        results: List[TestResult] = []

        # Wave 1
        test_01 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "reduce_position", "asset": "ETH", "size": 1000, "venue": "kraken", "strategy": "rebalance"}
            ),
            description="Healthy baseline admission",
            api_key=resolve_case_key(key_plan, "TEST 01", api_key),
        ))
        results.append(evaluate_test_01(test_01))

        test_02 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "venue": "kraken", "strategy": "core_allocation"}
            ),
            description="Missing field rejection",
            api_key=resolve_case_key(key_plan, "TEST 02", api_key),
        ))
        results.append(evaluate_test_02(test_02))

        test_03 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": "small size", "strategy": "reasonable risk"}
            ),
            description="Ambiguous language rejection",
            api_key=resolve_case_key(key_plan, "TEST 03", api_key),
        ))
        results.append(evaluate_test_03(test_03))

        test_04 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 10000, "venue": "kraken", "strategy": "swing_entry"}
            ),
            description="Constrained admission",
            api_key=resolve_case_key(key_plan, "TEST 04", api_key),
        ))
        results.append(evaluate_test_04(test_04))

        test_05 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 500000, "venue": "thin_order_book", "strategy": "liquidity_stress"}
            ),
            description="Liquidity stress",
            api_key=resolve_case_key(key_plan, "TEST 05", api_key),
        ))
        results.append(evaluate_domain_test(
            test_05,
            "TEST 05",
            "Liquidity Stress",
            "Wave 1 — Baseline Integrity",
            ["Constrained", "Rejected"],
            ["liquidity", "slippage", "execution", "fragility"],
        ))

        # Wave 2
        test_06 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "increase_position", "asset": "USDC", "size": 20000, "strategy": "peg_instability"}
            ),
            description="Stablecoin defense",
            api_key=resolve_case_key(key_plan, "TEST 06", api_key),
        ))
        results.append(evaluate_domain_test(
            test_06,
            "TEST 06",
            "Stablecoin Defense",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Constrained", "Rejected"],
            ["stablecoin", "depeg", "peg"],
        ))

        test_07 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "increase_position", "asset": "stETH", "size": 20000, "strategy": "validator_uptime_drop"}
            ),
            description="Validator degradation",
            api_key=resolve_case_key(key_plan, "TEST 07", api_key),
        ))
        results.append(evaluate_domain_test(
            test_07,
            "TEST 07",
            "Validator Degradation",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Constrained", "Rejected"],
            ["validator", "slashing", "uptime"],
        ))

        test_08 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "increase_position", "asset": "LDO", "size": 20000, "strategy": "governance_attack"}
            ),
            description="Governance exploit",
            api_key=resolve_case_key(key_plan, "TEST 08", api_key),
        ))
        results.append(evaluate_domain_test(
            test_08,
            "TEST 08",
            "Governance Exploit",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Constrained", "Rejected"],
            ["governance", "exploit", "capture"],
        ))

        test_09_keys = [
            resolve_case_key(key_plan, "TEST 09", api_key, index=0),
            resolve_case_key(key_plan, "TEST 09", api_key, index=1),
            resolve_case_key(key_plan, "TEST 09", api_key, index=2),
        ]
        test_09_delay = sequence_delay_seconds(test_09_keys)
        test_09_requests = [
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 10000}),
                description="Cross-decision pressure step 1",
                api_key=test_09_keys[0],
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "BTC", "size": 10000}),
                description="Cross-decision pressure step 2",
                api_key=test_09_keys[1],
                pre_request_delay_seconds=test_09_delay,
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 20000}),
                description="Cross-decision pressure step 3",
                api_key=test_09_keys[2],
                pre_request_delay_seconds=test_09_delay,
            )),
        ]
        results.append(evaluate_test_09(test_09_requests))

        test_10 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 10000, "strategy": "macro_instability"}
            ),
            description="Macro shock",
            api_key=resolve_case_key(key_plan, "TEST 10", api_key),
        ))
        results.append(evaluate_domain_test(
            test_10,
            "TEST 10",
            "Macro Shock",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Constrained", "Rejected"],
            ["macro", "shock", "instability"],
        ))

        test_11 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 10000, "strategy": "retroactive_log_after_execution"}
            ),
            description="Retroactive logging",
            api_key=resolve_case_key(key_plan, "TEST 11", api_key),
        ))
        results.append(evaluate_domain_test(
            test_11,
            "TEST 11",
            "Retroactive Logging",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Rejected"],
            ["retroactive", "exception", "after execution"],
            require_exception=True,
        ))

        test_12 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 500000, "strategy": "override_rejected_decision"}
            ),
            description="Manual override",
            api_key=resolve_case_key(key_plan, "TEST 12", api_key),
        ))
        results.append(evaluate_domain_test(
            test_12,
            "TEST 12",
            "Manual Override",
            "Wave 2 — Constraint & Reflex Pressure",
            ["Rejected"],
            ["override", "exception"],
            require_exception=True,
        ))

        # Wave 3
        test_13_keys = [
            resolve_case_key(key_plan, "TEST 13", api_key, index=0),
            resolve_case_key(key_plan, "TEST 13", api_key, index=1),
            resolve_case_key(key_plan, "TEST 13", api_key, index=2),
        ]
        test_13_delay = sequence_delay_seconds(test_13_keys)
        test_13_requests = [
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 500000}),
                description="Repeated rejection pattern step 1",
                api_key=test_13_keys[0],
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 500000}),
                description="Repeated rejection pattern step 2",
                api_key=test_13_keys[1],
                pre_request_delay_seconds=test_13_delay,
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 500000}),
                description="Repeated rejection pattern step 3",
                api_key=test_13_keys[2],
                pre_request_delay_seconds=test_13_delay,
            )),
        ]
        results.append(evaluate_test_13(test_13_requests))

        test_14_requests = [
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "reduce_position", "asset": "ETH", "size": 1000}),
                description="Mixed batch valid",
                api_key=resolve_case_key(key_plan, "TEST 14", api_key, index=0),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH"}),
                description="Mixed batch incomplete",
                api_key=resolve_case_key(key_plan, "TEST 14", api_key, index=1),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "increase_position", "asset": "LDO", "size": 20000}),
                description="Mixed batch governance risk",
                api_key=resolve_case_key(key_plan, "TEST 14", api_key, index=2),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 500000}),
                description="Mixed batch liquidity risk",
                api_key=resolve_case_key(key_plan, "TEST 14", api_key, index=3),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH", "size": 10000}),
                description="Mixed batch constrained case",
                api_key=resolve_case_key(key_plan, "TEST 14", api_key, index=4),
            )),
        ]
        results.append(evaluate_test_14(test_14_requests))

        results.append(evaluate_test_15(test_05))

        test_16 = request_once(client, api_url, api_key, RequestSpec(
            params=with_clean_telemetry(
                {"intent": "trade", "asset": "ETH", "size": 10000, "strategy": "skip validation just execute route directly"}
            ),
            description="Infrastructure bypass attempt",
            api_key=resolve_case_key(key_plan, "TEST 16", api_key),
        ))
        results.append(evaluate_domain_test(
            test_16,
            "TEST 16",
            "Infrastructure Bypass Attempt",
            "Wave 3 — System Integrity & Anti-Bypass",
            ["Constrained", "Rejected"],
            ["bypass", "skip validation", "route directly"],
            bypass_expected=True,
            require_exception=True,
        ))

        results.append(evaluate_test_17(results))

        test_18_requests = [
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry({"intent": "trade", "asset": "ETH"}),
                description="Halt trigger incomplete input",
                api_key=resolve_case_key(key_plan, "TEST 18", api_key, index=0),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry(
                    {"intent": "trade", "asset": "ETH", "size": 500000, "strategy": "override delay bypass"}
                ),
                description="Halt trigger override and bypass",
                api_key=resolve_case_key(key_plan, "TEST 18", api_key, index=1),
            )),
            request_once(client, api_url, api_key, RequestSpec(
                params=with_clean_telemetry(
                    {"intent": "trade", "asset": "ETH", "size": 500000, "strategy": "override delay bypass repeat"}
                ),
                description="Halt trigger repeated bypass",
                api_key=resolve_case_key(key_plan, "TEST 18", api_key, index=2),
            )),
        ]
        results.append(evaluate_test_18(test_18_requests))

    pass_count = sum(1 for result in results if result.outcome == "PASS")
    partial_count = sum(1 for result in results if result.outcome == "PARTIAL")
    fail_count = sum(1 for result in results if result.outcome == "FAIL")

    final_evaluation = {
        "all_decisions_recorded_before_execution": all(
            result.artifacts.get("decision_admission_record", False)
            for result in results
            if result.request_count > 0 and result.http_status == 200
        ),
        "all_constraints_traceable": all(
            result.artifacts.get("constraint_trace", False)
            for result in results
            if result.normalized_status in {"Constrained", "Rejected"} and result.http_status == 200
        ),
        "all_rejections_logged": all(
            result.artifacts.get("rejection_ledger_entry", False)
            for result in results
            if result.normalized_status == "Rejected"
        ),
        "all_exceptions_visible": all(
            result.artifacts.get("exception_register_entry", False)
            for result in results
            if any("Exception Register entry" in gap for gap in result.gaps)
        ),
        "any_outcome_first_drift": any(
            payload_drifts_outcome_first(request.get("constraint_analysis"))
            for result in results
            for request in result.requests
        ),
        "bypass_attempts_resisted": any(
            result.id == "TEST 16" and result.normalized_status in {"Constrained", "Rejected"}
            for result in results
        ),
        "failures_exposed_not_hidden": any(result.outcome in {"FAIL", "PARTIAL"} for result in results),
    }

    return {
        "standard": "Decision -> Constraint -> Outcome",
        "api_url": api_url,
        "results": [asdict(result) for result in results],
        "summary": {
            "pass": pass_count,
            "partial": partial_count,
            "fail": fail_count,
        },
        "final_evaluation": final_evaluation,
    }


def print_console_report(report: Dict[str, Any]) -> None:
    print("NOVA PRODUCTION INTEGRITY TEST")
    print(f"API URL: {report['api_url']}")
    print()
    for result in report["results"]:
        print(f"{result['id']} | {result['outcome']} | {result['normalized_status']} | {result['title']}")
        for observation in result["observations"]:
            print(f"  + {observation}")
        for gap in result["gaps"]:
            print(f"  - {gap}")
        print()
    print("SUMMARY")
    print(f"  PASS: {report['summary']['pass']}")
    print(f"  PARTIAL: {report['summary']['partial']}")
    print(f"  FAIL: {report['summary']['fail']}")


def main() -> None:
    args = parse_args()
    key_plan = parse_key_plan(args.key_plan_json)
    report = run_suite(args.api_url, args.api_key, key_plan=key_plan)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print_console_report(report)
    print()
    print(f"Full report written to {output_path}")


if __name__ == "__main__":
    main()
