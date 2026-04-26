# Sharpe Nova OS — Nova API Governance Upgrade v2.0
## Control-Layer Expansion for Persistent Autonomous Systems

---

# Status
**REQUIRED — Canonical Nova API Governance Upgrade**

This document defines the next control-layer expansion required for Sharpe Nova OS.

It is not a feature roadmap.

It is a governance upgrade to preserve Nova as:

> **a pre-execution decision discipline layer that conditions capital before it moves**

This upgrade must not turn Nova into:

- an agent runtime
- an orchestration framework
- a workflow engine
- an execution system
- a venue-specific trading application

---

# 1. Purpose

Nova’s admission layer is now enforcement-complete.

The next requirement is governance across:

- repeated decision requests
- persistent retry loops
- degraded telemetry
- cumulative permission pressure
- concurrent decision flow
- memory influence over time
- system-state degradation

This upgrade is required because autonomous systems can now:

- request decisions continuously
- retry denials rapidly
- apply pressure programmatically
- degrade system integrity through frequency rather than single-event failure

Nova must therefore govern:

> not only **what decision is allowed**
> but also
> **how decision pressure is allowed to exist over time**

---

# 2. Non-Negotiable Principles

## 2.1 Canonical Nova Identity
Sharpe Nova OS remains:

- a pre-execution decision discipline layer
- a decision-context infrastructure system
- a coordination layer between strategy and execution
- a system that determines whether capital may move

Nova is not:

- an execution engine
- a strategy optimizer
- a signal-producing strategy system
- a queue runner
- an autonomous business workflow agent

---

## 2.2 Governing Order
All Nova behavior must preserve:

> **Decision → Constraint → Outcome**

Outcome is always downstream.

---

## 2.3 Boundary Protection
This governance upgrade must remain canonical and venue-agnostic.

No venue-specific behavior may be written into Nova core.

Any environment-specific handling must remain outside the API in an adapter layer.

---

# 3. Required Governance Layers

## 3.1 Temporal Governance Layer

### Purpose
Govern the rate and timing of decision submission.

### Required Controls
- max decision requests per time window
- cooldown after DENY
- cooldown after HALT
- throttle after repeated constrained outcomes
- quarantine window after integrity failures
- decision-family retry spacing

### Required API Fields
- `decision_count_window`
- `cooldown_state`
- `retry_cooldown_expiry`
- `post_halt_quarantine_expiry`
- `temporal_constraint_triggered`

### Required Outputs
- `DELAY`
- `DENY`
- `HALT`
- `cooldown_active: true|false`

### Rule
A decision may be structurally valid and still be denied due to timing pressure.

---

## 3.2 Loop Integrity Layer

### Purpose
Govern repeated retries, semantic rewording, and programmatic insistence.

### Required Controls
- retry count by decision family
- semantic similarity against prior denials
- distinction between learning retry vs pressure retry
- loop escalation thresholds
- loop quarantine thresholds

### Required API Fields
- `retry_count_by_family`
- `semantic_similarity_to_prior_denial`
- `loop_classification`
  - `learning_retry`
  - `pressure_retry`
  - `ambiguous`
- `pressure_score`
- `loop_integrity_state`

### Required Outputs
- `RETRY_DELAYED`
- `RETRY_BLOCKED`
- `PRESSURE_ESCALATED`
- `HALT_RECOMMENDED`

### Rule
Minor wording changes do not create a new decision identity.

---

## 3.3 Telemetry Integrity Gate

### Purpose
Govern whether telemetry itself is admissible.

### Required Controls
- source freshness validation
- minimum reliability threshold by decision type
- cross-source disagreement detection
- stale-data detection
- degraded telemetry quarantine
- single-source insufficiency checks

### Required API Fields
- `telemetry_reliability_score`
- `telemetry_freshness_state`
- `cross_source_disagreement`
- `telemetry_integrity_state`
- `minimum_required_reliability`
- `telemetry_admissible`

### Required Outputs
- `DELAY` due to stale telemetry
- `DENY` due to insufficient telemetry confidence
- `HALT` due to telemetry degradation

### Rule
Nova must not only ask what telemetry says.
Nova must ask whether telemetry is trustworthy enough to influence permission at all.

---

## 3.4 System State Model

### Purpose
Allow Nova to communicate its own operating posture, not just decision outcomes.

### Required States
- `NORMAL`
- `PRESSURE_ELEVATED`
- `CONSTRAINED_OPERATION`
- `TELEMETRY_DEGRADED`
- `HALT_RECOMMENDED`
- `HALT_ACTIVE`
- `RECOVERY_REVIEW_REQUIRED`

### Required API Fields
- `system_state`
- `state_transition_reason`
- `state_entered_at`
- `state_release_condition`
- `escalation_flag`

### Rule
Nova must be able to say:
- this decision is denied
and separately:
- the system itself is not in a healthy permissioning posture

---

## 3.5 Permission Budgeting Layer

### Purpose
Govern cumulative admission behavior across time.

### Required Controls
- daily admitted exposure budget
- regime-specific permission budget
- exception budget
- leverage expansion budget
- new-risk-class budget

### Required API Fields
- `permission_budget_class`
- `permission_budget_remaining`
- `budget_consumed_by_request`
- `budget_exhausted`
- `exception_budget_remaining`

### Required Outputs
- `REDUCE`
- `DELAY`
- `DENY`
- `HALT_RECOMMENDED` when budget exhaustion compounds with other integrity events

### Rule
Position sizing governs one decision.
Permission budgeting governs system-level admission accumulation.

---

## 3.6 Decision Queue Governance

### Purpose
Govern ordering, batching, and conflict handling across concurrent requests.

### Required Controls
- deterministic queue ordering
- conflict grouping
- priority classification
- batch review triggers
- expiry if regime state changes before evaluation

### Required API Fields
- `queue_priority`
- `queue_position`
- `conflict_group_id`
- `batch_review_required`
- `request_expiry_at`

### Rule
Concurrent decision flow must not weaken cross-decision discipline.

---

## 3.7 Memory Governance Layer

### Purpose
Govern what memory may influence permission and how long that influence remains valid.

### Required Controls
- admissible reflex classes
- memory decay rules
- stale reflex retirement
- confidence weighting for analog events
- controlled upstream memory integration only

### Required API Fields
- `memory_influence_invoked`
- `reflex_memory_class`
- `memory_confidence_weight`
- `memory_age_state`
- `stale_memory_flag`

### Rule
Reflex memory must remain governed recurrence logic, not mythology.

---

## 3.8 Halt Release Governance

### Purpose
Govern how Nova exits HALT state.

### Required Controls
- halt release authority
- required evidence for release
- cooldown after release
- queue invalidation vs re-evaluation policy

### Required API Fields
- `halt_release_required`
- `halt_release_authority`
- `halt_release_evidence`
- `post_release_cooldown`
- `re_evaluation_required`

### Rule
HALT must be strong on entry and governed on exit.

---

## 3.9 Human Intervention Taxonomy

### Purpose
Prevent “human-in-the-loop” from becoming a loophole.

### Required Intervention Types
- `clarification_required`
- `approval_required`
- `exception_authorization_required`
- `override_attempt_detected`
- `halt_release_authorization_required`

### Required API Fields
- `human_intervention_type`
- `human_intervention_required`
- `authorization_scope`
- `intervention_reason`

### Rule
Human participation must be classified, bounded, and auditable.

---

# 4. Proof and Logging Requirements

The following must become visible in Nova’s proof surfaces:

- retry pressure
- telemetry integrity state
- system state at decision time
- permission budget consumed
- queue priority / conflict status
- memory influence class
- halt release requirement where applicable

All proof must still preserve:

> **what was prevented, reshaped, delayed, or denied before capital moved**

---

# 5. Implementation Governance Constraints

## Must Do
- preserve venue-agnostic API behavior
- keep Hyperliquid-specific logic outside Nova core
- treat this as governance expansion, not capability sprawl
- keep outputs machine-legible and auditable

## Must Not Do
- add execution routing into Nova core
- add venue-specific perps logic into canonical API
- let retry handling become negotiation
- let “human review” override structure without explicit classification
- turn Nova into orchestration middleware

---

# 6. Required Implementation Order

Implement in this order:

1. Temporal Governance Layer
2. Loop Integrity Layer
3. Telemetry Integrity Gate
4. System State Model
5. Permission Budgeting Layer
6. Halt Release Governance
7. Human Intervention Taxonomy
8. Decision Queue Governance
9. Memory Governance Layer

This order protects the admission spine first.

---

# 7. Approval Standard

This upgrade is complete only when:

- repeated decision pressure is governed
- telemetry admissibility is explicit
- system state is machine-readable
- cumulative permission is budgeted
- queue order is deterministic
- memory influence is governed
- halt release is auditable
- human intervention is classified
- no venue-specific contamination enters Nova core

---

# 8. Final Directive

Do not build more action.

Build more control.

Nova’s next maturity step is not to become better at doing.

Nova’s next maturity step is to become stronger at governing repeated requests to do.

---

# End of Document
