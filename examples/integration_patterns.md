# Integration Patterns

Examples in this repository are controlled integration patterns for Sharpe Nova OS.

## Required Example Behavior

- submit decisions to the Nova API
- read `decision_status`
- enforce refusal states
- preserve the returned constraint surface

## Prohibited Example Behavior

- execute trades
- optimize strategies
- bypass governance
- treat refusal states as advisory only

## Current Example Set

- `hyperliquid_nova_enforcement_adapter.py`: demonstrates refusal-aware downstream enforcement
- `governance_key_profiles.json`: demonstrates governed environment profiles

Other examples should be read only if they preserve the same contract discipline.
