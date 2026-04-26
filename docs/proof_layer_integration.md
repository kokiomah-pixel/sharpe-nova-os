# Proof Layer Integration

`/v1/context` returns the governed decision.

`/v1/proof/{decision_id}` verifies the governed decision with proof-backed governance fields.

## Required Fields

- decision_id
- decision_status
- constraint_effect
- intervention_type
- failure_class
- reproducibility_hash

## Usage

- audit verification
- governance tracking
- proof-backed review of the governed outcome

Execution authority remains with `decision_status` from `/v1/context`.

Proof may inform audit and downstream review, but it must not replace `decision_status` as permission authority.
