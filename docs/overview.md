# Overview

Sharpe Nova OS is the canonical control-plane interface for pre-execution decision discipline.

It exists to condition capital before execution by returning an authoritative admission state over a machine-readable API.

## What the System Does

- receives a proposed decision
- evaluates admissibility under current constraints
- returns a binding decision surface for downstream systems

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
