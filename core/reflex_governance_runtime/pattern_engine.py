from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

# NOTE:
# This runtime is strictly observational.
# It must not modify decision logic, proof output, or system behavior.
# All governance changes must occur through explicit, versioned updates.


SHORT_WINDOW_DAYS = 7
MEDIUM_WINDOW_DAYS = 30


def _parse_timestamp(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _windowed_records(records: Iterable[Dict[str, Any]], now: datetime, days: int) -> List[Dict[str, Any]]:
    cutoff = now - timedelta(days=days)
    retained = []
    for record in records:
        observed_at = _parse_timestamp(str(record.get("observed_at") or ""), now)
        if observed_at >= cutoff:
            retained.append({**record, "_observed_at": observed_at})
    return retained


def _build_pattern(
    *,
    flag: str,
    domain: str,
    scope: str,
    window_days: int,
    records: List[Dict[str, Any]],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    ordered = sorted(records, key=lambda item: item["_observed_at"])
    return {
        "pattern_key": f"{flag}:{scope}:{window_days}",
        "flag": flag,
        "domain": domain,
        "scope": scope,
        "window_days": window_days,
        "occurrences": len(ordered),
        "first_seen": ordered[0]["_observed_at"].isoformat(),
        "last_seen": ordered[-1]["_observed_at"].isoformat(),
        "evidence": evidence,
        "affects_outcomes": any(bool(item.get("outcome_influenced")) for item in ordered),
    }


def _classification_tuple(record: Dict[str, Any]) -> tuple[str, ...]:
    classification = record.get("classification", [])
    if not isinstance(classification, list):
        classification = [classification]
    return tuple(sorted(str(item) for item in classification if str(item).strip()))


def _reflex_domain_patterns(records: List[Dict[str, Any]], window_days: int) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    reflex_occurrences: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    ineffective_records: List[Dict[str, Any]] = []
    conflict_records: List[Dict[str, Any]] = []
    registered_reflexes: Dict[str, List[datetime]] = defaultdict(list)

    for record in records:
        observed_at = record["_observed_at"]
        reflex_ids = record.get("reflex_ids", [])
        if not isinstance(reflex_ids, list):
            reflex_ids = [reflex_ids]
        for reflex_id in reflex_ids:
            reflex_occurrences[str(reflex_id)].append(record)
        if reflex_ids and str(record.get("intervention_type") or "none") == "none":
            ineffective_records.append(record)
        if len(reflex_ids) > 1:
            conflict_records.append(record)
        for reflex_id in record.get("registered_reflex_ids", []) or []:
            registered_reflexes[str(reflex_id)].append(observed_at)

    for reflex_id, items in reflex_occurrences.items():
        if len(items) >= 3:
            patterns.append(
                _build_pattern(
                    flag="overactive_reflex",
                    domain="reflex",
                    scope=reflex_id,
                    window_days=window_days,
                    records=items,
                    evidence={"reflex_id": reflex_id, "activation_count": len(items)},
                )
            )

    if len(ineffective_records) >= 3:
        patterns.append(
            _build_pattern(
                flag="ineffective_reflex",
                domain="reflex",
                scope="global",
                window_days=window_days,
                records=ineffective_records,
                evidence={"count": len(ineffective_records)},
            )
        )

    if len(conflict_records) >= 3:
        patterns.append(
            _build_pattern(
                flag="reflex_conflict_pattern",
                domain="reflex",
                scope="global",
                window_days=window_days,
                records=conflict_records,
                evidence={"count": len(conflict_records)},
            )
        )

    if window_days >= MEDIUM_WINDOW_DAYS and records:
        now = max(record["_observed_at"] for record in records)
        stale_records: List[Dict[str, Any]] = []
        dormant_records: List[Dict[str, Any]] = []
        for reflex_id, timestamps in registered_reflexes.items():
            last_seen = max(timestamps)
            if last_seen <= now - timedelta(days=MEDIUM_WINDOW_DAYS):
                stale_records.extend(
                    record for record in records if reflex_id in (record.get("registered_reflex_ids") or [])
                )
                dormant_records.extend(
                    record for record in records if reflex_id in (record.get("registered_reflex_ids") or [])
                )
        if len(stale_records) >= 3:
            patterns.append(
                _build_pattern(
                    flag="stale_reflex",
                    domain="decay",
                    scope="global",
                    window_days=window_days,
                    records=stale_records,
                    evidence={"count": len(stale_records)},
                )
            )
        if len(dormant_records) >= 3:
            patterns.append(
                _build_pattern(
                    flag="dormant_reflex",
                    domain="reflex",
                    scope="global",
                    window_days=window_days,
                    records=dormant_records,
                    evidence={"count": len(dormant_records)},
                )
            )

        active_reflexes = {reflex_id for reflex_id, items in reflex_occurrences.items() if items}
        retained_reflexes = {reflex_id for reflex_id in registered_reflexes if reflex_id}
        inactive_count = len(retained_reflexes - active_reflexes)
        if retained_reflexes and inactive_count >= 3:
            patterns.append(
                _build_pattern(
                    flag="memory_bloat_risk",
                    domain="decay",
                    scope="global",
                    window_days=window_days,
                    records=records,
                    evidence={
                        "retained_reflex_count": len(retained_reflexes),
                        "inactive_retained_reflex_count": inactive_count,
                    },
                )
            )

    return patterns


def _classification_domain_patterns(records: List[Dict[str, Any]], window_days: int) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    all_classifications = Counter()
    unclassified_records: List[Dict[str, Any]] = []
    by_signature: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for record in records:
        classification = _classification_tuple(record)
        by_signature[str(record.get("normalized_signature") or "")].append(record)
        if classification:
            all_classifications.update(classification)
        if not classification and (
            record.get("reflex_ids")
            or str(record.get("decision_status") or "").upper() != "ALLOW"
            or bool(record.get("memory_influence_present"))
        ):
            unclassified_records.append(record)

    total_classified = sum(all_classifications.values())
    if total_classified >= 3:
        top_label, top_count = all_classifications.most_common(1)[0]
        if top_count / total_classified >= 0.8:
            relevant_records = [
                record for record in records if top_label in _classification_tuple(record)
            ]
            patterns.append(
                _build_pattern(
                    flag="classification_compression",
                    domain="classification",
                    scope=top_label,
                    window_days=window_days,
                    records=relevant_records,
                    evidence={"classification": top_label, "share": round(top_count / total_classified, 4)},
                )
            )

    if len(unclassified_records) >= 3:
        patterns.append(
            _build_pattern(
                flag="unclassified_decisions",
                domain="classification",
                scope="global",
                window_days=window_days,
                records=unclassified_records,
                evidence={"count": len(unclassified_records)},
            )
        )

    for signature, items in by_signature.items():
        classification_shapes = {_classification_tuple(item) for item in items}
        if len(items) >= 2 and len(classification_shapes) > 1:
            patterns.append(
                _build_pattern(
                    flag="classification_inconsistency",
                    domain="classification",
                    scope=signature,
                    window_days=window_days,
                    records=items,
                    evidence={
                        "normalized_signature": signature,
                        "classification_variants": [list(shape) for shape in sorted(classification_shapes)],
                    },
                )
            )

    return patterns


def _proof_domain_patterns(records: List[Dict[str, Any]], window_days: int) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    by_signature: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    mismatches: List[Dict[str, Any]] = []

    for record in records:
        by_signature[str(record.get("normalized_signature") or "")].append(record)
        if str(record.get("context_decision_status") or "") != str(record.get("proof_decision_status") or ""):
            mismatches.append(record)

    for signature, items in by_signature.items():
        decision_statuses = {str(item.get("decision_status") or "") for item in items}
        intervention_types = {str(item.get("intervention_type") or "") for item in items}
        reproducibility_hashes = {str(item.get("reproducibility_hash") or "") for item in items}
        if len(items) >= 2 and (len(decision_statuses) > 1 or len(intervention_types) > 1):
            patterns.append(
                _build_pattern(
                    flag="determinism_violation",
                    domain="proof",
                    scope=signature,
                    window_days=window_days,
                    records=items,
                    evidence={"decision_statuses": sorted(decision_statuses), "intervention_types": sorted(intervention_types)},
                )
            )
        if len(items) >= 2 and len(reproducibility_hashes) > 1:
            patterns.append(
                _build_pattern(
                    flag="reproducibility_failure",
                    domain="proof",
                    scope=signature,
                    window_days=window_days,
                    records=items,
                    evidence={"hash_count": len(reproducibility_hashes)},
                )
            )

    if len(mismatches) >= 2:
        patterns.append(
            _build_pattern(
                flag="proof_mismatch",
                domain="proof",
                scope="global",
                window_days=window_days,
                records=mismatches,
                evidence={"count": len(mismatches)},
            )
        )

    return patterns


def _decay_patterns_from_resolutions(
    records: List[Dict[str, Any]],
    window_days: int,
    resolution_history: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if not resolution_history:
        return []

    attempts_by_scope = defaultdict(list)
    for resolution in resolution_history:
        if str(resolution.get("action") or "") == "REHABILITATE":
            attempts_by_scope[str(resolution.get("scope") or "global")].append(resolution)

    patterns: List[Dict[str, Any]] = []
    for scope, attempts in attempts_by_scope.items():
        related = [
            record for record in records
            if scope == "global"
            or scope in (record.get("reflex_ids") or [])
            or scope == str(record.get("normalized_signature") or "")
        ]
        if len(related) >= 3:
            patterns.append(
                _build_pattern(
                    flag="failed_rehabilitation",
                    domain="decay",
                    scope=scope,
                    window_days=window_days,
                    records=related,
                    evidence={"rehabilitation_attempts": len(attempts)},
                )
            )
    return patterns


def detect_structural_patterns(
    records: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    resolution_history: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    all_records = list(records)
    patterns: List[Dict[str, Any]] = []

    for window_days in (SHORT_WINDOW_DAYS, MEDIUM_WINDOW_DAYS):
        scoped = _windowed_records(all_records, current_time, window_days)
        if not scoped:
            continue
        patterns.extend(_reflex_domain_patterns(scoped, window_days))
        patterns.extend(_classification_domain_patterns(scoped, window_days))
        patterns.extend(_proof_domain_patterns(scoped, window_days))
        patterns.extend(_decay_patterns_from_resolutions(scoped, window_days, resolution_history))

    return patterns
