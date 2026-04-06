# Nova State Model

Nova exposes a system state composed of:

- epoch (time bucket)
- timestamp (request time)
- regime (system condition)
- action_policy (decision constraints before execution)
- reflex_memory (retained discipline state)

The Nova State Model defines how decision context is structured, not how capital is validated for exposure.
Reflex Memory is operational retained discipline: governed memory that conditions decisions before execution, not a latent-learning system.

---

## Epoch

- Derived from UTC time
- Updates hourly
- Represents a coarse system clock

Example:
epoch = int(timestamp / 3600)

---

## Timestamp

- Generated on each live API call
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

Defines what decision state is allowed before execution:

- allow_new_risk
- allow_position_increase
- allow_risk_reduction
- allow_position_decrease

---

## Reflex Memory

Reflex Memory formalizes retained discipline in machine-readable form.

Canonical schema objects:

- `reflex_memory_state`
- `reflex_proof`
- `reflex_registry_entry`

Launch-safe registry fields:

- origin
- failure_class
- activation_condition
- behavioral_effect
- persistence_state
- validation_status

Proof surfaces expose:

- what intervention class occurred
- what failure class was addressed
- what decision was altered
- why the intervention happened

This boundary is intentionally thin. It makes retained memory governable without expanding into full decay, rehabilitation, or conflict arbitration scaffolding before exposure.

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

time-aware → state-aware decision control
