from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# NOTE:
# This runtime is strictly observational.
# It must not modify decision logic, proof output, or system behavior.
# All governance changes must occur through explicit, versioned updates.


ALLOWED_RESOLUTION_ACTIONS = {"HOLD", "VALIDATE", "DECAY", "REHABILITATE", "FORMALIZE"}
STRONG_ACTIONS = {"DECAY", "REHABILITATE", "FORMALIZE"}


def _load_json(path: Optional[Path], default: Any) -> Any:
    if path is None or not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Optional[Path], data: Any) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def _recommended_posture(flag: str) -> str:
    if flag in {"classification_inconsistency", "classification_compression", "unclassified_decisions"}:
        return "VALIDATE"
    return "HOLD"


class ReflexGovernanceAlertEngine:
    def __init__(
        self,
        *,
        signals_path: Optional[Path] = None,
        escalations_path: Optional[Path] = None,
    ) -> None:
        self.signals_path = signals_path
        self.escalations_path = escalations_path
        self.signals: Dict[str, Dict[str, Any]] = _load_json(signals_path, {})
        self.escalations: Dict[str, Dict[str, Any]] = _load_json(escalations_path, {})

    def observe_patterns(
        self,
        patterns: List[Dict[str, Any]],
        *,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        statuses: List[Dict[str, Any]] = []
        for pattern in patterns:
            key = str(pattern["pattern_key"])
            prior = self.signals.get(key, {})
            occurrence_count = int(pattern.get("occurrences", 0))
            if occurrence_count <= 1:
                posture = "ignore"
            elif occurrence_count == 2:
                posture = "watch"
            else:
                posture = "escalate"

            signal = {
                "pattern_key": key,
                "flag": pattern["flag"],
                "domain": pattern["domain"],
                "scope": pattern["scope"],
                "window_days": pattern["window_days"],
                "occurrence_count": occurrence_count,
                "status": posture,
                "first_seen": prior.get("first_seen") or pattern.get("first_seen") or timestamp,
                "last_seen": timestamp,
                "recommended_posture": _recommended_posture(str(pattern["flag"])),
                "evidence": pattern.get("evidence", {}),
                "affects_outcomes": bool(pattern.get("affects_outcomes")),
            }
            self.signals[key] = signal
            statuses.append(signal)
            if posture == "escalate":
                self._ensure_escalation(pattern, signal, timestamp)

        _write_json(self.signals_path, self.signals)
        _write_json(self.escalations_path, self.escalations)
        return {"signals": statuses, "escalations": self.reviewable_escalations()}

    def _ensure_escalation(self, pattern: Dict[str, Any], signal: Dict[str, Any], timestamp: str) -> None:
        escalation_id = f"escalation::{signal['pattern_key']}"
        existing = self.escalations.get(escalation_id)
        if existing:
            existing["last_seen"] = timestamp
            existing["signal_status"] = signal["status"]
            existing["recommended_posture"] = signal["recommended_posture"]
            existing["pattern"] = pattern
            return

        self.escalations[escalation_id] = {
            "escalation_id": escalation_id,
            "pattern_key": signal["pattern_key"],
            "flag": signal["flag"],
            "domain": signal["domain"],
            "scope": signal["scope"],
            "window_days": signal["window_days"],
            "signal_status": signal["status"],
            "recommended_posture": signal["recommended_posture"],
            "state": "pending_resolution",
            "created_at": timestamp,
            "last_seen": timestamp,
            "pattern": pattern,
            "resolution": None,
            "watch": None,
        }

    def record_resolution(
        self,
        escalation_id: str,
        *,
        action: str,
        resolved_at: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_action = str(action or "").upper()
        if normalized_action not in ALLOWED_RESOLUTION_ACTIONS:
            raise ValueError("invalid governance resolution action")
        escalation = self.escalations[escalation_id]
        if normalized_action in STRONG_ACTIONS and not self._strong_action_allowed(escalation):
            raise ValueError("strong governance action requires persistent multi-window outcome impact")
        escalation["state"] = "resolved"
        escalation["resolution"] = {
            "action": normalized_action,
            "timestamp_utc": resolved_at or datetime.now(timezone.utc).isoformat(),
            "note": note,
            "pattern_key": escalation["pattern_key"],
            "scope": escalation["scope"],
        }
        _write_json(self.escalations_path, self.escalations)
        return escalation

    def mark_active_watch(
        self,
        escalation_id: str,
        *,
        noted_at: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        escalation = self.escalations[escalation_id]
        escalation["state"] = "active_watch"
        escalation["watch"] = {
            "timestamp_utc": noted_at or datetime.now(timezone.utc).isoformat(),
            "note": note or "continued monitoring",
            "pattern_key": escalation["pattern_key"],
        }
        _write_json(self.escalations_path, self.escalations)
        return escalation

    def reviewable_escalations(self) -> List[Dict[str, Any]]:
        return sorted(self.escalations.values(), key=lambda item: item["created_at"])

    def reviewable_resolution_history(self) -> List[Dict[str, Any]]:
        resolved = []
        for escalation in self.escalations.values():
            resolution = escalation.get("resolution")
            if isinstance(resolution, dict):
                resolved.append(resolution)
        return sorted(resolved, key=lambda item: item["timestamp_utc"])

    def _strong_action_allowed(self, escalation: Dict[str, Any]) -> bool:
        pattern = escalation.get("pattern", {})
        if not isinstance(pattern, dict):
            return False
        # Operator discipline rule:
        # strong governance actions require persistence across governance cycles
        # and demonstrated outcome impact before they are allowed.
        return int(pattern.get("window_days", 0)) >= 30 and bool(pattern.get("affects_outcomes"))
