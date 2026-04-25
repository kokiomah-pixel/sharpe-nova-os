# Integration Patterns

Examples in this repository are controlled integration patterns for Sharpe Nova OS.

## Required Example Behavior

- submit decisions to the Nova API
- read `decision_status`
- retain `decision_id`
- retrieve `/v1/proof/{decision_id}` when audit evidence is required
- enforce refusal states
- preserve the authoritative outcome surface

## Prohibited Example Behavior

- execute trades
- optimize strategies
- bypass governance
- treat refusal states as non-binding

## Current Example Set

- `hyperliquid_nova_enforcement_adapter.py`: demonstrates refusal-aware downstream enforcement
- `governance_key_profiles.json`: demonstrates governed environment profiles

Other examples should be read only if they preserve the same contract discipline.
