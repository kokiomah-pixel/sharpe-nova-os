# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer that conditions and verifies whether capital is allowed to move before execution.

## What This Is

- A pre-execution decision discipline layer
- A decision admission infrastructure surface
- A constraint interface with verifiable proof

## What This Is Not

- Not a trading system
- Not a signal engine
- Not an execution framework

## Who This Is For

- builders of agent systems
- allocators managing capital flows
- engineers designing decision infrastructure

## System Boundary

All interaction is governed through the Nova API.

The API output is authoritative and auditable.
Each decision produces a deterministic outcome and a verifiable proof surface.

No interpretation beyond contract is permitted.

## Governance Doctrine

Sharpe Nova OS operates under explicit governance discipline:

- Runtime Artifact Policy
- Signal Pressure Discipline Protocol

These define:

- what is system definition vs runtime state
- how governance signals are interpreted and acted upon
- how discipline is preserved under system pressure

All implementations and operator behavior must adhere to these policies.

These documents are part of the system boundary and must not be treated as optional guidance.

## Canonical Interface

Nova API is the machine-readable interface to the pre-execution decision layer.

## Proof Layer

Every decision is bound to a verifiable proof object.

- `/v1/context` returns a governed decision and `decision_id`
- `/v1/proof/{decision_id}` returns the audit surface for that decision

Proof includes:

- `decision_status`
- `constraint_effect`
- `failure_class`
- `intervention_type`
- `memory_influence`
- `system_state`
- `reproducibility_hash`

Proof reflects the final governing outcome only.
Internal logic, scoring, and Reflex Memory structure are not exposed.

## Field Hierarchy

Nova exposes both primary and secondary fields.

Primary fields define the authoritative decision outcome and must be used for integration and audit:

- `decision_status`
- `constraint_effect`
- `intervention_type`
- `failure_class`

Secondary fields provide supporting detail and must not be used as the source of decision authority:

- `impact_on_outcomes`
- `adjustment`
- internal constraint calculations

All integrations must bind to primary fields.

Primary root surfaces:

- [START_HERE.md](START_HERE.md)
- [SYSTEM_IDENTITY.md](SYSTEM_IDENTITY.md)
- [CONSTRAINT_POLICY.md](CONSTRAINT_POLICY.md)
- [nova.system.json](nova.system.json)

Stable machine-readable specifications:

- [specs/decision_admission_contract.json](specs/decision_admission_contract.json)
- [specs/constraint_interface.json](specs/constraint_interface.json)
- [specs/constraint_policy.json](specs/constraint_policy.json)
- [specs/decision_admission_rules.json](specs/decision_admission_rules.json)
- [specs/permission_contract.json](specs/permission_contract.json)

## Repository Structure

- `app.py`: Nova API surface
- `docs/`: overview, allocator entry, integration entry, governance rollout
- `specs/`: machine-readable contracts and policies
- `examples/`: controlled integration examples
- `tests/`: behavioral verification

## Quick Start

Start the local API:

```bash
NOVA_API_KEY=mytestkey ./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

Submit a decision for admission:

```bash
curl -s -H "Authorization: Bearer mytestkey" \
  "http://127.0.0.1:8000/v1/context?intent=trade&asset=ETH&size=10000"
```

Read the governed response through:

- `decision_status`
- `decision_id`
- `system_state`

Retrieve proof for the auditable outcome:

```bash
curl -s -H "Authorization: Bearer mytestkey" \
  "http://127.0.0.1:8000/v1/proof/{decision_id}"
```

Evaluate proof through:

- `decision_status`
- `constraint_effect`
- `intervention_type`
- `failure_class`
- `memory_influence`
- `reproducibility_hash`

## Interpretation Discipline

Nova enforces and proves whether a decision is admissible before execution.

Nova conditions decisions before execution.

It does not:

- select trades
- optimize strategy
- route execution
- bypass governance

Examples in this repository are valid only when they submit decisions, bind to `decision_status`, and enforce refusal states.
