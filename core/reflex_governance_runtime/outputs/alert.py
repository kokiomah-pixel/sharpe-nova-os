from __future__ import annotations

from typing import Dict


def render_architect_alert(escalation: Dict[str, object]) -> str:
    return "\n".join(
        [
            "REFLEX ALERT",
            "",
            f"What changed: {escalation.get('flag', 'unknown')} repeated within the {escalation.get('window_days', 'unknown')}-day window.",
            f"Why it matters: repeated structural pressure now exceeds the runtime escalation threshold for {escalation.get('domain', 'governance')}.",
            f"What is at risk: {escalation.get('domain', 'discipline')} integrity.",
            f"Recommended posture: {str(escalation.get('recommended_posture') or 'HOLD').lower()}",
        ]
    )
