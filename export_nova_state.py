#!/usr/bin/env python3
"""
Export current Nova state from /v1/context endpoint.

Reads NOVA_API_URL and NOVA_API_KEY from environment variables.
Calls /v1/context with a standard scenario and writes the canonical state to nova_state.json.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.exceptions import RequestException


def infer_action_policy_from_regime(regime):
    # Fallback mapping when API response does not include guardrail.action_policy.
    if regime == "Stress":
        return {
            "allow_new_risk": False,
            "allow_risk_reduction": True,
            "allow_position_increase": False,
            "allow_position_decrease": True,
        }

    if regime == "Elevated Fragility":
        return {
            "allow_new_risk": True,
            "allow_risk_reduction": True,
            "allow_position_increase": False,
            "allow_position_decrease": True,
        }

    return {
        "allow_new_risk": True,
        "allow_risk_reduction": True,
        "allow_position_increase": True,
        "allow_position_decrease": True,
    }


def main():
    # Read environment variables
    api_url = os.getenv("NOVA_API_URL")
    api_key = os.getenv("NOVA_API_KEY")

    if not api_url or not api_key:
        print("ERROR: NOVA_API_URL and NOVA_API_KEY must be set in environment.")
        sys.exit(1)

    # Prepare the /v1/context request
    context_url = f"{api_url.rstrip('/')}/v1/context"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    params = {
        "intent": "trade",
        "asset": "ETH",
        "size": 10000,
    }

    try:
        response = requests.get(context_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
    except RequestException as e:
        print(f"ERROR: Failed to call /v1/context: {e}")
        sys.exit(1)

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse API response as JSON: {e}")
        sys.exit(1)

    # Extract canonical state
    action_policy = data.get("guardrail", {}).get("action_policy")
    if not action_policy:
        action_policy = infer_action_policy_from_regime(data.get("regime"))

    canonical_state = {
        "timestamp_utc": data.get("timestamp_utc"),
        "epoch": data.get("epoch"),
        "regime": data.get("regime"),
        "action_policy": action_policy,
    }

    # Validate required fields
    required_fields = ["timestamp_utc", "epoch", "regime"]
    missing = [f for f in required_fields if not canonical_state.get(f)]
    if missing:
        print(f"ERROR: Missing required fields in API response: {missing}")
        sys.exit(1)

    # Write to nova_state.json
    output_path = Path(__file__).parent / "nova_state.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(canonical_state, f, indent=2)
    except IOError as e:
        print(f"ERROR: Failed to write to {output_path}: {e}")
        sys.exit(1)

    # Success message
    print(f"✓ Nova state exported successfully to {output_path}")
    print(f"  Epoch: {canonical_state['epoch']}")
    print(f"  Regime: {canonical_state['regime']}")
    print(f"  Timestamp: {canonical_state['timestamp_utc']}")


if __name__ == "__main__":
    main()
