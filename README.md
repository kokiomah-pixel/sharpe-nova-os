# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer for autonomous capital systems.
It conditions decisions before capital moves, ensuring they are coherent, constrained, and explainable under consistent rules.
Nova conditions decisions through telemetry, constraint logic, and retained memory before execution.

## What Nova Is

Nova is a callable API that evaluates decision context before execution.
It returns structured, neutral outputs that can be used in trading systems, agent workflows, and governance processes.

## What Nova Is Not

- Not a trading system
- Not a signal engine
- Not a portfolio optimizer
- Not a hedge fund
- Not an execution layer

Nova does not generate trades or execution signals.
Nova conditions the decision context in which trades are made.

## The Shift

Capital is becoming autonomous.
Execution is no longer the constraint.

Decision coherence is.

Nova operates at this layer.

## Reference

- Example output: see Output Structure below
- Integration: `examples/nova_client.py`
- Behavior demo: `examples/nova_comparison_agent.py`
- Tests: `tests/test_app.py`
- State model: `docs/NOVA_STATE_MODEL.md`

## System Position

```text
[ Strategy / Agent Layer ]
            ↓
[ Nova OS — Pre-Execution Decision Constraint Layer ]
            ↓
[ Execution Layer ]
```

## Output Structure

### Example Output

- Decision Context
- Constraint Analysis
- Historical Reference
- Reflex Memory
- Impact on Outcomes
- Adjustment
- Decision Status

This structure is invariant across all Nova decision responses.

In the JSON payload, these sections are exposed as:
- `decision_context`
- `constraint_analysis`
- `historical_reference`
- `reflex_memory`
- `impact_on_outcomes`
- `adjustment`
- `decision_status`

All outputs follow a fixed structure, are neutral in tone, and are designed for institutional decision workflows.
They are readable in real time and defensible in governance settings.

`reflex_memory` is operational retained discipline, not latent learning. It exposes machine-readable state, a small validated registry surface, and allocator-safe proof of when retained memory tightened or blocked a decision.

### API Contract (Simplified)

Input: decision context
Output: structured decision response

The response format is fixed and invariant.

## Verifiability

Nova outputs are designed to be verifiable.

Decisions can be anchored to cryptographic attestations that ensure:
- consistent inputs
- applied constraints
- no post-generation modification

This repository focuses on the decision layer.

Attestation infrastructure is introduced separately and is not implemented here.

Verifiability is designed to ensure decision integrity without exposing strategy details.

## Quick Integration

1. Form a decision (allocation, trade, adjustment)
2. Send it to Nova API
3. Receive structured decision output
4. Apply constraints before execution

This establishes Nova as a pre-execution checkpoint in any decision workflow.

## Captured Example

This is a captured example for demonstration purposes, not a live output.

**WITHOUT NOVA**
- Executed size: 80,500

**WITH NOVA (Configured Decision Regime: Elevated Fragility)**
- Decision: CONSTRAIN
- Executed size: 40,250
- Reason: position increase blocked

---

Without Nova -> decisions are evaluated in isolation
With Nova -> decisions are evaluated under consistent constraints

## Run This First

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
"https://YOUR_API_DOMAIN/v1/context?intent=trade&asset=ETH&size=10000"
```

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run the server:

```bash
./.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

For local example scripts:

```bash
export NOVA_API_URL=http://127.0.0.1:8000
export NOVA_API_KEY=mytestkey
```

### Run via Docker

```bash
docker build -t nova-api .
docker run --rm -p 8000:8000 -e NOVA_API_KEY=mytestkey nova-api
```

---

## Access & Metering

Nova API access is controlled via API keys.

Usage is governed through Policy B:
- request metering
- quota enforcement
- usage tracking

This repository implements access control and usage constraints.

Payment rails, wallet integration, and settlement are not implemented in this repository.

Access and usage are designed to integrate into external systems rather than define them.

---

## Integration Reference

- Wrapper path: `examples/nova_client.py`
- Direct call: `GET /v1/context`
- Behavior demo: `python3 examples/nova_comparison_agent.py`

---

## Live vs Fixed Mode

Live mode is default:
- `timestamp_utc` updates on every request
- `epoch` updates automatically (hourly bucket)

Fixed mode is available for evidence capture:

```bash
export NOVA_TIMESTAMP_UTC="2026-03-16T16:00:00Z"
export NOVA_EPOCH=2461
```

## Evidence

Controlled behavior evidence is documented in [`NOVA_EVIDENCE_PACK_V1.md`](NOVA_EVIDENCE_PACK_V1.md).

This includes verified structured decision output captures for all three behavior outcomes across configured decision regimes:

| Outcome | Configured Decision Regime | Verified |
|---------|--------|---------|
| VETO | Stress | yes |
| CONSTRAIN | Elevated Fragility | yes |
| ALLOW | Stable | yes |

Evidence was captured under controlled conditions with locked epoch, configured decision regime, and action policy values. All outputs are machine-verifiable via HMAC-SHA256 payload signatures.

---

## Notes

- Payload signatures: HMAC-SHA256 using `NOVA_SIGNING_SECRET`
- Usage state: `.usage.json` (override via `NOVA_USAGE_FILE`)
- Shared deployments: use `NOVA_REDIS_URL`
- Core config: `NOVA_REGIME`, `NOVA_EPOCH`, `NOVA_TIMESTAMP_UTC`, `NOVA_CONSTITUTION_VERSION`

---

## Verification / Tests

Run the following from repo root:

```bash
curl -i http://127.0.0.1:8000/health
curl -H "Authorization: Bearer YOUR_API_KEY" "https://YOUR_API_DOMAIN/v1/context?intent=trade&asset=ETH&size=10000"
export NOVA_API_KEY="mytestkey"
curl -i -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/regime
curl -i -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/usage
curl -i -X POST -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/usage/reset
PYTHONPATH=. ./.venv/bin/pytest -q
python3 examples/nova_client.py
python3 examples/nova_comparison_agent.py
```
