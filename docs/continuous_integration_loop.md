# Continuous Decision Loop

Sharpe Nova OS sits between decision formation and execution.

Canonical placement:

signal → sizing → Nova → execution

## Why Nova Must Sit Here

Nova is called every time capital is about to move.

It is not a periodic report.

It is not a post-trade explanation layer.

## Canonical Continuous Loop

```python
import requests

while True:
    decision = generate_decision()

    res = requests.get(
        "http://127.0.0.1:8000/v1/context",
        headers={"Authorization": f"Bearer {api_key}"},
        params=decision,
    ).json()

    status = res["decision_status"]

    if status == "ALLOW":
        execute(decision)

    elif status == "CONSTRAIN":
        adjusted = res["impact_on_outcomes"]["adjusted_size"]
        decision["size"] = adjusted
        execute(decision)

    else:
        log_block(res)
        continue
```

This is the canonical loop:

1. form a decision
2. send it to Nova before execution
3. obey the governed outcome

## Outcome Handling

- `ALLOW` → proceed
- `CONSTRAIN` → modify the decision according to governed output, then proceed
- `DENY` → do not execute
- `DELAY` → do not execute
- `HALT` → do not execute
- `VETO` → do not execute

Primary authority comes from:

- `decision_status`
- proof-layer outcomes when audit is needed

Supporting fields such as `impact_on_outcomes` are explanatory, not authoritative.

## Proof Retrieval

When auditability is required:

1. retain `decision_id` from `/v1/context`
2. retrieve `/v1/proof/{decision_id}`
3. use proof to verify the governed outcome

Proof is for verification.
It does not replace `decision_status` as execution authority.

## If Nova Is Unavailable

Preferred posture:

- fail closed
- halt decision flow
- do not proceed to capital movement without governed output

Bypassing Nova due to convenience is outside governed decision discipline.

## Non-Bypass Rule

Sharpe Nova OS is a decision discipline layer.

If a system ignores or bypasses governed output, it is no longer operating under Nova's decision discipline.

Nova is only integrated when its output is binding.
