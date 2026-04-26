# OpenAI Workspace Agent Integration

OpenAI workspace agents may propose actions.

Nova determines decision admission before capital-moving execution.

Nova remains external, model-agnostic, and binding.

## Required Flow

Agent -> Decision Proposal -> Nova -> Execution

## Rules

- Agent must call `/v1/context` before execution
- `decision_status` is binding
- Agent may not treat its own reasoning as permission
- Agent may retrieve `/v1/proof/{decision_id}` when proof-backed verification is required
- Refusal states must fail closed

## Outcome Handling

ALLOW -> execute  
CONSTRAIN -> adjust, then execute  
DENY / DELAY / HALT / VETO -> do not execute
