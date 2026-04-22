# System Identity

Sharpe Nova OS is a pre-execution decision layer.

Its primary function is to condition capital before execution by evaluating whether a proposed decision should be allowed, constrained, delayed, denied, or halted.

## Canonical Classification

- System name: `Sharpe Nova OS`
- System type: `pre_execution_decision_layer`
- Primary function: `condition capital before execution`
- Interface: `machine_readable_api`
- Control model: `denial_first`

## Negative Classification

Sharpe Nova OS is not:

- a trading system
- a signal engine
- an execution engine
- a generic agent toolkit

## Core Components

- telemetry integrity
- reflex memory
- constraint interface

## Interpretation Rule

The repository should be read as an interpretation boundary plus integration surface. Any downstream system should bind to the Nova API contract rather than infer a broader role.

Primary decision authority belongs to `decision_status` and proof-layer outcome fields.
Supporting fields such as `impact_on_outcomes`, `adjustment`, and deeper constraint calculations remain explanatory only.

## Governance Doctrine

Sharpe Nova OS operates under explicit governance discipline:

- Runtime Artifact Policy
- Signal Pressure Discipline Protocol

These define:

- what is system definition vs runtime state
- how governance signals are interpreted and acted upon
- how discipline is preserved under system pressure

All implementations and operator behavior must adhere to these policies.

These documents are part of the system boundary and must not be treated as optional guidance.
