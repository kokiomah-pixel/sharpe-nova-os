# Overview

Sharpe Nova OS is the canonical control-plane interface for pre-execution decision discipline.

It exists to condition capital before execution by returning an authoritative admission state over a machine-readable API.

The interaction surface is two-step:

- `/v1/context` governs the decision and returns `decision_id`
- `/v1/proof/{decision_id}` returns the authoritative audit surface

## What the System Does

- receives a proposed decision
- evaluates admissibility under current constraints
- returns a binding decision surface for downstream systems
- provides verifiable proof of the final governing outcome

## What the System Does Not Do

- generate trades
- optimize strategy
- execute orders
- act as a generic toolkit

## Core Model

Sharpe Nova OS is denial-first.

The system is designed so that:

- refusal states are explicit
- governance layers are visible
- downstream systems inherit discipline through the API contract
- execution proceeds only after decision admission
