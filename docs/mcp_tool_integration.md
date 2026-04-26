# MCP Tool Integration

Nova may be exposed as external tools, but tool wrapping does not weaken Nova authority.

## Tools

- `nova_context` -> call `/v1/context` to retrieve the governed decision
- `nova_proof` -> call `/v1/proof/{decision_id}` to verify the governed decision

## Rule

All capital-moving actions must call `nova_context` before execution.

MCP clients must bind behavior to `decision_status`, not to agent reasoning or supporting fields.
