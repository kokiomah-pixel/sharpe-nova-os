# Sharpe Nova OS — Governance Rollout Policy (v1.0)

## Status

REQUIRED — Nova API Governance Activation Reference

---

## 1. Purpose

This document defines how governance layers are activated, inspected, and rolled out within Sharpe Nova OS.

It ensures that:
- governance is explicit and deterministic
- rollout occurs without mutating Nova core behavior
- Nova remains:

> a pre-execution decision discipline layer that conditions capital before it moves

---

## 2. Core Principle

### Governance is Activated Per Key

There is:
- NO global governance mode
- NO environment flag inside Nova core
- NO implicit activation

All governance behavior is:

> explicitly configured per API key

### Default Behavior

If a governance block is unset:

It is treated as disabled.

This preserves:
- backward compatibility
- baseline admission behavior
- deterministic rollout control

---

## 3. Activation Model

Governance layers activate only when present in the key configuration.

Example:

```json
{
  "temporal_governance": {},
  "loop_integrity": {}
}
```

If absent:

```json
{}
```

---

## 4. Governance Layers

Nova governance is composed of the following layers:

1. Temporal Governance
2. Loop Integrity
3. Telemetry Integrity
4. System State
5. Permission Budgeting
6. Halt Release Governance
7. Human Intervention Taxonomy
8. Decision Queue Governance
9. Memory Governance

Each layer:
- operates independently
- is opt-in
- does not require other layers to function

---

## 5. Rollout Matrix

Nova rollout progresses through key-level activation states:

## Activation Matrix (Corrected Interpretation)

- baseline -> public/default usage
- controlled_governance -> limited/internal rollout
- full_governance -> institutional readiness
- hyperliquid_proving_ground -> private Architect-controlled proving only

### Baseline

Definition:
No governance layers enabled

Behavior:
- minimal admission enforcement
- default Nova API behavior

### Controlled Governance

Definition:
Core enforcement layers enabled:
- Temporal Governance
- Loop Integrity
- Telemetry Integrity

Optional:
- System State
- Permission Budgeting

Behavior:
- timing control
- retry discipline
- telemetry validation

### Full Governance

Definition:
All governance layers enabled

Behavior:
- full admission discipline
- system-wide constraint visibility
- complete governance surface

### Hyperliquid Proving Ground

Definition:
Full governance plus stricter thresholds

Behavior:
- adversarial stress testing
- elevated constraint sensitivity
- high-pressure validation environment

Critical constraint:

Hyperliquid:
- does NOT define Nova
- does NOT modify Nova core
- is ONLY a proving environment

## Non-Exposure Rule — Proving Environments

Proving environments must not be exposed externally.

This includes:
- no public API keys
- no onboarding flows referencing proving environments
- no documentation positioning proving environments as usable tiers

All proving-ground activity is internal to Nova system validation.

Violation of this rule creates:
- category confusion
- operator misuse
- governance misinterpretation

### Hyperliquid Consumption Order

Hyperliquid must consume Nova outputs in the following order:

1. Submit a decision and receive the full Nova context.
2. Respect `decision_status` first.
3. Treat all other fields as explanatory and non-optional.

Hyperliquid must NOT:
- interpret fields instead of `decision_status`
- optimize around fields
- selectively apply fields

This prevents enforcement from degrading into field-based heuristics.

### Custom

Definition:
Any non-standard combination of governance layers

---

## 6. Inspection Surfaces

### `/v1/key-info`

Returns:

```json
{
  "active_governance_layers": []
}
```

Purpose:
- immediate visibility into enabled governance

### `/v1/governance-profile`

Returns:

```json
{
  "active_governance_layers": [],
  "thresholds": {},
  "environment_classification": "baseline",
  "proving_ground": false
}
```

When a proving ground is configured, Nova may also expose:

```json
{
  "proving_ground_name": "hyperliquid"
}
```

Purpose:
- full inspection of governance configuration
- environment classification derived from configuration
- no runtime mode switching

### Proving Ground Fields

- `proving_ground`: boolean  
- `proving_ground_name`: string (optional)

### Interpretation

- `proving_ground = true` indicates the key is operating in a **private internal proving environment**
- `proving_ground_name` identifies the proving domain (e.g., `"hyperliquid"`)

### Constraint

Proving ground classification does not imply:
- public availability
- external access
- productization

It is strictly an internal classification for governance validation.

---

## 7. Environment Classification

Environment classification is descriptive and derived from key configuration.

| Classification | Description | Access Level |
|----------------------------------|--------------------------------------------------|---------------------|
| baseline | No governance layers active | Public / Default |
| controlled_governance | Partial governance (Sprints 1–3/5) | Limited / Internal |
| full_governance | All governance layers active (Sprints 1–9) | Internal / Pre-prod |
| hyperliquid_proving_ground | Full governance + adversarial validation | **Private Only** |
| custom | Non-standard configuration | Case-by-case |

Classification:
- is descriptive
- is not used for logic branching
- does not alter admission behavior

## Hyperliquid Proving Ground — Classification

The Hyperliquid environment is a **private proving ground**.

It is not:
- a public deployment environment
- a product tier
- an externally accessible governance mode
- a distribution surface for Nova

It is:
- an internal Architect-controlled proving environment
- an adversarial testing domain for governance validation
- a runtime consumer of Nova API outputs under real market pressure

### Operational Constraints

- Access is restricted to a single internal proving key.
- This key is not distributed, documented for public use, or exposed as part of onboarding.
- No external operator or allocator interacts directly with this environment.

### Purpose

The Hyperliquid proving ground exists to:

- stress-test Nova governance layers under real conditions
- validate denial-first behavior under pressure
- generate reflex memory candidates
- confirm system-state transitions under adversarial input

### Category Protection Rule

Hyperliquid must never define Nova’s category.

All external framing must remain:

> Sharpe Nova OS is a pre-execution decision discipline layer.

Not:
- a trading system
- a Hyperliquid system
- a perps execution engine

### Enforcement Rule

Hyperliquid consumes Nova outputs.

It does not:
- interpret governance fields
- override `decision_status`
- introduce execution-side logic into Nova

Nova remains the sole source of decision authority.

---

## 8. Example Key Profiles

Canonical reference file:

`examples/governance_key_profiles.json`

Includes:
- `baseline_key`
- `controlled_key`
- `full_governance_key`
- `hyperliquid_proving_ground_key`

These serve as:
- onboarding references
- testing inputs
- allocator demonstration artifacts

---

## 9. Enforcement Boundary

Governance rollout must NOT:
- introduce execution logic
- introduce strategy optimization
- introduce signal generation
- introduce environment-based branching

Decision-consuming adapters must NOT:
- replace `decision_status` with local heuristics
- downgrade explanatory governance fields into optional hints
- apply only a subset of Nova's decision surface

### Decision Response Completeness

For `/v1/context`, Nova's decision surface must remain complete across every decision path.

Every decision response must include:
- `decision_status`
- `constraint_trace`
- `system_state`
- relevant governance fields for the active control plane

This completeness requirement applies to:
- admission paths
- rejection paths
- delay paths
- reduce paths
- halt paths

If omission re-enters through partial decision responses, ambiguity re-enters with it.

Critical rule:

> Nova conditions capital before execution. It does not decide what to execute.

---

## 10. System Integrity Guarantee

This rollout model ensures:
- deterministic activation
- auditable governance
- consistent operator behavior
- preservation of Nova's category

---

## Final Statement

Sharpe Nova OS governance rollout is:

> a key-level activation system that enables progressive enforcement without compromising Nova's identity as decision discipline infrastructure

---

## Final Clarification

Hyperliquid is not a deployment environment.

It is a proving ground.

Nova is not defined by where it is tested.

Nova is defined by how it governs decisions before execution.

---

# End of Document
