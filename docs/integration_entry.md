# Integration Entry

Sharpe Nova OS integrates through a machine-readable API contract.

## Integration Pattern

1. Submit a decision candidate to `/v1/context`.
2. Parse `decision_status`, `decision_id`, and `system_state`.
3. Retrieve `/v1/proof/{decision_id}` when you need the authoritative audit surface.
4. Enforce refusal or constraint states before any downstream execution step.

## Required Binding

- `ALLOW`: proceed
- `CONSTRAIN`: proceed only with returned limits
- `DELAY`: hold and re-evaluate later
- `DENY`: refuse
- `HALT`: suspend downstream admission

## Integration Boundary

No integration should reinterpret Nova output as a bypassable suggestion.

The response contract is authoritative, and proof fields should be read from the proof endpoint rather than inferred from internal traces.
