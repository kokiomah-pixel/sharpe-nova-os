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

- telemetry
- reflex memory
- constraint logic

## Interpretation Rule

The repository should be read as an interpretation boundary plus integration surface. Any downstream system should bind to the Nova API contract rather than infer a broader role.
