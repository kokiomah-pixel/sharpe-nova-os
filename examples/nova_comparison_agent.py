"""Minimal side-by-side demo: agent without Nova vs with Nova guardrails."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx


NOVA_API_URL = os.getenv("NOVA_API_URL", "https://nova-api-ipz6.onrender.com")
NOVA_API_KEY = os.getenv("NOVA_API_KEY", "your_api_key_here")


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


def fetch_nova_context(scenario: Scenario) -> Dict[str, Any]:
    endpoint = f"{NOVA_API_URL.rstrip('/')}/v1/context"
    params = {
        "intent": scenario.intent,
        "asset": scenario.asset,
        "size": scenario.size,
    }
    headers = {"Authorization": f"Bearer {NOVA_API_KEY}"}

    with httpx.Client(timeout=20.0) as client:
        response = client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def is_risk_increasing_intent(intent: str) -> bool:
    return intent in {"trade", "deploy_liquidity", "open_position", "increase_position"}


def run_with_nova(scenario: Scenario) -> Dict[str, Any]:
    context = fetch_nova_context(scenario)

    regime = context.get("regime", "Unknown")
    action_policy = context.get("guardrail", {}).get("action_policy", {})
    memory_context = context.get("memory_context", {})

    allow_new_risk = bool(action_policy.get("allow_new_risk", False))
    allow_position_increase = bool(action_policy.get("allow_position_increase", False))

    if not allow_new_risk and is_risk_increasing_intent(scenario.intent):
        decision = "VETO"
        executed_size = 0.0
        reason = "new risk not allowed"
        recommendation = "Do not initiate new risk. Reduce or exit existing exposure."
    elif not allow_position_increase and is_risk_increasing_intent(scenario.intent):
        executed_size = max(scenario.size * 0.5, 1)
        decision = "CONSTRAIN"
        reason = "position increase blocked"
        recommendation = "Constrain exposure size and avoid position increases."
    else:
        executed_size = scenario.size
        decision = "ALLOW"
        reason = "execution validated"
        recommendation = "Proceed under local controls."

    decision_context = {
        "intent": scenario.intent,
        "asset": scenario.asset,
        "requested_size": scenario.size,
        "configured_decision_regime": regime,
        "timestamp_utc": context.get("timestamp_utc"),
    }
    constraint_analysis = {
        "action_policy": action_policy,
        "reason": reason,
    }
    impact_on_outcomes = {
        "requested_size": scenario.size,
        "executed_size": executed_size,
    }

    return {
        "decision_context": decision_context,
        "constraint_analysis": constraint_analysis,
        "historical_reference": memory_context,
        "impact_on_outcomes": impact_on_outcomes,
        "recommendation": recommendation,
        "decision_status": decision,
        "executed_size": executed_size,
        "reason": reason,
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
        print(f"Constraint Analysis: {json.dumps(with_nova['constraint_analysis'], sort_keys=True)}")
        print(f"Historical Reference: {json.dumps(with_nova['historical_reference'], sort_keys=True)}")
        print(f"Impact on Outcomes: {json.dumps(with_nova['impact_on_outcomes'], sort_keys=True)}")
        print(f"Recommendation: {with_nova['recommendation']}")
        print(f"Decision Status: {with_nova['decision_status']}")
    except Exception as exc:
        # Fail-safe behavior is explicit so demo output stays understandable.
        with_nova = {
            "decision_status": "VETO",
            "executed_size": 0.0,
            "reason": f"Nova context unavailable ({exc})",
            "decision_context": {"status": "unavailable"},
            "constraint_analysis": {"status": "unavailable"},
            "historical_reference": {"status": "unavailable"},
            "impact_on_outcomes": {"requested_size": scenario.size, "executed_size": 0.0},
            "recommendation": f"Failed to fetch Nova context ({exc})",
        }
        print(f"Decision Context: {json.dumps(with_nova['decision_context'], sort_keys=True)}")
        print(f"Constraint Analysis: {json.dumps(with_nova['constraint_analysis'], sort_keys=True)}")
        print(f"Historical Reference: {json.dumps(with_nova['historical_reference'], sort_keys=True)}")
        print(f"Impact on Outcomes: {json.dumps(with_nova['impact_on_outcomes'], sort_keys=True)}")
        print(f"Recommendation: {with_nova['recommendation']}")
        print(f"Decision Status: {with_nova['decision_status']}")

    print()
    print("---")
    print("Comparison:")
    print("Without Nova -> decision evaluated in isolation")
    print("With Nova -> decision evaluated under consistent constraints")
    print()
    print("Implication:")
    print("Without Nova -> decision quality is inconsistent")
    print("With Nova -> decision quality is standardized")
    print()
    print("Nova does not change the decision.")
    print("It changes how the decision is made.")

    print("=" * 60)
    return {
        "without_nova_decision": without_nova["decision"],
        "with_nova_decision": with_nova["decision_status"],
        "requested_size": scenario.size,
        "executed_size_without_nova": scenario.size,
        "executed_size_with_nova": with_nova.get("executed_size", 0.0),
    }


def main() -> None:
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
