# Sharpe Nova OS

## Run a Decision Through Nova

Before capital moves, the system determines whether the decision should exist.

Start the local server:

```bash
NOVA_API_KEY=mytestkey uvicorn app:app --host 127.0.0.1 --port 8000
```

Try this:

```bash
curl -s -H "Authorization: Bearer mytestkey" \
"http://127.0.0.1:8000/v1/context?intent=trade&asset=ETH&size=10000"
```

You are not asking Nova what performs best.

## Why this matters

You are not giving instructions.

You are:

> **forcing a cognitive shift**

Nova does not execute trades.

It applies pre-execution discipline through decision validation before capital moves.

### Example Output (Simplified)

```json
{
  "decision_status": "CONSTRAIN",
  "adjustment": "Reduce requested size from 10000 to 4000 and tighten execution controls.",
  "constraint_analysis": {
    "why_this_happened": "Constraint analysis limited the request because the regime allows participation but blocks unrestricted position growth."
  },
  "impact_on_outcomes": {
    "adjusted_size": 4000.0,
    "why_this_happened": "Risk can proceed only in reduced form, so downstream execution should be size-limited."
  }
}
```

The key is not the output itself.

It is seeing that the system intervenes before execution.

### Important

This example is simplified to foreground the constrained decision, the exposure adjustment, and the visible reason while matching the current response shape.

This is the moment Nova introduces discipline into a decision before capital moves.

### What Just Happened

A decision attempted to enter the system.

Nova evaluated it before execution.

The system did one of three things:

- Allowed it
- Constrained it
- Rejected it

This is not optimization.

This is decision admission.

## Run It Again (Change One Variable)

Now run the same request again, but change the size:

```bash
curl -s -H "Authorization: Bearer mytestkey" \
"http://127.0.0.1:8000/v1/context?intent=trade&asset=ETH&size=20000"
```

Compare this response to your first one.

You are asking:

Is this decision allowed?

Look for:

- whether the decision is still allowed or further constrained
- how the adjustment changes
- how the reasoning evolves

Nova is not producing a static answer.

It is conditioning decisions based on the structure of the request and current system context before execution.

If you change the structure of the decision, Nova will change how it responds.

This is how discipline becomes consistent across different scenarios.

### Try Your Own Decision

Change the parameters and run the request again:

- asset
- size
- intent

Observe how Nova responds under different conditions.

## Safe to Test

This repository is safe for local testing.

All examples run against a locally scoped environment and do not interact with live capital or production systems. Nova validates decisions before execution, and this repo is designed to make that behavior observable without exposing any sensitive infrastructure.

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

- full allocation remains unchanged before execution

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

- decisions remain unchanged before execution
- exposure remains unchanged
- failure conditions propagate

With Nova:

- decisions are validated before execution
- exposure is adjusted under constraint
- failure propagation is reduced

## What Nova Is Not

Nova is not:

- a market action system
- a signal engine
- a prediction model
- an allocation optimizer

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

Note: This endpoint returns a validated decision state. It does not initiate market actions or deploy capital.

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

## Testing Nova Locally

You can run and test Nova entirely in a local environment.

- Runs on `localhost`
- Uses test API keys
- Does not connect to live capital or external execution systems

Example:

`http://127.0.0.1:8000/v1/context?intent=trade&asset=ETH&size=10000`

This allows you to observe how Nova validates and constrains decisions before execution.

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
