# Your Decision Stack Has No Risk Brake. Nova OS Adds One.

If your system can expose capital without checking whether it is *allowed* under the current decision constraint context, it is operating without constraint enforcement.

Run this:

```bash
./.venv/bin/python examples/nova_comparison_agent.py
```

Here is what you will see:

```
============================================================
Scenario: trade | ETH | 10000

WITHOUT NOVA
Decision State: UNCONSTRAINED
Result: full exposure remains at proposed size (10000)

WITH NOVA
Configured Decision Regime: Elevated Fragility
Action Policy: {
  "allow_new_risk": true,
  "allow_position_decrease": true,
  "allow_position_increase": false,
  "allow_risk_reduction": true
}
Decision: CONSTRAIN
Result: validated decision state constrains exposure to retained-discipline size (4000 vs 10000)
============================================================

SUMMARY

Without Nova:
- 4/4 scenarios remained unconstrained at full size
- Total validated exposure before execution: 80500

With Nova:
- 4 CONSTRAIN
- Total validated exposure before execution: 32200

Nova changed validated decision state in 4/4 scenarios.
```

---

## What This Means

Your agent, running without a control layer, would have deployed **80,500 units** of exposure across four standard scenarios under captured decision-relevant conditions.

With Nova, it deployed **32,200** — because the configured decision regime (`Elevated Fragility`) and retained discipline together tighten exposure before execution.

That is not a strategy difference. That is a **control gap**.

Your system did not know the configured decision regime. It had no policy to read. The proposed exposure remained at full size because nothing told it not to.

---

## The Missing Step in Every Autonomous Decision Loop

Every autonomous capital system has some version of this loop:

```
intent → size → decision validation before execution
```

The missing step is:

```
intent → size → [CHECK: is this allowed right now?] → constrain, allow, or halt
```

Nova is that check. It is a single API call that returns:

- the current decision constraint context (including configured decision regime)
- whether new risk is allowed
- whether position increases are allowed
- whether risk reduction is required

Your system reads it. Your system applies constraint enforcement. Capital is then exposed only under a validated decision state.

---

## Integration (2 Lines)

```python
import requests

def nova_gate(intent, asset, size, api_key):
    res = requests.get(
        "https://nova-api-ipz6.onrender.com/v1/context",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"intent": intent, "asset": asset, "size": size}
    ).json()

    if res["decision_status"] == "VETO":
        raise RuntimeError("Nova VETO: new risk not permitted in current configured decision regime")

    if res["decision_status"] == "CONSTRAIN":
        adjusted = res["impact_on_outcomes"]["adjusted_size"]
        raise RuntimeError(f"Nova CONSTRAIN: reduce size to {adjusted} before capital deployment")

    return True
```

Drop this before any capital action. If Nova says no, your system does not proceed to capital deployment.

---

## Example Decision Constraint Context Snapshot (Captured 2026-03-16 UTC)

```json
{
  "timestamp_utc": "2026-03-16T16:00:00Z",
  "epoch": 2461,
  "regime": "Elevated Fragility",
  "action_policy": {
    "allow_new_risk": true,
    "allow_risk_reduction": true,
    "allow_position_increase": false,
    "allow_position_decrease": true
  }
}
```

This is a machine-readable snapshot example. Your system can poll `/v1/context` before every capital deployment for current decision constraint context.

---

## What Happens Without This

Agents already validate and route capital decisions in loops.

Without a pre-execution control point:

- they increase exposure during fragile conditions
- they continue deploying risk after the environment degrades
- they compound behavior across systems with no shared constraints

This is not a model failure. It is a control failure.

If your agent cannot determine whether it is *allowed* to increase risk before acting, it is incomplete.

---

## Check Your System

Before integrating anything, answer this:

- Does your system know when it should NOT increase risk?
- Does it change execution size based on configured decision regime?
- Would it behave differently in Stress vs Stable?

If the answer to any of these is “no”:

Your system is operating with no control layer.

---

## Next Step

Run the comparison script. Observe the difference in validated exposure.

Then route a real decision through Nova:

```bash
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
  "https://nova-api-ipz6.onrender.com/v1/context?intent=trade&asset=ETH&size=10000"
```

Read the response:

- `decision_status` -> whether the decision is admissible
- `constraint_effect` -> how exposure must change
- `intervention_type` -> what action is enforced

Retrieve proof:

```bash
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
  "https://nova-api-ipz6.onrender.com/v1/proof/{decision_id}"
```

If Nova changes the decision - if size is reduced, blocked, or delayed -

you are seeing a live constraint that your system does not enforce.

That is the gap.

Close it before capital moves.
