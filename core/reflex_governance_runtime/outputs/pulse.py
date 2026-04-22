from __future__ import annotations

from typing import Dict, Iterable

# NOTE:
# This runtime is strictly observational.
# It must not modify decision logic, proof output, or system behavior.
# All governance changes must occur through explicit, versioned updates.


def _domain_status(signals: Iterable[Dict[str, object]], domain: str, *, watch_label: str, issue_label: str) -> str:
    domain_signals = [signal for signal in signals if signal.get("domain") == domain]
    if any(signal.get("status") == "escalate" for signal in domain_signals):
        return issue_label
    if any(signal.get("status") == "watch" for signal in domain_signals):
        return watch_label
    return "stable"


def render_reflex_pulse(signals: Iterable[Dict[str, object]]) -> str:
    signal_list = list(signals)
    alert_posture = "none"
    if any(signal.get("status") == "escalate" for signal in signal_list):
        alert_posture = "escalate"
    elif any(signal.get("status") == "watch" for signal in signal_list):
        alert_posture = "watch"

    return "\n".join(
        [
            "REFLEX PULSE OPS",
            "",
            f"Drift: {_domain_status(signal_list, 'reflex', watch_label='watch', issue_label='issue')}",
            f"Classification: {_domain_status(signal_list, 'classification', watch_label='compression risk', issue_label='inconsistency')}",
            f"Proof: {_domain_status(signal_list, 'proof', watch_label='variance', issue_label='determinism issue')}",
            f"Decay: {_domain_status(signal_list, 'decay', watch_label='buildup', issue_label='stale risk')}",
            f"Alert posture: {alert_posture}",
        ]
    )
