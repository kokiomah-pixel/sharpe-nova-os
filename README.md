# Sharpe Nova OS

Sharpe Nova OS is a pre-execution decision discipline layer for autonomous capital systems.
It conditions decisions before capital moves, ensuring they are coherent, constrained, and explainable under consistent rules.

This positions Nova as a decision discipline layer for autonomous capital systems.

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

Nova operates at this layer and conditions decisions before execution.

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
- Impact on Outcomes
- Recommendation
- Decision Status

This structure is invariant across all Nova responses.

All outputs follow a fixed structure, are neutral in tone, and are designed for institutional decision workflows.
It is designed to be readable in real time and defensible in governance settings.

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

Nova can be inserted as a pre-execution checkpoint in any existing workflow.

## Captured Example

This is a captured example for demonstration purposes, not a live output.

WITHOUT NOVA
- Executed size: 80,500

WITH NOVA (Configured Decision Regime: Elevated Fragility)
- Decision: CONSTRAIN
- Executed size: 40,250
- Reason: position increase blocked

Without Nova, decisions are evaluated in isolation.
With Nova, decisions are evaluated under consistent constraints.

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

Use the wrapper in `examples/nova_client.py` for the fastest integration path.

```python
from examples.nova_client import get_nova_decision

decision = get_nova_decision("trade", "ETH", 10000)

if decision["decision"] in {"VETO", "CONSTRAIN"}:
    pass  # halt or reduce before execution
else:
    pass  # proceed under local controls
```

Direct API call:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://YOUR_API_DOMAIN/v1/context?intent=trade&asset=ETH&size=10000"
```

Behavior comparison demo:

```bash
python examples/nova_comparison_agent.py
```

---

## Live vs Fixed Mode

Nova operates in two modes depending on environment configuration.

### Live Mode (default)

- `timestamp_utc` updates on every request
- `epoch` updates automatically (hourly bucket)
- returns current API-configured decision context in real time

This is the default production behavior.

### Fixed Mode (for testing and evidence)

You can override time using environment variables:

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

- Payload signatures are HMAC-SHA256 using `NOVA_SIGNING_SECRET` (default: `replace_me`).
- Usage is persisted between restarts in a JSON file (default `.usage.json`). You can override via `NOVA_USAGE_FILE`.
- For scalable shared deployment, you can use Redis (set `NOVA_REDIS_URL`) instead of file persistence; this makes usage/quota/rate-limit state shared across instances.
- The service enforces a per-key `monthly_quota` (from the key metadata). If usage exceeds the quota, protected endpoints return `429`.
- Optionally, a key can set a `rate_limit` object in its metadata to enforce short-term rate limits (e.g. `{"window_seconds": 60, "max_calls": 30}`).
- Default configured decision regime/epoch values are set via:
  - `NOVA_EPOCH`
  - `NOVA_TIMESTAMP_UTC`
  - `NOVA_CONSTITUTION_VERSION`
  - `NOVA_REGIME`

---

## Verification / Tests

### Health check (no auth required)
```bash
curl -i http://127.0.0.1:8000/health
```

### Live decision call
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://YOUR_API_DOMAIN/v1/context?intent=trade&asset=ETH&size=10000"
```

### Usage and reset
```bash
export NOVA_API_KEY="mytestkey"
curl -i -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/regime

curl -i -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/usage

curl -i -X POST -H "Authorization: Bearer mytestkey" http://127.0.0.1:8000/v1/usage/reset
```

### Run tests
```bash
./.venv/bin/pytest -q
```
