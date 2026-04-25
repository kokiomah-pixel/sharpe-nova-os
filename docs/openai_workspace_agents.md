# OpenAI Workspace Agent Integration

Workspace agents may propose actions.

Nova determines if those actions are admissible.

## Required Flow

Agent -> Decision Proposal -> Nova -> Execution

## Rules

- Agent must call Nova before execution
- decision_status is binding
- Agent may not treat reasoning as permission
- Agent must retrieve proof when required

## Outcome Handling

ALLOW -> execute  
CONSTRAIN -> adjust, then execute  
DENY / DELAY / HALT / VETO -> do not execute
