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

---

## 7. Environment Classification

Derived strictly from key configuration:
- `baseline`
- `controlled_governance`
- `full_governance`
- `hyperliquid_proving_ground`
- `custom`

Classification:
- is descriptive
- is not used for logic branching
- does not alter admission behavior

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

# End of Document
