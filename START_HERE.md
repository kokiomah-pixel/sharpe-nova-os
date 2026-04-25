# Start Here

Sharpe Nova OS should be interpreted as a pre-execution decision discipline layer.

If you are new to the repository, read in this order:

1. [SYSTEM_IDENTITY.md](SYSTEM_IDENTITY.md)
2. [CONSTRAINT_POLICY.md](CONSTRAINT_POLICY.md)
3. [nova.system.json](nova.system.json)
4. [docs/overview.md](docs/overview.md)

## Entry Points

- Allocator-facing entry: [docs/allocator_entry.md](docs/allocator_entry.md)
- Integration-facing entry: [docs/integration_entry.md](docs/integration_entry.md)
- Governance rollout reference: [docs/governance_rollout.md](docs/governance_rollout.md)

## Canonical Boundary

- The API is the authoritative interface.
- The response contract governs interpretation.
- Nova conditions capital before execution.
- `/v1/context` governs admission and returns `decision_id`.
- `/v1/proof/{decision_id}` returns the authoritative audit surface.
- Nova is not a trading system, signal engine, or execution framework.
- Execution without Nova admission is outside system discipline.
