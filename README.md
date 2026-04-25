# Sharpe Nova OS — Developer Integration Doctrine

## Repository Role

This repository provides developer doctrine and integration rules for Sharpe Nova OS.

The canonical system, API, proof layer, and runtime live in:

-> https://github.com/kokiomah-pixel/sharpe-nova-os

This repository defines:

- how Nova must be integrated
- how decision admission must be enforced
- how non-bypass behavior is maintained
- how proof must be retrieved and used

This repository does NOT implement Nova.

It defines how Nova is used correctly.

Sharpe Nova OS is a pre-execution decision discipline layer that conditions and verifies whether capital is allowed to move before execution.

## What This Means

Nova does not:

- generate trades
- optimize strategies
- provide discretionary recommendations

Nova determines:

> whether a proposed capital action is allowed to proceed.

## Integration Model

All capital-moving decisions must follow:

Decision -> Nova -> Execution (only if admitted)

Nova returns:

- decision_status (authoritative)
- constraint_effect
- intervention_type
- reproducibility_hash

## Decision Authority

decision_status is binding:

- ALLOW -> proceed
- CONSTRAIN -> adjust before execution
- DENY / DELAY / HALT / VETO -> do not execute

## Non-Bypass Rule

Nova must be called before execution.

- No internal reasoning is considered permission
- No retries around denial states
- No execution without admission

## Proof Requirement

All governed decisions produce:

- decision_id
- decision_status
- constraint_effect
- reproducibility_hash

Proof must be retrievable via `/v1/proof/{decision_id}`

## Repository Purpose

This repo defines:

- correct integration patterns
- continuous decision loops
- agent enforcement rules
- workplace agent governance
- MCP tool usage

This repo does NOT:

- host Nova runtime
- modify Nova behavior
- provide execution systems

## Canonical System

https://github.com/kokiomah-pixel/sharpe-nova-os
