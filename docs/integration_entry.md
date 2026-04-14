# Integration Entry

Sharpe Nova OS integrates through a machine-readable API contract.

## Integration Pattern

1. Submit a decision candidate to `/v1/context`.
2. Parse `decision_status` and the returned constraint fields.
3. Enforce refusal or constraint states before any downstream execution step.

## Required Binding

- `ALLOW`: proceed
- `CONSTRAIN`: proceed only with returned limits
- `DELAY`: hold and re-evaluate later
- `DENY`: refuse
- `HALT`: suspend downstream admission

## Integration Boundary

No integration should reinterpret Nova output as optional guidance.

The response contract is authoritative.
