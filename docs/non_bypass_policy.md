# Non-Bypass Policy

Nova is a required pre-execution checkpoint.

## Rules

- Nova must be called before any capital-moving action
- decision_status is authoritative
- DENY / DELAY / HALT / VETO cannot be bypassed
- CONSTRAIN must be applied before execution
- No retries to force ALLOW outcomes
- No execution without Nova admission

## Fail-Closed Behavior

If Nova is unavailable:

-> execution must NOT proceed
