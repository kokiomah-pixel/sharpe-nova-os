# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer that conditions capital through telemetry, reflex memory, and constraint logic before execution.

It does not generate trades.  
It does not predict markets.  
It does not optimize portfolios.

It determines whether a decision should proceed before capital moves.

## The Missing Layer

Most systems are designed to act.

Very few are designed to validate whether an action should occur.

As capital systems become automated:

- decision frequency increases
- execution speed increases
- error propagation accelerates

The current stack assumes decisions are correct.

There is no system that conditions decisions before execution.

## System Placement

Decision → Nova → Execution

Nova sits between decision formation and execution.

It evaluates whether a decision should proceed under current conditions before capital is exposed.

## API Output Structure

Each call to Nova returns:

- `decision_context`
- `constraint_analysis`
- `historical_reference`
- `impact_on_outcomes`
- `adjustment`
- `decision_status`

This output represents a validated decision state before execution.

Nova also returns `reflex_memory`, which exposes the retained discipline state applied to the decision.

## Example

Input:

```text
intent=trade
asset=ETH
size=10000
```

Output (simplified):

- `decision_status`: `CONSTRAIN`
- `adjustment`: reduce size from `10000` to `4000`
- `constraint_analysis`: elevated fragility detected
- `impact_on_outcomes`: reduces exposure under unstable conditions

Without Nova:

- full allocation executes

With Nova:

- exposure is constrained before execution

## What Nova Changes

Nova does not improve outcomes after the fact.

It prevents fragile decisions from reaching execution.

This results in:

- reduced exposure under unstable conditions
- fewer repeated failure states
- more disciplined capital behavior over time

## Reflex Memory

Reflex Memory is the retained discipline layer inside Nova.

It encodes:

- prior failure states
- detection signals
- constraint logic
- future enforcement behavior

This ensures that known failure patterns do not repeat under similar conditions.

## Without Nova vs With Nova

Without Nova:

- decisions execute as proposed
- exposure remains unchanged
- failure conditions propagate

With Nova:

- decisions are validated before execution
- exposure is adjusted under constraint
- failure propagation is reduced

## What Nova Is Not

Nova is not:

- a trading system
- a signal engine
- a prediction model
- a portfolio optimizer

Nova is a decision discipline layer applied before execution.

## Final

Sharpe Nova OS is not where capital moves.

It is where decisions are validated before capital moves.

## Reference

- Example output: see API Output Structure above
- Integration: `examples/nova_client.py`
- Behavior demo: `examples/nova_comparison_agent.py`
- Tests: `tests/test_app.py`
- State model: `docs/NOVA_STATE_MODEL.md`

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
- Behavior demo: `./.venv/bin/python examples/nova_comparison_agent.py`

---

## Monetization

- Text version: `docs/NOVA_MONETIZATION.md`
- Manuscript PDF: design export to be added

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
./.venv/bin/python examples/nova_client.py
./.venv/bin/python examples/nova_comparison_agent.py
```
