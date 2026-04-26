# Sharpe Nova OS — End-to-End Decision Admission Flow

This example demonstrates how Sharpe Nova OS conditions a decision before execution and produces verifiable proof.

---

## Important Note

Nova outcomes depend on current system state.

This example demonstrates both possible paths:

- ALLOW (normal conditions)
- CONSTRAIN (elevated or stressed conditions)

---

## Scenario

A system proposes:

- Intent: allocate
- Asset: ETH
- Size: 10,000

---

## Step 1 — Submit Decision

```bash
curl -s -H "Authorization: Bearer mytestkey" \
"http://127.0.0.1:8000/v1/context?intent=allocate&asset=ETH&size=10000"
```

---

## Step 2 — Interpret Response

### Case A — ALLOW (Normal Conditions)

```json
{
  "decision_status": "ALLOW",
  "system_state": "NORMAL",
  "impact_on_outcomes": {
    "adjusted_size": 10000.0
  }
}
```

**Meaning:**

* Conditions are stable
* No constraint applied
* Execution proceeds as proposed

---

### Case B — CONSTRAIN (Elevated Conditions)

```json
{
  "decision_status": "CONSTRAIN",
  "system_state": "ELEVATED_FRAGILITY",
  "impact_on_outcomes": {
    "adjusted_size": 4000.0
  }
}
```

**Meaning:**

* Conditions require discipline
* Exposure is reduced before execution
* Execution must follow adjusted size

---

## Step 3 — Enforcement Rule (Always Applies)

```text
ALLOW → proceed

CONSTRAIN → adjust BEFORE execution

DENY / DELAY / HALT / VETO → DO NOT EXECUTE
```

---

## Step 4 — Retrieve Proof

```bash
curl -s -H "Authorization: Bearer mytestkey" \
"http://127.0.0.1:8000/v1/proof/<decision_id>"
```

---

## Step 5 — Proof Confirms Outcome

Proof will include:

* decision_id
* decision_status
* constraint_effect
* intervention_type
* reproducibility_hash

---

## What This Demonstrates

Nova does not always constrain.

Nova:

> **enforces discipline only when conditions require it**

---

## What Changed

Without Nova:

```text
Decision → Execution (always full size)
```

With Nova:

```text
Decision → Nova → Conditional Outcome → Execution only if admitted
```

---

## Authority Model

* `/v1/context` → determines decision admission
* `decision_status` → governs execution
* `/v1/proof/{decision_id}` → verifies outcome

Proof does not grant permission.

Proof confirms what was enforced.

---

## Final Principle

Sharpe Nova OS does not force constraint.

It determines:

> whether constraint is required before capital moves.
