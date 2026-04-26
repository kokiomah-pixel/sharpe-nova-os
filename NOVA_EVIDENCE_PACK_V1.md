# Nova Evidence Pack v1

This evidence pack demonstrates decision behavior under controlled and historical conditions.
It is not a representation of live performance.

## Captured Nova Decision Constraint Context (2026-03-16 UTC)

- Timestamp: 2026-03-16T16:00:00Z
- Epoch: 2461
- Configured Decision Regime: Elevated Fragility
- New Risk: Allowed
- Position Increase: Not Allowed
- Risk Reduction: Allowed
- Position Decrease: Allowed

---

## VETO Examples

### Controlled Configured Decision Regime Capture: Stress

### Scenario 1
- Name: Stress ETH Trade
- Params: intent=trade, asset=ETH, size=10000
- Configured Decision Regime: Stress
- Severity: high
- Governed constraint: Do not initiate new risk. Only reduce or exit existing exposure.
- Action Policy: allow_new_risk=false, allow_risk_reduction=true, allow_position_increase=false, allow_position_decrease=true
- Outcome: VETO

### Scenario 2
- Name: Stress Liquidity Deployment
- Params: intent=deploy_liquidity, asset=ETH, size=10000
- Configured Decision Regime: Stress
- Severity: high
- Governed constraint: Do not initiate new risk. Only reduce or exit existing exposure.
- Action Policy: allow_new_risk=false, allow_risk_reduction=true, allow_position_increase=false, allow_position_decrease=true
- Outcome: VETO

### Scenario 3
- Name: Stress BTC Trade
- Params: intent=trade, asset=BTC, size=50000
- Configured Decision Regime: Stress
- Severity: high
- Governed constraint: Do not initiate new risk. Only reduce or exit existing exposure.
- Action Policy: allow_new_risk=false, allow_risk_reduction=true, allow_position_increase=false, allow_position_decrease=true
- Outcome: VETO

---

## CONSTRAIN Examples

### Controlled Configured Decision Regime Capture: Elevated Fragility

### Scenario 1
- Name: Elevated ETH Trade
- Params: intent=trade, asset=ETH, size=10000
- Configured Decision Regime: Elevated Fragility
- Severity: medium
- Governed constraint: Reduce exposure and tighten controls before execution.
- Action Policy: allow_new_risk=true, allow_risk_reduction=true, allow_position_increase=false, allow_position_decrease=true
- Outcome: CONSTRAIN

### Scenario 2
- Name: Elevated Liquidity Deployment
- Params: intent=deploy_liquidity, asset=ETH, size=10000
- Configured Decision Regime: Elevated Fragility
- Severity: medium
- Governed constraint: Reduce size and avoid low-liquidity venues.
- Action Policy: allow_new_risk=true, allow_risk_reduction=true, allow_position_increase=false, allow_position_decrease=true
- Outcome: CONSTRAIN

---

## ALLOW Example

### Controlled Configured Decision Regime Capture: Stable

### Scenario 1
- Name: Stable ETH Trade
- Params: intent=trade, asset=ETH, size=10000
- Configured Decision Regime: Stable
- Severity: low
- Governed output: Proceed under normal risk controls.
- Action Policy: allow_new_risk=true, allow_risk_reduction=true, allow_position_increase=true, allow_position_decrease=true
- Outcome: ALLOW
