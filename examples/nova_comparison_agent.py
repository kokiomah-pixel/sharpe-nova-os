"""Minimal side-by-side demo: agent without Nova vs with Nova guardrails."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx


NOVA_API_URL = os.getenv("NOVA_API_URL", "https://nova-api-ipz6.onrender.com")
NOVA_API_KEY = os.getenv("NOVA_API_KEY", "nova_live_key_001")


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

    allow_new_risk = bool(action_policy.get("allow_new_risk", False))
    allow_position_increase = bool(action_policy.get("allow_position_increase", False))

    if not allow_new_risk and is_risk_increasing_intent(scenario.intent):
        decision = "VETO"
        executed_size = 0.0
        reason = "new risk not allowed"
        result = "Action blocked by Nova guardrail"
    elif not allow_position_increase and is_risk_increasing_intent(scenario.intent):
        executed_size = max(scenario.size * 0.5, 1)
        decision = "CONSTRAIN"
        reason = "position increase blocked"
        result = f"{scenario.intent} executes at reduced size ({executed_size:g} vs {scenario.size:g})"
    else:
        executed_size = scenario.size
        decision = "ALLOW"
        reason = "execution validated"
        result = f"{scenario.intent} executes at full size ({scenario.size:g})"

    return {
        "regime": regime,
        "action_policy": json.dumps(action_policy, indent=2, sort_keys=True),
        "decision": decision,
        "executed_size": executed_size,
        "reason": reason,
        "result": result,
    }


def print_scenario_comparison(scenario: Scenario) -> Dict[str, Any]:
    print("=" * 60)
    print(f"Scenario: {scenario.intent} | {scenario.asset} | {scenario.size:g}")
    print()

    without_nova = run_without_nova(scenario)
    print("WITHOUT NOVA")
    print(f"Decision: {without_nova['decision']}")
    print(f"Result: {without_nova['result']}")
    print()

    print("WITH NOVA")
    try:
        with_nova = run_with_nova(scenario)
        print(f"Regime: {with_nova['regime']}")
        print(f"Action Policy: {with_nova['action_policy']}")
        print(f"Decision: {with_nova['decision']}")
        print(f"Result: {with_nova['result']}")
        print()
        print("Nova Decision Impact")
        print(f"- Requested Size: {scenario.size:g}")
        executed_size = with_nova['executed_size']
        print(f"- Executed Size: {executed_size:g}" if executed_size > 0 else "- Executed Size: 0 (blocked)")
        print(f"- Nova Regime: {with_nova['regime']}")
        print(f"- Nova Decision: {with_nova['decision']}")
        print(f"- Reason: {with_nova['reason']}")
    except Exception as exc:
        # Fail-safe behavior is explicit so demo output stays understandable.
        with_nova = {
            "decision": "VETO",
            "executed_size": 0.0,
            "reason": f"Nova context unavailable ({exc})",
            "result": f"Failed to fetch Nova context ({exc})",
        }
        print("Regime: Unknown")
        print("Action Policy: unavailable")
        print(f"Decision: {with_nova['decision']}")
        print(f"Result: {with_nova['result']}")
        print()
        print("Nova Decision Impact")
        print(f"- Requested Size: {scenario.size:g}")
        print("- Executed Size: 0 (blocked)")
        print("- Nova Regime: Unknown")
        print(f"- Nova Decision: {with_nova['decision']}")
        print(f"- Reason: {with_nova['reason']}")

    print("=" * 60)
    return {
        "without_nova_decision": without_nova["decision"],
        "with_nova_decision": with_nova["decision"],
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
