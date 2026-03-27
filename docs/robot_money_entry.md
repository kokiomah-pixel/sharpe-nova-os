# Your Trading Agent Has No Risk Brake. Nova OS Adds One.

If your system can move capital without checking whether it is *allowed* under the current regime, it is executing unconditionally.

Run this:

```bash
python examples/nova_comparison_agent.py
```

Here is what you will see:

```
============================================================
Scenario: trade | ETH | 10000

WITHOUT NOVA
Decision: EXECUTE
Result: trade executes at full size (10000)

WITH NOVA
Regime: Elevated Fragility
Action Policy: {
  "allow_new_risk": true,
  "allow_position_decrease": true,
  "allow_position_increase": false,
  "allow_risk_reduction": true
}
Decision: CONSTRAIN
Result: trade executes at reduced size (5000 vs 10000)
============================================================

SUMMARY

Without Nova:
- 4/4 scenarios executed at full size
- Total executed size: 80500

With Nova:
- 4 CONSTRAIN
- Total executed size: 40250

Nova changed execution behavior in 4/4 scenarios.
```

---

## What This Means

Your agent, running without a control layer, would have deployed **80,500 units** of risk across four standard scenarios under current market conditions.

With Nova, it deployed **40,250** — because the live regime (`Elevated Fragility`) prohibits increasing position size.

That is not a strategy difference. That is a **control gap**.

Your system did not know the regime. It had no policy to read. It executed at full size because nothing told it not to.

---

## The Missing Step in Every Autonomous Execution Loop

Every autonomous capital system has some version of this loop:

```
intent → size → execute
```

The missing step is:

```
intent → size → [CHECK: is this allowed right now?] → execute or halt
```

Nova is that check. It is a single API call that returns:

- the current market regime
- whether new risk is allowed
- whether position increases are allowed
- whether risk reduction is required

Your system reads it. Your system decides. Capital moves conditionally.

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

    policy = res["guardrail"]["action_policy"]

    if not policy["allow_new_risk"]:
        raise RuntimeError("Nova VETO: new risk not permitted in current regime")

    if not policy["allow_position_increase"]:
        raise RuntimeError("Nova CONSTRAIN: position increase blocked")

    return True
```

Drop this before any capital action. If Nova says no, your system stops.

---

## Live State Right Now

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

This is a machine-readable signal. Your system can poll it before every execution.

---

## What Happens Without This

Agents already execute capital decisions in loops.

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
- Does it change execution size based on regime?
- Would it behave differently in Stress vs Stable?

If the answer to any of these is “no”:

Your system is executing with no control layer.

---

## Next Step

Run the comparison script. See your own output.

If the numbers change — if Nova would have modified what your system would have done — you have a live gap in your execution stack.

Close it: [nova-api-ipz6.onrender.com](https://nova-api-ipz6.onrender.com)
