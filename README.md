# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer that conditions, enforces, and proves whether capital is allowed to move before execution.

This repository is the canonical Sharpe Nova OS system repo. It contains the Nova API, proof layer, governance runtime, canonical specs, tests, and runnable examples.

## Canonical Decision Contract

- `/v1/context` returns the governed decision and authoritative `decision_status`
- `/v1/proof/{decision_id}` verifies the governed decision with proof-backed governance fields

Nova is authoritative and auditable. Downstream systems must bind execution behavior to the governed decision returned by `/v1/context`.

## What Lives Here

- API implementation and runtime behavior
- proof generation and retrieval
- governance specifications and system contracts
- tests for decision admission and proof integrity
- examples showing one-decision flows and integration behavior

## What Nova Is Not

Nova is not an execution engine or a strategy system. It does not move capital on its own. It determines whether a proposed capital action is admitted, constrained, delayed, denied, halted, or vetoed before execution can occur.

## Run One Decision

From the repository root:

```bash
./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl -s "http://127.0.0.1:8000/v1/context?intent=trade&asset=ETH&size=10000" \
  -H "x-api-key: mytestkey"
```

Read `decision_status` first. If the response returns `CONSTRAIN`, apply the governed adjustment before any execution step. If the response returns `DENY`, `DELAY`, `HALT`, or `VETO`, do not execute.

## Retrieve Proof

After receiving a `decision_id` from `/v1/context`:

```bash
curl -s "http://127.0.0.1:8000/v1/proof/<decision_id>" \
  -H "x-api-key: mytestkey"
```

`/v1/proof/{decision_id}` verifies the governed decision. It does not replace `decision_status` as execution authority.

## End-to-End Decision Flow

See a complete example of decision admission, enforcement, and proof:

[examples/nova_end_to_end_decision_flow.md](examples/nova_end_to_end_decision_flow.md)

## Read Next

1. [START_HERE.md](START_HERE.md)
2. [docs/overview.md](docs/overview.md)
3. [docs/integration_entry.md](docs/integration_entry.md)
4. [specs/decision_admission_contract.json](specs/decision_admission_contract.json)

For developer integration doctrine, see:
https://github.com/kokiomah-pixel/nova-developer-docs
