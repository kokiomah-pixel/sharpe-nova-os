# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer that conditions capital before it moves.

## What This Is

- A decision-layer interface
- A capital conditioning system
- A constraint and governance surface

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
The API output is authoritative.
No interpretation beyond contract is permitted.

## Canonical Interface

Nova API is the machine-readable interface to the pre-execution decision layer.

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

Evaluate the response through contract fields such as:

- `decision_status`
- `constraint_analysis`
- `impact_on_outcomes`
- `adjustment`

## Interpretation Discipline

Nova conditions decisions before execution.

It does not:

- select trades
- optimize strategy
- route execution
- bypass governance

Examples in this repository are valid only when they submit decisions, bind to `decision_status`, and enforce refusal states.
