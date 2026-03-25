# Nova State Model

Nova exposes a system state composed of:

- epoch (time bucket)
- timestamp (request time)
- regime (system condition)
- action_policy (execution constraints)

---

## Epoch

- Derived from UTC time
- Updates hourly
- Represents a coarse system clock

Example:
epoch = int(timestamp / 3600)

---

## Timestamp

- Generated per request in live mode
- Used for:
  - freshness
  - signature generation
  - auditability

---

## Regime

Represents current system conditions:

| Regime | Meaning |
|--------|--------|
| Stable | normal conditions |
| Elevated Fragility | deteriorating conditions |
| Stress | high-risk conditions |

---

## Action Policy

Defines what execution is allowed:

- allow_new_risk
- allow_position_increase
- allow_risk_reduction
- allow_position_decrease

---

## Key Concept

Nova does not tell you what to do.

It tells you what is allowed.

---

## Call Frequency

Recommended:

- call Nova before every capital action
- cache per epoch if needed
- refresh immediately on regime-sensitive operations

---

## Future Evolution (Planned)

Nova will evolve toward:

- regime-triggered state changes (not only time-based)
- explicit transition tracking
- cross-system synchronization

This will move Nova from:

time-aware → state-aware execution control
