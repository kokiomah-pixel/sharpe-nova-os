from __future__ import annotations

from typing import Dict, Iterable, List

# NOTE:
# This runtime is strictly observational.
# It must not modify decision logic, proof output, or system behavior.
# All governance changes must occur through explicit, versioned updates.


def build_reflex_ledger(
    *,
    signals: Iterable[Dict[str, object]],
    escalations: Iterable[Dict[str, object]],
) -> Dict[str, List[Dict[str, object]]]:
    signal_list = list(signals)
    escalation_list = list(escalations)

    return {
        "new_reflex_pressure": [signal for signal in signal_list if signal.get("flag") in {"overactive_reflex", "ineffective_reflex", "reflex_conflict_pattern"}],
        "decayed_reflexes": [signal for signal in signal_list if signal.get("flag") in {"stale_reflex", "dormant_reflex"}],
        "rehabilitated_reflexes": [
            item
            for item in escalation_list
            if isinstance(item.get("resolution"), dict) and item["resolution"].get("action") == "REHABILITATE"
        ],
        "classification_anomalies": [signal for signal in signal_list if signal.get("domain") == "classification"],
        "proof_anomalies": [signal for signal in signal_list if signal.get("domain") == "proof"],
        "active_watch_backlog": [item for item in escalation_list if item.get("state") == "active_watch"],
        "resolved_escalation_history": [item for item in escalation_list if item.get("state") == "resolved"],
    }
