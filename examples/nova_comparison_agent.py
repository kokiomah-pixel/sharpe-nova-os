"""Minimal side-by-side demo: decision flow without Nova vs with governed admission.

Defaults to a local Nova API for development safety.
Override with NOVA_API_URL and NOVA_API_KEY when targeting another environment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import requests


# Default to local API for immediate usability
DEFAULT_API_URL = "http://127.0.0.1:8000"

# Allow override via environment variable
API_URL = os.getenv("NOVA_API_URL", DEFAULT_API_URL)

API_KEY = os.getenv("NOVA_API_KEY", "mytestkey")


@dataclass(frozen=True)
class Scenario:
    intent: str
    asset: str
    size: float


def run_without_nova(scenario: Scenario) -> Dict[str, str]:
    return {
        "decision": "EXECUTE",
        "result": f"{scenario.intent} executes at full size ({scenario.size:g})",
    }


def call_nova(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        res = requests.get(
            f"{API_URL}/v1/context",
            headers={"Authorization": f"Bearer {API_KEY}"},
            params=params,
            timeout=20,
        )

        if res.status_code == 403:
            raise RuntimeError(
                "Nova API returned 403.\n\n"
                "If using the hosted endpoint, ensure your API key is valid.\n"
                "For local testing, run the API locally and set:\n\n"
                "NOVA_API_URL=http://127.0.0.1:8000\n"
                "NOVA_API_KEY=mytestkey\n"
            )

        res.raise_for_status()
        return res.json()

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Unable to reach Nova API.\n\n"
            "Start the local server:\n"
            "NOVA_API_KEY=mytestkey ./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000\n"
        ) from exc


def fetch_nova_context(scenario: Scenario) -> Dict[str, Any]:
    params = {
        "intent": scenario.intent,
        "asset": scenario.asset,
        "size": scenario.size,
    }
    return call_nova(params)


def fetch_nova_proof(decision_id: str) -> Dict[str, Any]:
    endpoint = f"{API_URL.rstrip('/')}/v1/proof/{decision_id}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(endpoint, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def is_risk_increasing_intent(intent: str) -> bool:
    return intent in {"trade", "deploy_liquidity", "open_position", "increase_position"}


def run_with_nova(scenario: Scenario) -> Dict[str, Any]:
    context = fetch_nova_context(scenario)
    proof = fetch_nova_proof(context["decision_id"])

    regime = context.get("regime", "Unknown")
    action_policy = context.get("guardrail", {}).get("action_policy", {})
    decision = context.get("decision_status", "ALLOW")
    impact_on_outcomes = context.get("impact_on_outcomes", {})
    # decision_status and constraint_effect define authority; impact_on_outcomes
    # remains supporting detail for validated exposure reporting.
    executed_size = impact_on_outcomes.get("adjusted_size", scenario.size)
    constraint_effect = proof.get("constraint_effect", {})
    intervention_type = proof.get("intervention_type")
    failure_class = proof.get("failure_class")

    decision_context = {
        "intent": scenario.intent,
        "asset": scenario.asset,
        "requested_size": scenario.size,
        "configured_decision_regime": regime,
        "timestamp_utc": context.get("timestamp_utc"),
        "decision_id": context.get("decision_id"),
        "system_state": context.get("system_state"),
    }
    validated_exposure = {
        "requested_size": scenario.size,
        "validated_size": executed_size,
    }

    return {
        "decision_context": decision_context,
        "action_policy": action_policy,
        "validated_exposure": validated_exposure,
        "decision_status": decision,
        "executed_size": executed_size,
        "constraint_effect": constraint_effect,
        "intervention_type": intervention_type,
        "failure_class": failure_class,
        "raw_action_policy": json.dumps(action_policy, indent=2, sort_keys=True),
    }


def print_scenario_comparison(scenario: Scenario) -> Dict[str, Any]:
    print("=" * 60)
    print("Scenario: Allocation decision under changing conditions")
    print(f"Input: {scenario.intent} | {scenario.asset} | {scenario.size:g}")
    print()

    without_nova = run_without_nova(scenario)
    print("WITHOUT NOVA:")
    print("Decision executed directly.")
    print("No constraint validation.")
    print("No historical reference.")
    print("No consistency enforcement.")
    print("Decision quality depends entirely on local logic.")
    print()

    print("WITH NOVA:")
    try:
        with_nova = run_with_nova(scenario)
        print(f"Decision Context: {json.dumps(with_nova['decision_context'], sort_keys=True)}")
        print(f"Action Policy: {json.dumps(with_nova['action_policy'], sort_keys=True)}")
        print(f"Validated Exposure: {json.dumps(with_nova['validated_exposure'], sort_keys=True)}")
        print(f"Decision Status: {with_nova['decision_status']}")
        print(f"Constraint Effect: {json.dumps(with_nova['constraint_effect'], sort_keys=True)}")
        print(f"Intervention Type: {with_nova['intervention_type']}")
        print(f"Failure Class: {with_nova['failure_class']}")
    except Exception as exc:
        # Surface transport failures honestly rather than implying Nova constrained the action.
        with_nova = {
            "decision_status": "UNAVAILABLE",
            "executed_size": scenario.size,
            "decision_context": {"status": "unavailable"},
            "action_policy": {"status": "unavailable"},
            "validated_exposure": {"requested_size": scenario.size, "validated_size": scenario.size},
            "constraint_effect": {"status": "unavailable"},
            "intervention_type": f"Failed to fetch Nova proof ({exc})",
            "failure_class": "unavailable",
        }
        print(f"Decision Context: {json.dumps(with_nova['decision_context'], sort_keys=True)}")
        print(f"Action Policy: {json.dumps(with_nova['action_policy'], sort_keys=True)}")
        print(f"Validated Exposure: {json.dumps(with_nova['validated_exposure'], sort_keys=True)}")
        print(f"Decision Status: {with_nova['decision_status']}")
        print(f"Constraint Effect: {json.dumps(with_nova['constraint_effect'], sort_keys=True)}")
        print(f"Intervention Type: {with_nova['intervention_type']}")
        print(f"Failure Class: {with_nova['failure_class']}")

    print()
    print("---")
    print("Comparison:")
    print("Without Nova -> decision evaluated in isolation")
    if with_nova["decision_status"] == "UNAVAILABLE":
        print("With Nova -> decision context unavailable, so no constraint claim can be made")
    else:
        print("With Nova -> decision evaluated under consistent constraints")
    print()
    print("Implication:")
    print("Without Nova -> decision quality is inconsistent")
    if with_nova["decision_status"] == "UNAVAILABLE":
        print("With Nova -> integration path is unavailable and should be fixed before use")
    else:
        print("With Nova -> decision quality is standardized")
    print()
    print("Nova conditions whether capital is allowed to move before execution.")

    print("=" * 60)
    return {
        "without_nova_decision": without_nova["decision"],
        "with_nova_decision": with_nova["decision_status"],
        "requested_size": scenario.size,
        "executed_size_without_nova": scenario.size,
        "executed_size_with_nova": with_nova.get("executed_size", 0.0),
    }


def main() -> None:
    print(f"Using Nova API: {API_URL}")
    print()

    scenarios: List[Scenario] = [
        Scenario("trade", "ETH", 10000),
        Scenario("trade", "BTC", 50000),
        Scenario("deploy_liquidity", "ETH", 20000),
        Scenario("trade", "ETH", 500),
    ]

    without_nova_execute_count = 0
    with_nova_counts = {"ALLOW": 0, "CONSTRAIN": 0, "VETO": 0}
    changed_behavior_count = 0
    validated_behavior_count = 0
    total_requested = 0.0
    total_executed_without_nova = 0.0
    total_executed_with_nova = 0.0

    for scenario in scenarios:
        decisions = print_scenario_comparison(scenario)
        if decisions["without_nova_decision"] == "EXECUTE":
            without_nova_execute_count += 1

        with_decision = decisions["with_nova_decision"]
        if with_decision in with_nova_counts:
            with_nova_counts[with_decision] += 1

        if with_decision in {"CONSTRAIN", "VETO"}:
            changed_behavior_count += 1
        if with_decision == "ALLOW":
            validated_behavior_count += 1

        total_requested += decisions["requested_size"]
        total_executed_without_nova += decisions["executed_size_without_nova"]
        total_executed_with_nova += decisions["executed_size_with_nova"]

        print()

    n = len(scenarios)
    print("SUMMARY")
    print()
    print("Without Nova:")
    print(f"- {without_nova_execute_count}/{n} scenarios executed at full size")
    print(f"- Total requested size: {total_requested:g}")
    print(f"- Total executed size: {total_executed_without_nova:g}")
    print()
    print("With Nova:")
    print(f"- {with_nova_counts['ALLOW']} ALLOW")
    print(f"- {with_nova_counts['CONSTRAIN']} CONSTRAIN")
    print(f"- {with_nova_counts['VETO']} VETO")
    print(f"- Modified execution in {changed_behavior_count}/{n} scenarios")
    print(f"- Validated execution in {validated_behavior_count}/{n} scenarios")
    print(f"- Total executed size: {total_executed_with_nova:g}")
    print()
    print("Conclusion:")
    print(f"Nova changed execution behavior in {changed_behavior_count}/{n} scenarios.")
    print(f"Nova validated execution in {validated_behavior_count}/{n} scenarios.")


if __name__ == "__main__":
    main()
