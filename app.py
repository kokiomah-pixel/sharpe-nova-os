import json
import os
import hmac
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any, List

import redis
import fakeredis
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from core.reflex_memory import (
    ReflexMemoryState,
    build_registry,
    select_active_entry,
    validate_reflex_memory_state,
)
from core.reflex_memory.proof import build_reflex_proof
from key_manager import (
    activate_or_renew_key,
    deactivate_key_by_stripe_customer_id,
    deactivate_keys_for_owner,
    find_key_by_owner,
    find_key_by_stripe_customer_id,
    generate_api_key,
    load_keys,
    store_key,
    suspend_key_by_stripe_customer_id,
    suspend_keys_for_owner,
)

try:
    import stripe
except Exception:  # pragma: no cover - runtime fallback when stripe isn't installed
    stripe = None

load_dotenv()


def get_current_timestamp() -> str:
    fixed = os.getenv("NOVA_TIMESTAMP_UTC")
    if fixed:
        return fixed
    return get_current_datetime().isoformat()


def get_current_datetime() -> datetime:
    fixed = os.getenv("NOVA_NOW_UTC")
    if fixed:
        normalized = fixed.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def get_current_epoch() -> int:
    fixed = os.getenv("NOVA_EPOCH")
    if fixed:
        return int(fixed)
    now = get_current_datetime()
    return int(now.timestamp() // 3600)  # hourly epoch bucket

app = FastAPI(
    title="Sharpe Nova OS API",
    version="1.1.0",
    description="Decision-context infrastructure for autonomous capital systems."
)

SIGNING_SECRET = os.getenv("NOVA_SIGNING_SECRET", "replace_me")
CONSTITUTION_VERSION = os.getenv("NOVA_CONSTITUTION_VERSION", "v1.0")
DEFAULT_REGIME = os.getenv("NOVA_REGIME", "Elevated Fragility")

# Backward compatibility for your current single-key setup
LEGACY_API_KEY = os.getenv("NOVA_API_KEY", "")

# New v1 key registry
NOVA_KEYS_JSON = os.getenv("NOVA_KEYS_JSON", "")

# Usage tracking
# - Stored in-memory for fast access
# - Persisted to disk so counters survive restarts (configurable via NOVA_USAGE_FILE)
USAGE_TRACKING: Dict[str, Dict[str, Any]] = {}
USAGE_FILE = Path(os.getenv("NOVA_USAGE_FILE", ".usage.json")).expanduser()

# Billing policy
BILLABLE_ENDPOINTS = {"/v1/context", "/v1/regime", "/v1/epoch"}
NON_BILLABLE_ENDPOINTS = {"/health", "/v1/key-info", "/v1/usage"}
ADMIN_ONLY_ENDPOINTS = {"/v1/usage/reset"}

NOVA_REDIS_URL = os.getenv("NOVA_REDIS_URL", "")
REDIS_CLIENT: Optional[redis.Redis] = None

# Optional in-memory rate-limit state (per-key)
# Keys in the registry may include a `rate_limit` object:
# {"window_seconds": 60, "max_calls": 30}
RATE_LIMIT_STATE: Dict[str, Dict[str, Any]] = {}
PROCESSED_EVENTS = set()
PROCESSED_EVENTS_FILE = Path(os.getenv("STRIPE_PROCESSED_EVENTS_FILE", ".stripe_events.json")).expanduser()
PROCESSED_EVENTS_LOCK = Lock()
STRIPE_AUDIT_FILE = Path(os.getenv("NOVA_STRIPE_AUDIT_FILE", "stripe_webhook_audit.jsonl")).expanduser()
REJECTION_LEDGER: List[Dict[str, Any]] = []
EXCEPTION_REGISTER: List[Dict[str, Any]] = []
HALT_SIGNAL_STATE: Dict[str, List[Dict[str, Any]]] = {}
DECISION_ADMISSION_STATE: Dict[str, List[Dict[str, Any]]] = {}
TEMPORAL_GOVERNANCE_STATE: Dict[str, Dict[str, Any]] = {}
LOOP_INTEGRITY_STATE: Dict[str, Dict[str, Any]] = {}
SYSTEM_STATE_REGISTRY: Dict[str, Dict[str, Any]] = {}
PERMISSION_BUDGET_STATE: Dict[str, Dict[str, Any]] = {}
HALT_RELEASE_STATE: Dict[str, Dict[str, Any]] = {}
DECISION_QUEUE_STATE: Dict[str, Dict[str, Any]] = {}

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_EMERGING_ID = os.getenv("STRIPE_PRICE_EMERGING_ID", "price_emerging_id")
PRICE_CORE_ID = os.getenv("STRIPE_PRICE_CORE_ID", "price_core_id")
PRICE_ENTERPRISE_ID = os.getenv("STRIPE_PRICE_ENTERPRISE_ID", "price_enterprise_id")

if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def _load_processed_events() -> set[str]:
    if not PROCESSED_EVENTS_FILE.exists():
        return set()
    try:
        raw = json.loads(PROCESSED_EVENTS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {str(item) for item in raw if item}
    except Exception:
        return set()
    return set()


def _persist_processed_events(events: set[str]) -> None:
    PROCESSED_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROCESSED_EVENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(events), indent=2), encoding="utf-8")
    tmp.replace(PROCESSED_EVENTS_FILE)


def _is_duplicate_event(event_id: str) -> bool:
    with PROCESSED_EVENTS_LOCK:
        if event_id in PROCESSED_EVENTS:
            return True
        PROCESSED_EVENTS.add(event_id)
        _persist_processed_events(PROCESSED_EVENTS)
        return False


PROCESSED_EVENTS.update(_load_processed_events())


def log_stripe_audit(
    *,
    event_id: str,
    event_type: str,
    customer_email: str = "",
    stripe_customer_id: str = "",
    action: str,
    result: str,
    api_key: str = "",
    tier: str = "",
    reason: str = "",
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "event_id": event_id,
        "event_type": event_type,
        "customer_email": customer_email,
        "stripe_customer_id": stripe_customer_id,
        "action": action,
        "result": result,
        "api_key": api_key,
        "tier": tier,
        "reason": reason,
    }
    try:
        STRIPE_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STRIPE_AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception as exc:
        print(f"[WARN] Stripe audit log write failed: {exc}", file=sys.stderr)


def _get_redis_client() -> Optional[redis.Redis]:
    global REDIS_CLIENT
    if REDIS_CLIENT is not None:
        return REDIS_CLIENT

    if not NOVA_REDIS_URL:
        return None

    if NOVA_REDIS_URL.startswith("fakeredis://"):
        REDIS_CLIENT = fakeredis.FakeRedis()
    else:
        REDIS_CLIENT = redis.from_url(NOVA_REDIS_URL, decode_responses=True)

    return REDIS_CLIENT


def _write_usage_file(data: Dict[str, Any]) -> None:
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = USAGE_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        tmp.replace(USAGE_FILE)
    except Exception:
        # best-effort persistence, don't break the app if disk writes fail
        pass


def _load_usage_file() -> Dict[str, Dict[str, Any]]:
    if not USAGE_FILE.exists():
        return {}
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_redis_usage(api_key: str) -> Dict[str, Any]:
    client = _get_redis_client()
    if not client:
        return {}

    key = f"usage:{api_key}"
    result = client.hgetall(key)
    if not result:
        return {}

    usage = {
        "total_calls": int(result.get("total_calls", 0)),
        "last_seen": result.get("last_seen"),
        "by_endpoint": {},
    }

    # endpoint breakdown is stored in a hash per key
    endpoint_key = f"usage:{api_key}:endpoints"
    raw_by_endpoint = client.hgetall(endpoint_key)
    by_endpoint = {}
    for k, v in raw_by_endpoint.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8", errors="ignore")
        by_endpoint[k] = int(v)
    usage["by_endpoint"] = by_endpoint
    return usage


def _persist_redis_usage(api_key: str, usage: Dict[str, Any]) -> None:
    client = _get_redis_client()
    if not client:
        return

    key = f"usage:{api_key}"
    client.hset(key, mapping={
        "total_calls": usage.get("total_calls", 0),
        "last_seen": usage.get("last_seen"),
    })

    endpoint_key = f"usage:{api_key}:endpoints"
    if usage.get("by_endpoint"):
        client.hset(endpoint_key, mapping={k: v for k, v in usage.get("by_endpoint", {}).items()})


def _persist_usage() -> None:
    # persist to disk unless Redis is configured
    if _get_redis_client():
        return
    _write_usage_file(USAGE_TRACKING)


# Initialize in-memory tracking from disk
if not NOVA_REDIS_URL:
    USAGE_TRACKING.update(_load_usage_file())


def track_usage(api_key: str, endpoint: str) -> None:
    now = get_current_datetime().isoformat()

    client = _get_redis_client()
    if client:
        key = f"usage:{api_key}"
        endpoint_key = f"usage:{api_key}:endpoints"
        pipe = client.pipeline()
        pipe.hincrby(key, "total_calls", 1)
        pipe.hset(key, "last_seen", now)
        pipe.hincrby(endpoint_key, endpoint, 1)
        pipe.execute()
        return

    record = USAGE_TRACKING.setdefault(api_key, {
        "total_calls": 0,
        "by_endpoint": {},
        "last_seen": None,
    })
    record["total_calls"] += 1
    record["by_endpoint"][endpoint] = record["by_endpoint"].get(endpoint, 0) + 1
    record["last_seen"] = now
    _persist_usage()


def load_key_registry() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}

    if NOVA_KEYS_JSON.strip():
        try:
            parsed = json.loads(NOVA_KEYS_JSON)
            if isinstance(parsed, dict):
                registry.update(parsed)
        except json.JSONDecodeError:
            raise RuntimeError("Invalid NOVA_KEYS_JSON format")

    # Merge Stripe/manual keys from keys.json
    external_keys = load_keys()
    for api_key, record in external_keys.items():
        if not isinstance(record, dict):
            continue
        merged = dict(record)
        merged.setdefault("owner", "external")
        merged.setdefault("tier", "free")
        merged.setdefault("status", "active")
        if "monthly_quota" not in merged and "quota" in merged:
            merged["monthly_quota"] = merged.get("quota")
        merged.setdefault("monthly_quota", 1000)
        merged.setdefault("allowed_endpoints", [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/key-info",
            "/v1/usage",
            "/health",
        ])
        registry[api_key] = merged

    # fallback so your current live key keeps working
    if LEGACY_API_KEY:
        registry.setdefault(LEGACY_API_KEY, {
            "owner": "legacy",
            "tier": "admin",
            "status": "active",
            "monthly_quota": 1000000,
            "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/key-info",
            "/v1/usage",
            "/v1/usage/reset",
            "/health",
        ]
        })

    return registry


def get_api_key_from_headers(authorization: Optional[str], x_api_key: Optional[str]) -> str:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1).strip()
    raise HTTPException(status_code=401, detail="Missing API key")


def get_key_record(api_key: str) -> Dict[str, Any]:
    registry = load_key_registry()

    if api_key not in registry:
        raise HTTPException(status_code=403, detail="Invalid API key")

    record = registry[api_key]

    status = (record.get("status") or "").lower()
    if status != "active":
        if status == "suspended":
            raise HTTPException(status_code=403, detail="Suspended API key")
        if status == "inactive":
            raise HTTPException(status_code=403, detail="Inactive API key")
        raise HTTPException(status_code=403, detail="API key is not active")

    return record


def require_entitlement(
    request: Request,
    authorization: Optional[str],
    x_api_key: Optional[str],
) -> Dict[str, Any]:
    api_key = get_api_key_from_headers(authorization, x_api_key)
    record = get_key_record(api_key)

    path = request.url.path
    allowed = record.get("allowed_endpoints", [])

    if path not in allowed:
        raise HTTPException(status_code=403, detail="API key not allowed for this endpoint")

    if path in ADMIN_ONLY_ENDPOINTS and record.get("tier") != "admin":
        raise HTTPException(status_code=403, detail="Admin tier required for this endpoint")

    monthly_quota = record.get("monthly_quota")

    # Monthly quota only applies to billable endpoints
    if path in BILLABLE_ENDPOINTS:
        if isinstance(monthly_quota, int) and monthly_quota >= 0:
            total_calls = 0
            client = _get_redis_client()
            if client:
                total_calls = int(client.hget(f"usage:{api_key}", "total_calls") or 0)
            else:
                total_calls = USAGE_TRACKING.get(api_key, {}).get("total_calls", 0)

            if total_calls >= monthly_quota:
                raise HTTPException(status_code=429, detail="Monthly quota exceeded")

    # Optional per-key rate limiting
    rate_limit = record.get("rate_limit")
    if isinstance(rate_limit, dict):
        window_seconds = int(rate_limit.get("window_seconds", 0))
        max_calls = int(rate_limit.get("max_calls", 0))
        if window_seconds > 0 and max_calls > 0:
            client = _get_redis_client()
            if client:
                key = f"ratelimit:{api_key}"
                count = client.incr(key)
                if count == 1:
                    client.expire(key, window_seconds)
                if count > max_calls:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")
            else:
                now = datetime.now(timezone.utc)
                state = RATE_LIMIT_STATE.setdefault(api_key, {
                    "window_start": now,
                    "count": 0,
                })

                window_start = state.get("window_start")
                if not isinstance(window_start, datetime):
                    window_start = now
                delta = (now - window_start).total_seconds()
                if delta >= window_seconds:
                    state["window_start"] = now
                    state["count"] = 0

                if state["count"] >= max_calls:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")

                state["count"] += 1

    # Billable endpoints count towards quota and usage
    if path in BILLABLE_ENDPOINTS:
        track_usage(api_key, path)

    return {
        "api_key": api_key,
        "owner": record.get("owner"),
        "tier": record.get("tier"),
        "monthly_quota": monthly_quota,
        "allowed_endpoints": allowed,
        "key_record": record,
    }


def sign_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(
        SIGNING_SECRET.encode("utf-8"),
        encoded,
        hashlib.sha256
    ).hexdigest()


AMBIGUOUS_LANGUAGE_TERMS = {
    "small size",
    "looks safe",
    "good setup",
    "reasonable risk",
}
BYPASS_PHRASES = {
    "skip validation",
    "just execute",
    "route directly",
}
RETROACTIVE_PHRASES = {
    "retroactive",
    "after execution",
    "retroactive log",
}
OVERRIDE_PHRASES = {
    "override",
}
DELAY_PHRASES = {
    "delay",
    "delayed logging",
}
RISK_INCREASING_INTENTS = {
    "trade",
    "deploy_liquidity",
    "open_position",
    "increase_position",
}
STABLECOIN_ASSETS = {"USDC", "USDT", "DAI", "FRAX", "LUSD"}
VALIDATOR_ASSETS = {"stETH", "rETH", "cbETH"}
GOVERNANCE_ASSETS = {"LDO", "COMP", "MKR", "AAVE", "UNI"}


def _normalize_text(value: Optional[str]) -> str:
    return " ".join((value or "").strip().lower().split())


def _request_snapshot(
    *,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
) -> Dict[str, Any]:
    return {
        "intent": intent,
        "asset": asset,
        "size": size_raw,
        "venue": venue,
        "strategy": strategy,
    }


def _build_request_id(timestamp: str, snapshot: Dict[str, Any]) -> str:
    raw = json.dumps({"timestamp": timestamp, "snapshot": snapshot}, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _decision_family(intent: Optional[str], asset: Optional[str]) -> str:
    normalized_intent = _normalize_text(intent) or "unknown_intent"
    normalized_asset = _normalize_text(asset) or "unknown_asset"
    return f"{normalized_intent}:{normalized_asset}"


def _decision_direction(intent: Optional[str]) -> str:
    normalized_intent = _normalize_text(intent)
    if normalized_intent in RISK_INCREASING_INTENTS:
        return "risk_increasing"
    if normalized_intent in {"reduce_position", "exit_position", "decrease_position"}:
        return "risk_reducing"
    return "general"


def _isoformat_optional(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _queue_governance_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("decision_queue_governance")
    if not isinstance(config, dict):
        return {
            "request_ttl_seconds": 0,
            "expire_on_regime_change": True,
            "expire_on_epoch_change": True,
        }
    return {
        "request_ttl_seconds": max(int(config.get("request_ttl_seconds", 0) or 0), 0),
        "expire_on_regime_change": bool(config.get("expire_on_regime_change", True)),
        "expire_on_epoch_change": bool(config.get("expire_on_epoch_change", True)),
    }


def _default_queue_fields() -> Dict[str, Any]:
    return {
        "queue_priority": "normal",
        "queue_position": 1,
        "conflict_group_id": None,
        "batch_review_required": False,
        "request_expiry_at": None,
    }


def _default_memory_fields() -> Dict[str, Any]:
    return {
        "memory_influence_invoked": False,
        "reflex_memory_class": None,
        "memory_confidence_weight": None,
        "memory_age_state": "not_applicable",
        "stale_memory_flag": False,
    }


def _memory_governance_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("memory_governance")
    if not isinstance(config, dict):
        config = {}

    raw_admissible = config.get(
        "admissible_reflex_classes",
        [
            "fragility_escalation",
            "liquidity_deterioration",
            "baseline_monitoring",
        ],
    )
    if not isinstance(raw_admissible, list):
        raw_admissible = [raw_admissible]

    confidence_weights = config.get("confidence_weights", {})
    if not isinstance(confidence_weights, dict):
        confidence_weights = {}

    return {
        "admissible_reflex_classes": {
            str(item).strip() for item in raw_admissible if str(item).strip()
        },
        "memory_age_seconds": max(float(config.get("memory_age_seconds", 0.0) or 0.0), 0.0),
        "stale_after_seconds": max(float(config.get("stale_after_seconds", 3600.0) or 3600.0), 0.0),
        "aging_after_ratio": min(max(float(config.get("aging_after_ratio", 0.5) or 0.5), 0.0), 1.0),
        "confidence_weights": {
            str(key): min(max(float(value), 0.0), 1.0)
            for key, value in confidence_weights.items()
            if str(key).strip()
        },
    }


def _reflex_memory_class(entry: Optional[Any]) -> Optional[str]:
    if entry is None:
        return None
    return str(getattr(entry, "failure_class", None) or "").strip() or None


def _memory_confidence_weight(
    *,
    entry: Any,
    config: Dict[str, Any],
) -> float:
    validation_status = str(getattr(entry, "validation_status", "observed") or "observed")
    configured = config.get("confidence_weights", {})
    if validation_status in configured:
        return float(configured[validation_status])
    defaults = {
        "validated": 1.0,
        "observed": 0.5,
    }
    return float(defaults.get(validation_status, 0.5))


def _memory_age_state(
    *,
    age_seconds: float,
    stale_after_seconds: float,
    aging_after_ratio: float,
) -> str:
    if stale_after_seconds <= 0:
        return "fresh"
    if age_seconds >= stale_after_seconds:
        return "stale"
    if age_seconds >= stale_after_seconds * aging_after_ratio:
        return "aging"
    return "fresh"


def _weighted_adjustment_factor(base_factor: Optional[float], confidence_weight: float) -> Optional[float]:
    if base_factor is None:
        return None
    bounded_base = min(max(float(base_factor), 0.0), 1.0)
    bounded_confidence = min(max(float(confidence_weight), 0.0), 1.0)
    return round(1.0 - ((1.0 - bounded_base) * bounded_confidence), 4)


def _evaluate_memory_governance(
    *,
    record: Dict[str, Any],
    entry: Optional[Any],
) -> Dict[str, Any]:
    if entry is None:
        return {
            **_default_memory_fields(),
            "admissible": False,
            "blocked_reason": "no_active_reflex_entry",
        }

    config = _memory_governance_config(record)
    memory_class = _reflex_memory_class(entry)
    age_seconds = config["memory_age_seconds"]
    age_state = _memory_age_state(
        age_seconds=age_seconds,
        stale_after_seconds=config["stale_after_seconds"],
        aging_after_ratio=config["aging_after_ratio"],
    )
    stale_flag = age_state == "stale"
    admissible = memory_class in config["admissible_reflex_classes"]
    confidence_weight = _memory_confidence_weight(entry=entry, config=config)
    blocked_reason = None
    if not admissible:
        blocked_reason = "inadmissible_reflex_class"
    elif stale_flag:
        blocked_reason = "stale_memory"

    return {
        "memory_influence_invoked": admissible and not stale_flag,
        "reflex_memory_class": memory_class,
        "memory_confidence_weight": confidence_weight,
        "memory_age_state": age_state,
        "stale_memory_flag": stale_flag,
        "admissible": admissible,
        "blocked_reason": blocked_reason,
    }


def _queue_priority(intent: Optional[str]) -> str:
    direction = _decision_direction(intent)
    if direction == "risk_reducing":
        return "high"
    if direction == "risk_increasing":
        return "normal"
    return "low"


def _queue_priority_rank(priority: str) -> int:
    ranks = {"high": 0, "normal": 1, "low": 2}
    return ranks.get(priority, 1)


def _queue_state_for_api_key(api_key: str) -> Dict[str, Any]:
    state = DECISION_QUEUE_STATE.setdefault(
        api_key,
        {
            "entries": [],
            "next_sequence": 1,
        },
    )
    state.setdefault("entries", [])
    state.setdefault("next_sequence", 1)
    return state


def _queue_conflict_key(intent: Optional[str], asset: Optional[str]) -> str:
    normalized_asset = _normalize_text(asset)
    if normalized_asset:
        return f"asset:{normalized_asset}"
    return f"family:{_decision_family(intent, asset)}"


def _queue_conflict_group_id(conflict_key: str) -> str:
    return hashlib.sha256(conflict_key.encode("utf-8")).hexdigest()[:12]


def _prune_queue_entries(
    *,
    entries: List[Dict[str, Any]],
    now: datetime,
    current_regime: str,
    current_epoch: int,
) -> List[Dict[str, Any]]:
    active_entries: List[Dict[str, Any]] = []
    for entry in entries:
        expiry_at = entry.get("expiry_at")
        if isinstance(expiry_at, datetime) and expiry_at <= now:
            continue
        if entry.get("expire_on_regime_change", True) and entry.get("regime") != current_regime:
            continue
        if entry.get("expire_on_epoch_change", True) and entry.get("epoch") != current_epoch:
            continue
        active_entries.append(entry)
    return active_entries[-25:]


def _evaluate_queue_governance(
    *,
    api_key: str,
    record: Dict[str, Any],
    intent: Optional[str],
    asset: Optional[str],
    request_id: str,
    timestamp: str,
    epoch: int,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    config = _queue_governance_config(record)
    expiry_at: Optional[datetime] = None
    if config["request_ttl_seconds"] > 0:
        expiry_at = now + timedelta(seconds=config["request_ttl_seconds"])

    state = _queue_state_for_api_key(api_key)
    state["entries"] = _prune_queue_entries(
        entries=state.get("entries", []),
        now=now,
        current_regime=DEFAULT_REGIME,
        current_epoch=epoch,
    )

    priority = _queue_priority(intent)
    conflict_key = _queue_conflict_key(intent, asset)
    sequence = int(state.get("next_sequence", 1))
    state["next_sequence"] = sequence + 1
    candidate = {
        "request_id": request_id,
        "snapshot": snapshot,
        "intent": _normalize_text(intent),
        "asset": _normalize_text(asset),
        "priority": priority,
        "conflict_key": conflict_key,
        "timestamp_utc": timestamp,
        "expiry_at": expiry_at,
        "regime": DEFAULT_REGIME,
        "epoch": epoch,
        "expire_on_regime_change": config["expire_on_regime_change"],
        "expire_on_epoch_change": config["expire_on_epoch_change"],
        "sequence": sequence,
    }
    state["entries"].append(candidate)

    ordered_entries = sorted(
        state["entries"],
        key=lambda entry: (
            _queue_priority_rank(str(entry.get("priority"))),
            int(entry.get("sequence", 0)),
            str(entry.get("request_id")),
        ),
    )
    conflict_entries = [entry for entry in state["entries"] if entry.get("conflict_key") == conflict_key]
    return {
        "queue_priority": priority,
        "queue_position": next(
            index for index, entry in enumerate(ordered_entries, start=1) if entry.get("sequence") == sequence
        ),
        "conflict_group_id": _queue_conflict_group_id(conflict_key) if len(conflict_entries) > 1 else None,
        "batch_review_required": len(conflict_entries) > 1,
        "request_expiry_at": _isoformat_optional(expiry_at),
    }


def _temporal_governance_config(record: Dict[str, Any]) -> Dict[str, int]:
    config = record.get("temporal_governance")
    if not isinstance(config, dict):
        return {}
    return {
        "window_seconds": max(int(config.get("window_seconds", 0) or 0), 0),
        "max_requests_per_window": max(int(config.get("max_requests_per_window", 0) or 0), 0),
        "deny_cooldown_seconds": max(int(config.get("deny_cooldown_seconds", 0) or 0), 0),
        "halt_cooldown_seconds": max(int(config.get("halt_cooldown_seconds", 0) or 0), 0),
        "retry_spacing_seconds": max(int(config.get("retry_spacing_seconds", 0) or 0), 0),
        "halt_threshold": max(int(config.get("halt_threshold", 0) or 0), 0),
    }


def _temporal_state_for_api_key(api_key: str) -> Dict[str, Any]:
    state = TEMPORAL_GOVERNANCE_STATE.setdefault(
        api_key,
        {
            "request_timestamps": [],
            "family_request_timestamps": {},
            "retry_cooldown_expiry": {},
            "deny_cooldown_expiry": None,
            "post_halt_quarantine_expiry": None,
        },
    )
    state.setdefault("request_timestamps", [])
    state.setdefault("family_request_timestamps", {})
    state.setdefault("retry_cooldown_expiry", {})
    state.setdefault("deny_cooldown_expiry", None)
    state.setdefault("post_halt_quarantine_expiry", None)
    return state


def _prune_temporal_state(
    *,
    state: Dict[str, Any],
    now: datetime,
    window_seconds: int,
) -> None:
    if window_seconds <= 0:
        return
    cutoff = now - timedelta(seconds=window_seconds)
    state["request_timestamps"] = [
        timestamp for timestamp in state.get("request_timestamps", []) if timestamp >= cutoff
    ]
    family_timestamps = state.get("family_request_timestamps", {})
    for family, timestamps in list(family_timestamps.items()):
        retained = [timestamp for timestamp in timestamps if timestamp >= cutoff]
        if retained:
            family_timestamps[family] = retained
        else:
            family_timestamps.pop(family, None)


def _default_temporal_fields() -> Dict[str, Any]:
    cooldown_state = {
        "active": False,
        "reason": "none",
        "deny_cooldown_active": False,
        "halt_quarantine_active": False,
    }
    return {
        "decision_count_window": {
            "window_seconds": 0,
            "max_requests": 0,
            "request_count": 0,
            "decision_family": None,
            "family_request_count": 0,
        },
        "cooldown_state": cooldown_state,
        "cooldown_active": False,
        "retry_cooldown_expiry": None,
        "post_halt_quarantine_expiry": None,
        "temporal_constraint_triggered": False,
    }


def _loop_integrity_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("loop_integrity")
    if not isinstance(config, dict):
        return {}
    return {
        "pressure_similarity_threshold": float(config.get("pressure_similarity_threshold", 0.75) or 0.75),
        "ambiguous_similarity_threshold": float(config.get("ambiguous_similarity_threshold", 0.4) or 0.4),
        "retry_block_threshold": max(int(config.get("retry_block_threshold", 2) or 2), 1),
        "pressure_escalation_threshold": max(int(config.get("pressure_escalation_threshold", 3) or 3), 1),
        "denial_history_limit": max(int(config.get("denial_history_limit", 10) or 10), 1),
    }


def _default_loop_fields() -> Dict[str, Any]:
    return {
        "retry_count_by_family": 0,
        "semantic_similarity_to_prior_denial": 0.0,
        "loop_classification": None,
        "pressure_score": 0.0,
        "loop_integrity_state": "clear",
    }


def _telemetry_integrity_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("telemetry_integrity")
    if not isinstance(config, dict):
        return {}
    return {
        "stale_after_seconds": float(config.get("stale_after_seconds", 300) or 300),
        "default_min_reliability": float(config.get("default_min_reliability", 0.7) or 0.7),
        "risk_increasing_min_reliability": float(config.get("risk_increasing_min_reliability", 0.8) or 0.8),
        "risk_reducing_min_reliability": float(config.get("risk_reducing_min_reliability", 0.6) or 0.6),
        "disagreement_threshold": float(config.get("disagreement_threshold", 0.35) or 0.35),
        "halt_disagreement_threshold": float(config.get("halt_disagreement_threshold", 0.7) or 0.7),
        "halt_on_degraded": bool(config.get("halt_on_degraded", False)),
    }


def _default_telemetry_fields() -> Dict[str, Any]:
    return {
        "telemetry_reliability_score": None,
        "telemetry_freshness_state": "not_evaluated",
        "cross_source_disagreement": False,
        "telemetry_integrity_state": "not_evaluated",
        "minimum_required_reliability": None,
        "telemetry_admissible": True,
    }


def _permission_budget_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("permission_budgeting")
    if not isinstance(config, dict):
        return {}
    return {
        "default_daily_budget": float(config.get("default_daily_budget", config.get("daily_budget", 0.0)) or 0.0),
        "risk_increasing_daily_budget": float(
            config.get("risk_increasing_daily_budget", config.get("default_daily_budget", config.get("daily_budget", 0.0))) or 0.0
        ),
        "risk_reducing_daily_budget": float(
            config.get("risk_reducing_daily_budget", config.get("default_daily_budget", config.get("daily_budget", 0.0))) or 0.0
        ),
        "exception_budget": int(config.get("exception_budget", 0) or 0),
        "low_remaining_ratio": float(config.get("low_remaining_ratio", 0.2) or 0.2),
        "delay_on_exhaustion": bool(config.get("delay_on_exhaustion", False)),
        "halt_on_compounded_pressure": bool(config.get("halt_on_compounded_pressure", True)),
    }


def _default_permission_budget_fields() -> Dict[str, Any]:
    return {
        "permission_budget_class": None,
        "permission_budget_remaining": None,
        "budget_consumed_by_request": 0.0,
        "budget_exhausted": False,
        "exception_budget_remaining": None,
    }


def _permission_budget_class(intent: Optional[str]) -> str:
    normalized_intent = _normalize_text(intent)
    if normalized_intent in RISK_INCREASING_INTENTS:
        return "risk_increasing"
    if normalized_intent in {"reduce_position", "exit_position", "decrease_position"}:
        return "risk_reducing"
    return "general"


def _permission_budget_limit(config: Dict[str, Any], budget_class: str) -> float:
    if budget_class == "risk_increasing":
        return float(config.get("risk_increasing_daily_budget", 0.0) or 0.0)
    if budget_class == "risk_reducing":
        return float(config.get("risk_reducing_daily_budget", 0.0) or 0.0)
    return float(config.get("default_daily_budget", 0.0) or 0.0)


def _permission_budget_state_for_api_key(api_key: str) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    state = PERMISSION_BUDGET_STATE.setdefault(
        api_key,
        {
            "as_of_date": today,
            "budget_classes": {},
            "exception_budget_consumed": 0,
        },
    )
    if state.get("as_of_date") != today:
        state["as_of_date"] = today
        state["budget_classes"] = {}
        state["exception_budget_consumed"] = 0
    state.setdefault("budget_classes", {})
    state.setdefault("exception_budget_consumed", 0)
    return state


def _evaluate_permission_budget(
    *,
    api_key: str,
    record: Dict[str, Any],
    intent: Optional[str],
    decision_status: str,
    admitted_size: Optional[float],
) -> Dict[str, Any]:
    config = _permission_budget_config(record)
    base_fields = _default_permission_budget_fields()
    budget_class = _permission_budget_class(intent)
    if not config:
        return {
            **base_fields,
            "configured": False,
            "triggered": False,
            "action": None,
            "status_code": 200,
            "adjusted_size": admitted_size,
        }

    state = _permission_budget_state_for_api_key(api_key)
    class_state = state["budget_classes"].setdefault(budget_class, {"consumed": 0.0})
    budget_limit = _permission_budget_limit(config, budget_class)
    consumed_before = float(class_state.get("consumed", 0.0) or 0.0)
    remaining_before = max(round(budget_limit - consumed_before, 2), 0.0)
    exception_budget_remaining = max(
        int(config.get("exception_budget", 0)) - int(state.get("exception_budget_consumed", 0)),
        0,
    )
    result = {
        "configured": True,
        "triggered": False,
        "action": None,
        "status_code": 200,
        "adjusted_size": admitted_size,
        "permission_budget_class": budget_class,
        "permission_budget_remaining": remaining_before,
        "budget_consumed_by_request": 0.0,
        "budget_exhausted": remaining_before <= 0.0,
        "exception_budget_remaining": exception_budget_remaining,
    }

    if decision_status == "VETO" or admitted_size is None or admitted_size <= 0:
        return result

    if remaining_before <= 0.0:
        result.update({
            "triggered": True,
            "action": "DELAY" if config["delay_on_exhaustion"] else "DENY",
            "status_code": 429,
            "adjusted_size": 0.0,
            "permission_budget_remaining": 0.0,
            "budget_exhausted": True,
        })
        return result

    if admitted_size > remaining_before:
        result.update({
            "triggered": True,
            "action": "REDUCE",
            "adjusted_size": remaining_before,
            "budget_consumed_by_request": remaining_before,
            "permission_budget_remaining": 0.0,
            "budget_exhausted": True,
        })
        class_state["consumed"] = round(consumed_before + remaining_before, 2)
        return result

    consumed_by_request = round(admitted_size, 2)
    remaining_after = max(round(remaining_before - consumed_by_request, 2), 0.0)
    class_state["consumed"] = round(consumed_before + consumed_by_request, 2)
    result.update({
        "budget_consumed_by_request": consumed_by_request,
        "permission_budget_remaining": remaining_after,
        "budget_exhausted": remaining_after <= 0.0,
    })
    return result


def _parse_telemetry_source_scores(value: Optional[str]) -> List[float]:
    if not value:
        return []
    scores: List[float] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ":" in part:
            _, score_text = part.rsplit(":", 1)
        else:
            score_text = part
        try:
            scores.append(float(score_text))
        except ValueError:
            continue
    return scores


def _telemetry_request_class(intent: Optional[str]) -> str:
    normalized_intent = _normalize_text(intent)
    if normalized_intent in RISK_INCREASING_INTENTS:
        return "risk_increasing"
    if normalized_intent in {"reduce_position", "exit_position", "decrease_position"}:
        return "risk_reducing"
    return "default"


def _evaluate_telemetry_integrity(
    *,
    record: Dict[str, Any],
    intent: Optional[str],
    telemetry_age_seconds: Optional[float],
    telemetry_reliability: Optional[float],
    telemetry_source_scores: Optional[str],
) -> Dict[str, Any]:
    config = _telemetry_integrity_config(record)
    base_fields = _default_telemetry_fields()
    if not config:
        return {
            **base_fields,
            "configured": False,
            "triggered": False,
            "action": None,
            "status_code": 200,
        }

    request_class = _telemetry_request_class(intent)
    if request_class == "risk_increasing":
        minimum_required_reliability = config["risk_increasing_min_reliability"]
    elif request_class == "risk_reducing":
        minimum_required_reliability = config["risk_reducing_min_reliability"]
    else:
        minimum_required_reliability = config["default_min_reliability"]

    source_scores = _parse_telemetry_source_scores(telemetry_source_scores)
    reliability_score = telemetry_reliability
    if reliability_score is None and source_scores:
        reliability_score = round(sum(source_scores) / len(source_scores), 3)

    freshness_state = "fresh"
    if telemetry_age_seconds is None:
        freshness_state = "unknown"
    elif telemetry_age_seconds > config["stale_after_seconds"]:
        freshness_state = "stale"

    disagreement_delta = 0.0
    if len(source_scores) >= 2:
        disagreement_delta = max(source_scores) - min(source_scores)
    cross_source_disagreement = disagreement_delta >= config["disagreement_threshold"]

    telemetry_integrity_state = "telemetry_clear"
    telemetry_admissible = True
    triggered = False
    action = None
    status_code = 200

    if freshness_state == "stale":
        telemetry_integrity_state = "stale_telemetry"
        telemetry_admissible = False
        triggered = True
        action = "DELAY"
        status_code = 429
    elif cross_source_disagreement:
        telemetry_integrity_state = "cross_source_disagreement"
        telemetry_admissible = False
        triggered = True
        action = "DENY"
        status_code = 429
        if config["halt_on_degraded"] and disagreement_delta >= config["halt_disagreement_threshold"]:
            telemetry_integrity_state = "telemetry_degraded"
            action = "HALT"
            status_code = 409
    elif reliability_score is None or reliability_score < minimum_required_reliability:
        telemetry_integrity_state = "insufficient_reliability"
        telemetry_admissible = False
        triggered = True
        action = "DENY"
        status_code = 429

    return {
        "configured": True,
        "triggered": triggered,
        "action": action,
        "status_code": status_code,
        "telemetry_reliability_score": reliability_score,
        "telemetry_freshness_state": freshness_state,
        "cross_source_disagreement": cross_source_disagreement,
        "telemetry_integrity_state": telemetry_integrity_state,
        "minimum_required_reliability": minimum_required_reliability,
        "telemetry_admissible": telemetry_admissible,
    }


def _loop_state_for_api_key(api_key: str) -> Dict[str, Any]:
    state = LOOP_INTEGRITY_STATE.setdefault(
        api_key,
        {
            "family_retry_counts": {},
            "family_denials": {},
        },
    )
    state.setdefault("family_retry_counts", {})
    state.setdefault("family_denials", {})
    return state


def _normalize_size_bucket(size_raw: Optional[str]) -> str:
    normalized = _normalize_text(size_raw)
    if not normalized:
        return "missing"
    try:
        value = abs(float(size_raw))
    except (TypeError, ValueError):
        return "non_numeric"
    if value >= 250000:
        return "oversized"
    if value >= 50000:
        return "large"
    if value >= 5000:
        return "medium"
    if value > 0:
        return "small"
    return "zero"


def _tokenize(value: Optional[str]) -> set[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return set()
    return {token for token in normalized.replace(":", " ").split(" ") if token}


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _loop_similarity(current_snapshot: Dict[str, Any], prior_snapshot: Dict[str, Any]) -> float:
    score = 0.25
    if _normalize_size_bucket(current_snapshot.get("size")) == _normalize_size_bucket(prior_snapshot.get("size")):
        score += 0.35

    current_size_raw = _normalize_text(current_snapshot.get("size"))
    prior_size_raw = _normalize_text(prior_snapshot.get("size"))
    if current_size_raw and current_size_raw == prior_size_raw:
        score += 0.15

    strategy_similarity = _jaccard_similarity(
        _tokenize(current_snapshot.get("strategy")),
        _tokenize(prior_snapshot.get("strategy")),
    )
    score += 0.15 * strategy_similarity

    current_venue = _normalize_text(current_snapshot.get("venue"))
    prior_venue = _normalize_text(prior_snapshot.get("venue"))
    if current_venue and prior_venue and current_venue == prior_venue:
        score += 0.10

    return round(min(score, 1.0), 3)


def _record_loop_denial(
    *,
    api_key: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    constraint_category: str,
) -> None:
    state = _loop_state_for_api_key(api_key)
    family = _decision_family(intent, asset)
    history = state["family_denials"].setdefault(family, [])
    history.append({
        "timestamp_utc": get_current_timestamp(),
        "snapshot": _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy),
        "constraint_category": constraint_category,
    })
    state["family_denials"][family] = history[-10:]


def _evaluate_loop_integrity(
    *,
    api_key: str,
    record: Dict[str, Any],
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
) -> Dict[str, Any]:
    config = _loop_integrity_config(record)
    base_fields = _default_loop_fields()
    if not config:
        return {
            **base_fields,
            "configured": False,
            "triggered": False,
            "action": None,
            "status_code": 200,
        }

    state = _loop_state_for_api_key(api_key)
    family = _decision_family(intent, asset)
    prior_denials = state["family_denials"].get(family, [])
    if not prior_denials:
        return {
            **base_fields,
            "configured": True,
            "triggered": False,
            "action": None,
            "status_code": 200,
        }

    current_snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    most_similar_denial = max(
        prior_denials,
        key=lambda entry: _loop_similarity(current_snapshot, entry["snapshot"]),
    )
    similarity = _loop_similarity(current_snapshot, most_similar_denial["snapshot"])
    retry_count = int(state["family_retry_counts"].get(family, 0)) + 1
    state["family_retry_counts"][family] = retry_count

    if similarity >= config["pressure_similarity_threshold"]:
        classification = "pressure_retry"
    elif similarity >= config["ambiguous_similarity_threshold"]:
        classification = "ambiguous"
    else:
        classification = "learning_retry"

    pressure_score = round(min(1.0, similarity + (retry_count * 0.12)), 3)
    result = {
        "configured": True,
        "triggered": False,
        "action": None,
        "status_code": 200,
        "retry_count_by_family": retry_count,
        "semantic_similarity_to_prior_denial": similarity,
        "loop_classification": classification,
        "pressure_score": pressure_score,
        "loop_integrity_state": classification,
    }

    if classification == "learning_retry":
        return result

    if classification == "pressure_retry" and retry_count >= config["pressure_escalation_threshold"]:
        result.update({
            "triggered": True,
            "action": "PRESSURE_ESCALATED",
            "status_code": 409,
            "loop_integrity_state": "pressure_escalated",
        })
        return result

    if retry_count >= config["retry_block_threshold"]:
        result.update({
            "triggered": True,
            "action": "RETRY_BLOCKED",
            "status_code": 409,
            "loop_integrity_state": "retry_blocked",
        })
        return result

    result.update({
        "triggered": True,
        "action": "RETRY_DELAYED",
        "status_code": 429,
        "loop_integrity_state": "retry_delayed",
    })
    return result


def _evaluate_temporal_governance(
    *,
    api_key: str,
    record: Dict[str, Any],
    intent: Optional[str],
    asset: Optional[str],
) -> Dict[str, Any]:
    config = _temporal_governance_config(record)
    base_fields = _default_temporal_fields()
    if not config:
        return {
            **base_fields,
            "configured": False,
            "triggered": False,
            "action": None,
            "reason": None,
            "status_code": 200,
        }

    now = get_current_datetime()
    state = _temporal_state_for_api_key(api_key)
    family = _decision_family(intent, asset)
    window_seconds = config["window_seconds"]
    max_requests = config["max_requests_per_window"]
    deny_cooldown_seconds = config["deny_cooldown_seconds"]
    halt_cooldown_seconds = config["halt_cooldown_seconds"]
    retry_spacing_seconds = config["retry_spacing_seconds"]
    halt_threshold = config["halt_threshold"] or (max_requests + 1 if max_requests > 0 else 0)

    _prune_temporal_state(state=state, now=now, window_seconds=window_seconds)

    request_timestamps = state.get("request_timestamps", [])
    family_timestamps = state.get("family_request_timestamps", {})
    family_history = family_timestamps.get(family, [])
    retry_expiry = state.get("retry_cooldown_expiry", {}).get(family)
    deny_expiry = state.get("deny_cooldown_expiry")
    halt_expiry = state.get("post_halt_quarantine_expiry")

    if retry_expiry and retry_expiry <= now:
        state["retry_cooldown_expiry"].pop(family, None)
        retry_expiry = None
    if deny_expiry and deny_expiry <= now:
        state["deny_cooldown_expiry"] = None
        deny_expiry = None
    if halt_expiry and halt_expiry <= now:
        state["post_halt_quarantine_expiry"] = None
        halt_expiry = None

    decision_count_window = {
        "window_seconds": window_seconds,
        "max_requests": max_requests,
        "request_count": len(request_timestamps),
        "decision_family": family,
        "family_request_count": len(family_history),
    }
    cooldown_state = {
        "active": False,
        "reason": "none",
        "deny_cooldown_active": False,
        "halt_quarantine_active": False,
    }

    def build_result(
        *,
        triggered: bool,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        status_code: int = 200,
    ) -> Dict[str, Any]:
        return {
            "configured": True,
            "triggered": triggered,
            "action": action,
            "reason": reason,
            "status_code": status_code,
            "decision_count_window": decision_count_window,
            "cooldown_state": cooldown_state,
            "cooldown_active": cooldown_state["active"],
            "retry_cooldown_expiry": _isoformat_optional(retry_expiry),
            "post_halt_quarantine_expiry": _isoformat_optional(halt_expiry),
            "temporal_constraint_triggered": triggered,
        }

    if halt_expiry:
        cooldown_state.update({
            "active": True,
            "reason": "halt_quarantine_active",
            "halt_quarantine_active": True,
        })
        return build_result(triggered=True, action="HALT", reason="post_halt_quarantine_active", status_code=409)

    if retry_expiry:
        cooldown_state.update({
            "active": True,
            "reason": "retry_spacing_active",
        })
        return build_result(triggered=True, action="DELAY", reason="retry_spacing_active", status_code=429)

    if deny_expiry:
        cooldown_state.update({
            "active": True,
            "reason": "deny_cooldown_active",
            "deny_cooldown_active": True,
        })
        return build_result(triggered=True, action="DENY", reason="deny_cooldown_active", status_code=429)

    projected_request_count = len(request_timestamps) + 1
    projected_family_count = len(family_history) + 1
    decision_count_window.update({
        "request_count": projected_request_count,
        "family_request_count": projected_family_count,
    })

    if halt_threshold > 0 and projected_request_count > halt_threshold:
        halt_expiry = now + timedelta(seconds=halt_cooldown_seconds)
        state["post_halt_quarantine_expiry"] = halt_expiry
        cooldown_state.update({
            "active": True,
            "reason": "halt_quarantine_active",
            "halt_quarantine_active": True,
        })
        return build_result(triggered=True, action="HALT", reason="request_pressure_halt", status_code=409)

    if retry_spacing_seconds > 0 and family_history:
        retry_expiry = family_history[-1] + timedelta(seconds=retry_spacing_seconds)
        if retry_expiry > now:
            state["retry_cooldown_expiry"][family] = retry_expiry
            cooldown_state.update({
                "active": True,
                "reason": "retry_spacing_active",
            })
            return build_result(triggered=True, action="DELAY", reason="retry_spacing_active", status_code=429)

    if max_requests > 0 and projected_request_count > max_requests:
        deny_expiry = now + timedelta(seconds=deny_cooldown_seconds)
        state["deny_cooldown_expiry"] = deny_expiry
        cooldown_state.update({
            "active": True,
            "reason": "deny_cooldown_active",
            "deny_cooldown_active": True,
        })
        return build_result(triggered=True, action="DENY", reason="request_rate_limit_exceeded", status_code=429)

    request_timestamps.append(now)
    family_timestamps.setdefault(family, []).append(now)
    if retry_spacing_seconds > 0:
        state["retry_cooldown_expiry"][family] = now + timedelta(seconds=retry_spacing_seconds)

    retry_expiry = state.get("retry_cooldown_expiry", {}).get(family)
    return build_result(triggered=False, action=None, reason=None, status_code=200)


def _record_exception(
    *,
    api_key: str,
    timestamp: str,
    category: str,
    detail: str,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    entry = {
        "event_id": _build_request_id(timestamp, {"category": category, "snapshot": snapshot}),
        "timestamp_utc": timestamp,
        "category": category,
        "detail": detail,
        "request_snapshot": snapshot,
    }
    EXCEPTION_REGISTER.append(entry)
    HALT_SIGNAL_STATE.setdefault(api_key, []).append(entry)
    HALT_SIGNAL_STATE[api_key] = HALT_SIGNAL_STATE[api_key][-10:]
    return entry


def _record_rejection(
    *,
    timestamp: str,
    constraint_category: str,
    reason: str,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    entry = {
        "entry_id": _build_request_id(timestamp, {"constraint_category": constraint_category, "snapshot": snapshot}),
        "timestamp_utc": timestamp,
        "constraint_category": constraint_category,
        "reason": reason,
        "request_snapshot": snapshot,
    }
    REJECTION_LEDGER.append(entry)
    return entry


def _detect_exception_categories(*values: Optional[str]) -> List[Dict[str, str]]:
    text = " ".join(_normalize_text(value) for value in values if value)
    hits: List[Dict[str, str]] = []
    if any(phrase in text for phrase in BYPASS_PHRASES):
        hits.append({
            "category": "bypass_attempt",
            "detail": "Bypass phrasing detected in decision request.",
        })
    if any(phrase in text for phrase in RETROACTIVE_PHRASES):
        hits.append({
            "category": "retroactive_attempt",
            "detail": "Retroactive logging language detected in decision request.",
        })
    if any(phrase in text for phrase in OVERRIDE_PHRASES):
        hits.append({
            "category": "override_attempt",
            "detail": "Override language detected in decision request.",
        })
    if any(phrase in text for phrase in DELAY_PHRASES):
        hits.append({
            "category": "delayed_logging_attempt",
            "detail": "Delayed logging language detected in decision request.",
        })
    return hits


def _halt_state_for_api_key(api_key: str, current_exception_count: int) -> Dict[str, Any]:
    recent_events = HALT_SIGNAL_STATE.get(api_key, [])
    recent_categories = {event.get("category") for event in recent_events}
    escalate = current_exception_count >= 2 or len(recent_events) >= 3 or len(recent_categories) >= 3
    return {
        "escalation_flag": escalate,
        "halt_recommendation": "Halt and review process integrity before further decision admission." if escalate else None,
        "integrity_state": "halt_recommended" if escalate else "operational",
    }


def _halt_release_config(record: Dict[str, Any]) -> Dict[str, Any]:
    config = record.get("halt_release_governance")
    if not isinstance(config, dict):
        return {}
    evidence = config.get("required_evidence", ["control_integrity_review", "fresh_telemetry_confirmation"])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    normalized_evidence = [str(item).strip() for item in evidence if str(item).strip()]
    return {
        "release_authority": str(config.get("release_authority", "authorized_operator")).strip() or "authorized_operator",
        "required_evidence": normalized_evidence,
        "post_release_cooldown_seconds": max(int(config.get("post_release_cooldown_seconds", 300) or 300), 0),
    }


def _default_halt_release_fields() -> Dict[str, Any]:
    return {
        "halt_release_required": False,
        "halt_release_authority": None,
        "halt_release_evidence": [],
        "post_release_cooldown": None,
        "re_evaluation_required": False,
    }


def _default_human_intervention_fields() -> Dict[str, Any]:
    return {
        "human_intervention_type": None,
        "human_intervention_required": False,
        "authorization_scope": None,
        "intervention_reason": None,
    }


def _apply_human_intervention_taxonomy(payload: Dict[str, Any]) -> Dict[str, Any]:
    intervention = _default_human_intervention_fields()
    constraint_category = (payload.get("constraint_analysis") or {}).get("constraint_category")
    exception_entries = payload.get("exception_register") or []
    exception_categories = {entry.get("category") for entry in exception_entries if entry.get("category")}

    if payload.get("halt_release_required"):
        intervention.update({
            "human_intervention_type": "halt_release_authorization_required",
            "human_intervention_required": True,
            "authorization_scope": "halt_release_governance",
            "intervention_reason": "halt_release_required",
        })
    elif "override_attempt" in exception_categories:
        intervention.update({
            "human_intervention_type": "override_attempt_detected",
            "human_intervention_required": True,
            "authorization_scope": "generic_override_prohibited",
            "intervention_reason": "override_attempt_detected",
        })
    elif constraint_category in {"incomplete_decision_record", "ambiguous_constraint_language", "invalid_size_format"}:
        intervention.update({
            "human_intervention_type": "clarification_required",
            "human_intervention_required": True,
            "authorization_scope": "decision_record_clarification",
            "intervention_reason": str(constraint_category),
        })
    elif exception_categories & {"retroactive_attempt", "delayed_logging_attempt", "bypass_attempt"}:
        intervention.update({
            "human_intervention_type": "exception_authorization_required",
            "human_intervention_required": True,
            "authorization_scope": "process_integrity_exception_authorization",
            "intervention_reason": "process_integrity_violation",
        })
    elif payload.get("system_state") == "HALT_RECOMMENDED" or payload.get("escalation_flag"):
        intervention.update({
            "human_intervention_type": "approval_required",
            "human_intervention_required": True,
            "authorization_scope": "elevated_integrity_review",
            "intervention_reason": "halt_recommendation_active",
        })

    payload.update(intervention)
    return payload


def _halt_release_state_for_api_key(api_key: str) -> Dict[str, Any]:
    state = HALT_RELEASE_STATE.setdefault(
        api_key,
        {
            "cooldown_expiry": None,
            "released_at": None,
            "release_authority": None,
            "release_evidence": [],
            "re_evaluation_required": False,
        },
    )
    state.setdefault("cooldown_expiry", None)
    state.setdefault("released_at", None)
    state.setdefault("release_authority", None)
    state.setdefault("release_evidence", [])
    state.setdefault("re_evaluation_required", False)
    return state


def _parse_release_evidence(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _evaluate_halt_release_governance(
    *,
    api_key: str,
    record: Dict[str, Any],
    release_authority_input: Optional[str],
    release_evidence_input: Optional[str],
) -> Dict[str, Any]:
    config = _halt_release_config(record)
    base_fields = _default_halt_release_fields()
    if not config:
        return {
            **base_fields,
            "configured": False,
            "triggered": False,
            "action": None,
            "status_code": 200,
            "reason": None,
        }

    now = get_current_datetime()
    state = _halt_release_state_for_api_key(api_key)
    cooldown_expiry = state.get("cooldown_expiry")
    if cooldown_expiry and cooldown_expiry <= now:
        state["cooldown_expiry"] = None
        cooldown_expiry = None

    previous_system_state = (SYSTEM_STATE_REGISTRY.get(api_key) or {}).get("system_state")
    halt_required = previous_system_state in {"HALT_ACTIVE", "HALT_RECOMMENDED"}
    required_authority = config["release_authority"]
    required_evidence = config["required_evidence"]
    provided_authority = (release_authority_input or "").strip() or None
    provided_evidence = _parse_release_evidence(release_evidence_input)

    fields = {
        "halt_release_required": halt_required,
        "halt_release_authority": required_authority if halt_required or state.get("released_at") else None,
        "halt_release_evidence": required_evidence if halt_required else list(state.get("release_evidence", [])),
        "post_release_cooldown": None,
        "re_evaluation_required": bool(state.get("re_evaluation_required")),
    }

    if cooldown_expiry:
        fields["post_release_cooldown"] = {
            "seconds_remaining": max(int((cooldown_expiry - now).total_seconds()), 0),
            "expires_at": cooldown_expiry.isoformat(),
        }
        fields["re_evaluation_required"] = True
        return {
            **fields,
            "configured": True,
            "triggered": True,
            "action": "DELAY",
            "status_code": 429,
            "reason": "post_release_cooldown_active",
        }

    if halt_required:
        authority_ok = provided_authority == required_authority
        evidence_ok = all(item in provided_evidence for item in required_evidence)
        if authority_ok and evidence_ok:
            release_time = now
            cooldown_expiry = release_time + timedelta(seconds=config["post_release_cooldown_seconds"])
            state.update({
                "cooldown_expiry": cooldown_expiry,
                "released_at": release_time,
                "release_authority": provided_authority,
                "release_evidence": provided_evidence,
                "re_evaluation_required": True,
            })
            fields.update({
                "halt_release_required": False,
                "halt_release_authority": required_authority,
                "halt_release_evidence": required_evidence,
                "post_release_cooldown": {
                    "seconds_remaining": config["post_release_cooldown_seconds"],
                    "expires_at": cooldown_expiry.isoformat(),
                },
                "re_evaluation_required": True,
            })
            return {
                **fields,
                "configured": True,
                "triggered": True,
                "action": "DELAY",
                "status_code": 429,
                "reason": "halt_release_accepted",
            }

        fields["post_release_cooldown"] = {
            "seconds_remaining": config["post_release_cooldown_seconds"],
            "expires_at": None,
        }
        return {
            **fields,
            "configured": True,
            "triggered": True,
            "action": "HALT",
            "status_code": 409,
            "reason": "halt_release_required",
        }

    if state.get("re_evaluation_required"):
        fields["halt_release_authority"] = state.get("release_authority") or required_authority
        fields["halt_release_evidence"] = list(state.get("release_evidence", [])) or required_evidence
        return {
            **fields,
            "configured": True,
            "triggered": False,
            "action": None,
            "status_code": 200,
            "reason": "re_evaluation_required",
        }

    return {
        **fields,
        "configured": True,
        "triggered": False,
        "action": None,
        "status_code": 200,
        "reason": None,
    }


def _default_system_state_fields() -> Dict[str, Any]:
    return {
        "system_state": "NORMAL",
        "state_transition_reason": "baseline_operational_posture",
        "state_entered_at": None,
        "state_release_condition": "continue clean admissible operation",
    }


def _derive_system_state(payload: Dict[str, Any]) -> Dict[str, str]:
    decision_status = payload.get("decision_status")
    telemetry_state = payload.get("telemetry_integrity_state")
    loop_state = payload.get("loop_integrity_state")
    temporal_triggered = bool(payload.get("temporal_constraint_triggered"))
    escalation_flag = bool(payload.get("escalation_flag"))
    halt_recommendation = payload.get("halt_recommendation")
    re_evaluation_required = bool(payload.get("re_evaluation_required"))

    if decision_status == "HALT":
        return {
            "system_state": "HALT_ACTIVE",
            "state_transition_reason": "halt_condition_active",
            "state_release_condition": "halt condition cleared and recovery review completed",
        }

    if telemetry_state not in {"not_evaluated", "telemetry_clear", None}:
        return {
            "system_state": "TELEMETRY_DEGRADED",
            "state_transition_reason": f"telemetry_state_{telemetry_state}",
            "state_release_condition": "telemetry integrity restored to admissible state",
        }

    if escalation_flag or halt_recommendation:
        return {
            "system_state": "HALT_RECOMMENDED",
            "state_transition_reason": "halt_recommendation_active",
            "state_release_condition": "halt recommendation cleared by subsequent clean control cycle",
        }

    if re_evaluation_required:
        return {
            "system_state": "RECOVERY_REVIEW_REQUIRED",
            "state_transition_reason": "re_evaluation_required_after_halt_release",
            "state_release_condition": "post-release cooldown completed and the next decision was re-evaluated",
        }

    if loop_state in {"retry_delayed", "retry_blocked", "pressure_escalated"} or decision_status in {
        "RETRY_DELAYED",
        "RETRY_BLOCKED",
        "PRESSURE_ESCALATED",
    } or (temporal_triggered and decision_status in {"DELAY", "DENY"}):
        return {
            "system_state": "PRESSURE_ELEVATED",
            "state_transition_reason": "pressure_condition_detected",
            "state_release_condition": "pressure signals clear on subsequent admission cycle",
        }

    if decision_status in {"CONSTRAIN", "REDUCE"}:
        return {
            "system_state": "CONSTRAINED_OPERATION",
            "state_transition_reason": "admission_constrained_but_operational",
            "state_release_condition": "constraint conditions clear and normal admission resumes",
        }

    return {
        "system_state": "NORMAL",
        "state_transition_reason": "baseline_operational_posture",
        "state_release_condition": "continue clean admissible operation",
    }


def _apply_system_state(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    timestamp = payload.get("timestamp_utc") or get_current_timestamp()
    candidate = _derive_system_state(payload)
    previous = SYSTEM_STATE_REGISTRY.get(api_key)
    severe_states = {"PRESSURE_ELEVATED", "TELEMETRY_DEGRADED", "HALT_RECOMMENDED", "HALT_ACTIVE"}
    next_state = candidate["system_state"]
    transition_reason = candidate["state_transition_reason"]
    release_condition = candidate["state_release_condition"]

    if previous and previous.get("system_state") in severe_states and candidate["system_state"] in {
        "NORMAL",
        "CONSTRAINED_OPERATION",
    }:
        next_state = "RECOVERY_REVIEW_REQUIRED"
        transition_reason = f"recovery_review_required_after_{previous['system_state'].lower()}"
        release_condition = "one additional clean admission cycle after recovery review requirement"
    elif previous and previous.get("system_state") == "RECOVERY_REVIEW_REQUIRED" and candidate["system_state"] in {
        "NORMAL",
        "CONSTRAINED_OPERATION",
    }:
        next_state = candidate["system_state"]
        transition_reason = f"recovery_review_cleared_to_{candidate['system_state'].lower()}"
        release_condition = candidate["state_release_condition"]

    entered_at = timestamp
    if previous and previous.get("system_state") == next_state:
        entered_at = previous.get("state_entered_at") or timestamp

    SYSTEM_STATE_REGISTRY[api_key] = {
        "system_state": next_state,
        "state_transition_reason": transition_reason,
        "state_entered_at": entered_at,
        "state_release_condition": release_condition,
    }

    payload.update({
        "system_state": next_state,
        "state_transition_reason": transition_reason,
        "state_entered_at": entered_at,
        "state_release_condition": release_condition,
    })
    if next_state in {"HALT_RECOMMENDED", "HALT_ACTIVE"}:
        payload["escalation_flag"] = True
    return payload


def _domain_trace_defaults() -> Dict[str, Any]:
    return {
        "constraint_category": None,
        "reflex_memory_class": None,
        "domain_signal": None,
        "prevented_risk_type": None,
        "telemetry_domain": None,
        "regime_context_applied": False,
        "related_prior_decisions": [],
        "cross_decision_pressure": False,
        "accumulated_constraint_category": None,
        "exposure_compounding_detected": False,
    }


def _build_prior_decision_reference(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": entry.get("request_id"),
        "intent": entry.get("intent"),
        "asset": entry.get("asset"),
        "decision_status": entry.get("decision_status"),
        "requested_size": entry.get("requested_size"),
    }


def _recent_prior_decisions(
    *,
    api_key: str,
    intent: Optional[str],
    asset: Optional[str],
) -> List[Dict[str, Any]]:
    normalized_intent = _normalize_text(intent)
    if normalized_intent not in RISK_INCREASING_INTENTS:
        return []

    recent = DECISION_ADMISSION_STATE.get(api_key, [])
    related = []
    for entry in recent[-5:]:
        if entry.get("intent") in RISK_INCREASING_INTENTS and entry.get("asset") in {asset, "ANY"}:
            related.append(_build_prior_decision_reference(entry))
    return related


def _infer_domain_trace(
    *,
    api_key: str,
    intent: Optional[str],
    asset: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    decision_status: str,
    guardrail: Dict[str, Any],
) -> Dict[str, Any]:
    trace = _domain_trace_defaults()
    strategy_text = _normalize_text(strategy)
    venue_text = _normalize_text(venue)
    asset_text = (asset or "").upper()
    advisory_text = _normalize_text(guardrail.get("advisory"))

    if asset_text in STABLECOIN_ASSETS or "peg" in strategy_text or "stablecoin" in strategy_text:
        trace.update({
            "constraint_category": "stablecoin",
            "reflex_memory_class": "stablecoin_defense",
            "domain_signal": "peg_instability",
            "prevented_risk_type": "depeg_exposure",
            "telemetry_domain": "stablecoin_telemetry",
        })
    elif asset_text in VALIDATOR_ASSETS or any(term in strategy_text for term in ("validator", "slashing", "uptime", "withdrawal")):
        domain_signal = "validator_pressure"
        if "uptime" in strategy_text:
            domain_signal = "uptime_degradation"
        elif "slashing" in strategy_text:
            domain_signal = "slashing_risk"
        elif "withdrawal" in strategy_text:
            domain_signal = "withdrawal_queue_abnormality"
        trace.update({
            "constraint_category": "validator",
            "reflex_memory_class": "validator_reflex",
            "domain_signal": domain_signal,
            "prevented_risk_type": "validator_failure_exposure",
            "telemetry_domain": "validator_telemetry",
        })
    elif asset_text in GOVERNANCE_ASSETS or any(term in strategy_text for term in ("governance", "delegate", "proposal", "treasury")):
        domain_signal = "governance_pressure"
        if "delegate" in strategy_text:
            domain_signal = "delegate_concentration"
        elif "proposal" in strategy_text:
            domain_signal = "proposal_capture_risk"
        elif "treasury" in strategy_text:
            domain_signal = "treasury_compromise_signal"
        trace.update({
            "constraint_category": "governance",
            "reflex_memory_class": "governance_reflex",
            "domain_signal": domain_signal,
            "prevented_risk_type": "governance_capture",
            "telemetry_domain": "governance_telemetry",
        })
    elif any(term in strategy_text for term in ("macro", "rate", "inflation", "fx", "volatility")):
        domain_signal = "macro_instability"
        if "rate" in strategy_text:
            domain_signal = "rate_shock"
        elif "inflation" in strategy_text:
            domain_signal = "inflation_surprise"
        elif "fx" in strategy_text:
            domain_signal = "fx_instability"
        elif "volatility" in strategy_text:
            domain_signal = "volatility_expansion"
        trace.update({
            "constraint_category": "macro",
            "reflex_memory_class": "macro_reflex",
            "domain_signal": domain_signal,
            "prevented_risk_type": "macro_regime_exposure",
            "telemetry_domain": "macro_telemetry",
            "regime_context_applied": True,
        })
    elif any(term in advisory_text for term in ("liquidity", "fragility")) or "liquidity" in strategy_text or "slippage" in strategy_text or "thin_order_book" in venue_text:
        trace.update({
            "constraint_category": "liquidity",
            "reflex_memory_class": "liquidity_reflex",
            "domain_signal": "liquidity_deterioration",
            "prevented_risk_type": "execution_slippage_exposure",
            "telemetry_domain": "execution_telemetry",
        })
    else:
        trace.update({
            "constraint_category": "general",
            "reflex_memory_class": "retained_discipline",
            "domain_signal": "baseline_guardrail",
            "prevented_risk_type": "unrestricted_risk_growth",
            "telemetry_domain": "decision_telemetry",
        })

    related_prior_decisions = _recent_prior_decisions(api_key=api_key, intent=intent, asset=asset)
    if related_prior_decisions and decision_status in {"CONSTRAIN", "VETO"}:
        trace.update({
            "related_prior_decisions": related_prior_decisions,
            "cross_decision_pressure": True,
            "accumulated_constraint_category": "exposure_compounding",
            "exposure_compounding_detected": True,
        })

    return trace


def _record_admission_state(
    *,
    api_key: str,
    request_id: str,
    intent: Optional[str],
    asset: Optional[str],
    requested_size: Optional[float],
    decision_status: str,
) -> None:
    entry = {
        "request_id": request_id,
        "intent": _normalize_text(intent),
        "asset": asset or "ANY",
        "requested_size": requested_size,
        "decision_status": decision_status,
    }
    DECISION_ADMISSION_STATE.setdefault(api_key, []).append(entry)
    DECISION_ADMISSION_STATE[api_key] = DECISION_ADMISSION_STATE[api_key][-10:]


def _build_structured_response(
    *,
    status_code: int,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    decision_status: str,
    adjustment: str,
    constraint_category: str,
    constraint_reason: str,
    impact_reason: str,
    adjusted_size: Optional[float],
    constraint_trace: Optional[Dict[str, Any]] = None,
    exception_entries: Optional[List[Dict[str, Any]]] = None,
    rejection_entry: Optional[Dict[str, Any]] = None,
    temporal_fields: Optional[Dict[str, Any]] = None,
    loop_fields: Optional[Dict[str, Any]] = None,
    telemetry_fields: Optional[Dict[str, Any]] = None,
    permission_fields: Optional[Dict[str, Any]] = None,
    halt_release_fields: Optional[Dict[str, Any]] = None,
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
    response_overrides: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    timestamp = get_current_timestamp()
    epoch = get_current_epoch()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    request_id = _build_request_id(timestamp, snapshot)
    parsed_size: Optional[float]
    try:
        parsed_size = float(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):
        parsed_size = None

    exception_entries = exception_entries or []
    constraint_trace = {**_domain_trace_defaults(), **(constraint_trace or {})}
    halt_state = _halt_state_for_api_key(api_key, len(exception_entries))
    temporal_fields = temporal_fields or _default_temporal_fields()
    loop_fields = loop_fields or _default_loop_fields()
    telemetry_fields = telemetry_fields or _default_telemetry_fields()
    permission_fields = permission_fields or _default_permission_budget_fields()
    halt_release_fields = halt_release_fields or _default_halt_release_fields()
    queue_fields = queue_fields or _evaluate_queue_governance(
        api_key=api_key,
        record=get_key_record(api_key),
        intent=intent,
        asset=asset,
        request_id=request_id,
        timestamp=timestamp,
        epoch=epoch,
        snapshot=snapshot,
    )
    memory_fields = memory_fields or _default_memory_fields()
    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "regime": DEFAULT_REGIME,
        "constitution_version": CONSTITUTION_VERSION,
        "tier": tier,
        "decision_admission_record": {
            "request_id": request_id,
            "request_snapshot": snapshot,
            "recorded_before_execution": True,
        },
        "decision_context": {
            "intent": intent,
            "asset": asset,
            "requested_size": parsed_size,
            "request_size_raw": size_raw,
            "regime": DEFAULT_REGIME,
            "epoch": epoch,
            "timestamp_utc": timestamp,
            "constitution_version": CONSTITUTION_VERSION,
            "tier": tier,
            "reflex_influence_applied": False,
        },
        "constraint_analysis": {
            "intent": intent,
            "asset": asset,
            "requested_size": parsed_size,
            "severity": "high" if decision_status == "VETO" else "medium",
            "policy": {},
            "advisory": adjustment,
            "constraint_category": constraint_category,
            "why_this_happened": constraint_reason,
        },
        "constraint_trace": constraint_trace,
        "impact_on_outcomes": {
            "requested_size": parsed_size,
            "adjusted_size": adjusted_size,
            "size_delta": None if parsed_size is None or adjusted_size is None else round(adjusted_size - parsed_size, 2),
            "why_this_happened": impact_reason,
        },
        "adjustment": adjustment,
        "decision_status": decision_status,
        "exception_register": exception_entries,
        "rejection_ledger": rejection_entry,
        "escalation_flag": halt_state["escalation_flag"],
        "halt_recommendation": halt_state["halt_recommendation"],
        "integrity_state": halt_state["integrity_state"],
        "decision_count_window": temporal_fields["decision_count_window"],
        "cooldown_state": temporal_fields["cooldown_state"],
        "cooldown_active": temporal_fields["cooldown_active"],
        "retry_cooldown_expiry": temporal_fields["retry_cooldown_expiry"],
        "post_halt_quarantine_expiry": temporal_fields["post_halt_quarantine_expiry"],
        "temporal_constraint_triggered": temporal_fields["temporal_constraint_triggered"],
        "retry_count_by_family": loop_fields["retry_count_by_family"],
        "semantic_similarity_to_prior_denial": loop_fields["semantic_similarity_to_prior_denial"],
        "loop_classification": loop_fields["loop_classification"],
        "pressure_score": loop_fields["pressure_score"],
        "loop_integrity_state": loop_fields["loop_integrity_state"],
        "telemetry_reliability_score": telemetry_fields["telemetry_reliability_score"],
        "telemetry_freshness_state": telemetry_fields["telemetry_freshness_state"],
        "cross_source_disagreement": telemetry_fields["cross_source_disagreement"],
        "telemetry_integrity_state": telemetry_fields["telemetry_integrity_state"],
        "minimum_required_reliability": telemetry_fields["minimum_required_reliability"],
        "telemetry_admissible": telemetry_fields["telemetry_admissible"],
        "permission_budget_class": permission_fields["permission_budget_class"],
        "permission_budget_remaining": permission_fields["permission_budget_remaining"],
        "budget_consumed_by_request": permission_fields["budget_consumed_by_request"],
        "budget_exhausted": permission_fields["budget_exhausted"],
        "exception_budget_remaining": permission_fields["exception_budget_remaining"],
        "halt_release_required": halt_release_fields["halt_release_required"],
        "halt_release_authority": halt_release_fields["halt_release_authority"],
        "halt_release_evidence": halt_release_fields["halt_release_evidence"],
        "post_release_cooldown": halt_release_fields["post_release_cooldown"],
        "re_evaluation_required": halt_release_fields["re_evaluation_required"],
        "queue_priority": queue_fields["queue_priority"],
        "queue_position": queue_fields["queue_position"],
        "conflict_group_id": queue_fields["conflict_group_id"],
        "batch_review_required": queue_fields["batch_review_required"],
        "request_expiry_at": queue_fields["request_expiry_at"],
        "memory_influence_invoked": memory_fields["memory_influence_invoked"],
        "reflex_memory_class": memory_fields["reflex_memory_class"],
        "memory_confidence_weight": memory_fields["memory_confidence_weight"],
        "memory_age_state": memory_fields["memory_age_state"],
        "stale_memory_flag": memory_fields["stale_memory_flag"],
        **_default_human_intervention_fields(),
        **_default_system_state_fields(),
    }

    if response_overrides:
        payload.update(response_overrides)

    if asset:
        payload["asset"] = asset
    if intent:
        payload["intent"] = intent
    if parsed_size is not None:
        payload["size"] = parsed_size
    if venue:
        payload["venue"] = venue
    if strategy:
        payload["strategy"] = strategy

    payload = _apply_system_state(payload, api_key)
    payload = _apply_human_intervention_taxonomy(payload)
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload, status_code=status_code)


def _temporal_response(
    *,
    status_code: int,
    temporal_action: str,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    temporal_result: Dict[str, Any],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    action_reason = {
        "DELAY": (
            "Temporal governance delayed the request because retry spacing is still active for this decision family.",
            "Nova delayed the request until retry spacing conditions are satisfied.",
        ),
        "DENY": (
            "Temporal governance denied the request because request pressure exceeded the configured window or deny cooldown is active.",
            "Nova denied the request because timing pressure exceeded the permitted admission cadence.",
        ),
        "HALT": (
            "Temporal governance halted the request because request pressure escalated into a halt quarantine state.",
            "Nova halted further admission while the post-halt quarantine remains active.",
        ),
    }
    constraint_reason, impact_reason = action_reason[temporal_action]
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category="temporal_governance",
        reason=constraint_reason,
        snapshot=snapshot,
    )
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status=temporal_action,
        adjustment=constraint_reason,
        constraint_category="temporal_governance",
        constraint_reason=constraint_reason,
        impact_reason=impact_reason,
        adjusted_size=None,
        constraint_trace={
            **_domain_trace_defaults(),
            "constraint_category": "temporal_governance",
            "reflex_memory_class": "temporal_governance",
            "domain_signal": temporal_result.get("reason"),
            "prevented_risk_type": "timing_pressure",
            "telemetry_domain": "temporal_telemetry",
        },
        rejection_entry=rejection_entry,
        temporal_fields=temporal_result,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
    )


def _loop_response(
    *,
    status_code: int,
    loop_action: str,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    temporal_fields: Dict[str, Any],
    loop_fields: Dict[str, Any],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    action_reason = {
        "RETRY_DELAYED": (
            "Loop integrity delayed the retry because the request remains semantically tied to a prior denial.",
            "Nova delayed the retry so repeated decision pressure cannot negotiate around a prior denial.",
        ),
        "RETRY_BLOCKED": (
            "Loop integrity blocked the retry because repeated semantically similar retries exceeded the permitted retry threshold.",
            "Nova blocked the retry because pressure persisted after a prior denial.",
        ),
        "PRESSURE_ESCALATED": (
            "Loop integrity escalated the retry because repeated semantically similar retries now indicate programmatic decision pressure.",
            "Nova escalated the retry pattern and surfaced a halt recommendation before further admission.",
        ),
    }
    constraint_reason, impact_reason = action_reason[loop_action]
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category="loop_integrity",
        reason=constraint_reason,
        snapshot=snapshot,
    )
    _record_loop_denial(
        api_key=api_key,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        constraint_category="loop_integrity",
    )
    response_overrides = None
    if loop_action == "PRESSURE_ESCALATED":
        response_overrides = {
            "escalation_flag": True,
            "halt_recommendation": "HALT_RECOMMENDED",
            "integrity_state": "halt_recommended",
        }
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status=loop_action,
        adjustment=constraint_reason,
        constraint_category="loop_integrity",
        constraint_reason=constraint_reason,
        impact_reason=impact_reason,
        adjusted_size=None,
        constraint_trace={
            **_domain_trace_defaults(),
            "constraint_category": "loop_integrity",
            "reflex_memory_class": "loop_integrity",
            "domain_signal": loop_fields.get("loop_classification"),
            "prevented_risk_type": "retry_pressure",
            "telemetry_domain": "loop_integrity",
        },
        rejection_entry=rejection_entry,
        temporal_fields=temporal_fields,
        loop_fields=loop_fields,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
        response_overrides=response_overrides,
    )


def _telemetry_response(
    *,
    status_code: int,
    telemetry_action: str,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    temporal_fields: Dict[str, Any],
    loop_fields: Dict[str, Any],
    telemetry_fields: Dict[str, Any],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    action_reason = {
        "DELAY": (
            "Telemetry integrity delayed the request because the telemetry used for admission is stale.",
            "Nova delayed the request until telemetry freshness meets the admissibility threshold.",
        ),
        "DENY": (
            "Telemetry integrity denied the request because telemetry confidence is below the required admission threshold.",
            "Nova denied the request because telemetry was not trustworthy enough to influence permission.",
        ),
        "HALT": (
            "Telemetry integrity halted the request because telemetry degradation created an unsafe permissioning posture.",
            "Nova halted further admission until telemetry integrity is restored.",
        ),
    }
    constraint_reason, impact_reason = action_reason[telemetry_action]
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category="telemetry_integrity",
        reason=constraint_reason,
        snapshot=snapshot,
    )
    response_overrides = None
    if telemetry_action == "HALT":
        response_overrides = {
            "escalation_flag": True,
            "halt_recommendation": "HALT due to telemetry degradation.",
            "integrity_state": "halt_recommended",
        }
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status=telemetry_action,
        adjustment=constraint_reason,
        constraint_category="telemetry_integrity",
        constraint_reason=constraint_reason,
        impact_reason=impact_reason,
        adjusted_size=None,
        constraint_trace={
            **_domain_trace_defaults(),
            "constraint_category": "telemetry_integrity",
            "reflex_memory_class": "telemetry_integrity",
            "domain_signal": telemetry_fields.get("telemetry_integrity_state"),
            "prevented_risk_type": "telemetry_admissibility_failure",
            "telemetry_domain": "telemetry_integrity",
        },
        rejection_entry=rejection_entry,
        temporal_fields=temporal_fields,
        loop_fields=loop_fields,
        telemetry_fields=telemetry_fields,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
        response_overrides=response_overrides,
    )


def _permission_budget_response(
    *,
    status_code: int,
    budget_action: str,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    temporal_fields: Dict[str, Any],
    loop_fields: Dict[str, Any],
    telemetry_fields: Dict[str, Any],
    permission_fields: Dict[str, Any],
    compounded_pressure: bool,
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    action_reason = {
        "DENY": (
            "Permission budgeting denied the request because cumulative admitted exposure for this decision class is exhausted.",
            "Nova denied the request because cumulative permission capacity for this class has been exhausted.",
        ),
        "DELAY": (
            "Permission budgeting delayed the request because cumulative permission capacity is currently unavailable.",
            "Nova delayed the request until cumulative permission capacity becomes available again.",
        ),
    }
    constraint_reason, impact_reason = action_reason[budget_action]
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category="permission_budgeting",
        reason=constraint_reason,
        snapshot=snapshot,
    )
    response_overrides = None
    if compounded_pressure:
        response_overrides = {
            "escalation_flag": True,
            "halt_recommendation": "HALT_RECOMMENDED",
            "integrity_state": "halt_recommended",
        }
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status=budget_action,
        adjustment=constraint_reason,
        constraint_category="permission_budgeting",
        constraint_reason=constraint_reason,
        impact_reason=impact_reason,
        adjusted_size=None,
        constraint_trace={
            **_domain_trace_defaults(),
            "constraint_category": "permission_budgeting",
            "reflex_memory_class": "permission_budgeting",
            "domain_signal": permission_fields.get("permission_budget_class"),
            "prevented_risk_type": "cumulative_permission_exhaustion",
            "telemetry_domain": "permission_budgeting",
        },
        rejection_entry=rejection_entry,
        temporal_fields=temporal_fields,
        loop_fields=loop_fields,
        telemetry_fields=telemetry_fields,
        permission_fields=permission_fields,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
        response_overrides=response_overrides,
    )


def _halt_release_response(
    *,
    status_code: int,
    release_action: str,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    temporal_fields: Dict[str, Any],
    loop_fields: Dict[str, Any],
    telemetry_fields: Dict[str, Any],
    permission_fields: Dict[str, Any],
    halt_release_fields: Dict[str, Any],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    action_reason = {
        "HALT": (
            "Halt release governance requires an explicit release authority and evidence set before the system may exit halt-related posture.",
            "Nova kept the system in halt posture because release requirements have not been satisfied.",
        ),
        "DELAY": (
            "Halt release governance delayed admission because the halt release was accepted and the post-release cooldown is active.",
            "Nova delayed fresh admission until post-release cooldown completes and a new decision is re-evaluated.",
        ),
    }
    constraint_reason, impact_reason = action_reason[release_action]
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category="halt_release_governance",
        reason=constraint_reason,
        snapshot=snapshot,
    )
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status=release_action,
        adjustment=constraint_reason,
        constraint_category="halt_release_governance",
        constraint_reason=constraint_reason,
        impact_reason=impact_reason,
        adjusted_size=None,
        constraint_trace={
            **_domain_trace_defaults(),
            "constraint_category": "halt_release_governance",
            "reflex_memory_class": "halt_release_governance",
            "domain_signal": halt_release_fields.get("halt_release_authority"),
            "prevented_risk_type": "premature_halt_exit",
            "telemetry_domain": "halt_release_governance",
        },
        rejection_entry=rejection_entry,
        temporal_fields=temporal_fields,
        loop_fields=loop_fields,
        telemetry_fields=telemetry_fields,
        permission_fields=permission_fields,
        halt_release_fields=halt_release_fields,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
    )


def _reject_decision(
    *,
    status_code: int,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    constraint_category: str,
    reason: str,
    impact_reason: str,
    exception_descriptors: Optional[List[Dict[str, str]]] = None,
    constraint_trace: Optional[Dict[str, Any]] = None,
    temporal_fields: Optional[Dict[str, Any]] = None,
    loop_fields: Optional[Dict[str, Any]] = None,
    telemetry_fields: Optional[Dict[str, Any]] = None,
    permission_fields: Optional[Dict[str, Any]] = None,
    halt_release_fields: Optional[Dict[str, Any]] = None,
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    timestamp = get_current_timestamp()
    snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size_raw, venue=venue, strategy=strategy)
    rejection_entry = _record_rejection(
        timestamp=timestamp,
        constraint_category=constraint_category,
        reason=reason,
        snapshot=snapshot,
    )
    _record_loop_denial(
        api_key=api_key,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        constraint_category=constraint_category,
    )
    exception_entries = [
        _record_exception(
            api_key=api_key,
            timestamp=timestamp,
            category=descriptor["category"],
            detail=descriptor["detail"],
            snapshot=snapshot,
        )
        for descriptor in (exception_descriptors or [])
    ]
    return _build_structured_response(
        status_code=status_code,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        decision_status="VETO",
        adjustment="Reject decision admission until the request satisfies Nova integrity requirements.",
        constraint_category=constraint_category,
        constraint_reason=reason,
        impact_reason=impact_reason,
        adjusted_size=0.0,
        constraint_trace=constraint_trace or {
            **_domain_trace_defaults(),
            "constraint_category": constraint_category,
            "reflex_memory_class": "integrity_reflex" if constraint_category == "process_integrity_violation" else "admission_gate",
            "domain_signal": constraint_category,
            "prevented_risk_type": "process_integrity_failure" if constraint_category == "process_integrity_violation" else "invalid_decision_admission",
            "telemetry_domain": "integrity_telemetry",
        },
        exception_entries=exception_entries,
        rejection_entry=rejection_entry,
        temporal_fields=temporal_fields,
        loop_fields=loop_fields,
        telemetry_fields=telemetry_fields,
        permission_fields=permission_fields,
        halt_release_fields=halt_release_fields,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
    )


def _parse_size_or_reject(
    *,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[float], Optional[JSONResponse]]:
    if size_raw is None or not str(size_raw).strip():
        return None, _reject_decision(
            status_code=422,
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
            constraint_category="incomplete_decision_record",
            reason="Decision admission requires a numeric size before any evaluation can occur.",
            impact_reason="Nova blocked the request because a complete decision record was not supplied before execution.",
        )

    normalized = _normalize_text(size_raw)
    if normalized in AMBIGUOUS_LANGUAGE_TERMS:
        return None, _reject_decision(
            status_code=422,
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
            constraint_category="ambiguous_constraint_language",
            reason="Ambiguous sizing language is not admissible. Provide a specific numeric size.",
            impact_reason="Nova blocked the request because vague operator language cannot substitute for an admissible decision structure.",
        )

    try:
        parsed = float(size_raw)
    except (TypeError, ValueError):
        return None, _reject_decision(
            status_code=422,
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
            constraint_category="invalid_size_format",
            reason="Decision admission requires a valid numeric size.",
            impact_reason="Nova blocked the request because the size field could not be evaluated structurally.",
        )

    return parsed, None


def _validate_decision_fields(
    *,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> Optional[JSONResponse]:
    normalized_intent = _normalize_text(intent)
    if not normalized_intent:
        return _reject_decision(
            status_code=422,
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
            constraint_category="incomplete_decision_record",
            reason="Decision admission requires an intent before any evaluation can occur.",
            impact_reason="Nova blocked the request because no decision intent was supplied before execution.",
        )

    if not _normalize_text(asset):
        return _reject_decision(
            status_code=422,
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
            constraint_category="incomplete_decision_record",
            reason="Decision admission requires an asset before any evaluation can occur.",
            impact_reason="Nova blocked the request because no asset was supplied before execution.",
        )

    if normalized_intent in RISK_INCREASING_INTENTS:
        _, rejection_response = _parse_size_or_reject(
            api_key=api_key,
            tier=tier,
            intent=intent,
            asset=asset,
            size_raw=size_raw,
            venue=venue,
            strategy=strategy,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )
        if rejection_response:
            return rejection_response
    return None


def _exception_response_if_needed(
    *,
    api_key: str,
    tier: str,
    intent: Optional[str],
    asset: Optional[str],
    size_raw: Optional[str],
    venue: Optional[str],
    strategy: Optional[str],
    queue_fields: Optional[Dict[str, Any]] = None,
    memory_fields: Optional[Dict[str, Any]] = None,
) -> Optional[JSONResponse]:
    exception_descriptors = _detect_exception_categories(intent, asset, venue, strategy)
    if not exception_descriptors:
        return None
    return _reject_decision(
        status_code=409,
        api_key=api_key,
        tier=tier,
        intent=intent,
        asset=asset,
        size_raw=size_raw,
        venue=venue,
        strategy=strategy,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
        constraint_category="process_integrity_violation",
        reason="Nova rejected the request because process integrity language indicated bypass, override, retroactive, or delayed-control behavior.",
        impact_reason="Nova blocked the request because abnormal process language cannot enter the decision path before execution.",
        exception_descriptors=exception_descriptors,
    )


def epoch_hash(epoch: int, timestamp_utc: str, constitution_version: str, regime: str) -> str:
    raw = f"{epoch}|{timestamp_utc}|{constitution_version}|{regime}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_guardrail(intent: Optional[str], asset: Optional[str], size: Optional[float]) -> dict:
    """
    Build guardrail with explicit action policy.

    Core rule:
    Stress = no new risk
    """

    # -----------------------------
    # STRESS REGIME (HARD VETO)
    # -----------------------------
    normalized_intent = (intent or "").strip().lower()
    requested_size = float(size) if size is not None else 0.0
    is_risk_increasing = normalized_intent in {
        "trade",
        "deploy_liquidity",
        "open_position",
        "increase_position",
    }

    if DEFAULT_REGIME == "Stress":
        return {
            "severity": "high",
            "advisory": "Do not initiate new risk. Only reduce or exit existing exposure.",
            "action_policy": {
                "allow_new_risk": False,
                "allow_risk_reduction": True,
                "allow_position_increase": False,
                "allow_position_decrease": True
            }
        }

    # -----------------------------
    # ELEVATED FRAGILITY (CONSTRAIN)
    # -----------------------------
    if DEFAULT_REGIME == "Elevated Fragility":
        if is_risk_increasing and requested_size >= 250000:
            return {
                "severity": "high",
                "advisory": "Block large risk expansion until fragility conditions improve.",
                "action_policy": {
                    "allow_new_risk": False,
                    "allow_risk_reduction": True,
                    "allow_position_increase": False,
                    "allow_position_decrease": True
                }
            }

        if normalized_intent == "deploy_liquidity":
            return {
                "severity": "medium",
                "advisory": "Reduce size and avoid low-liquidity venues.",
                "action_policy": {
                    "allow_new_risk": True,
                    "allow_risk_reduction": True,
                    "allow_position_increase": False,
                    "allow_position_decrease": True
                }
            }

        return {
            "severity": "medium",
            "advisory": "Proceed with caution. Reduce exposure and tighten controls.",
            "action_policy": {
                "allow_new_risk": True,
                "allow_risk_reduction": True,
                "allow_position_increase": False,
                "allow_position_decrease": True
            }
        }

    # -----------------------------
    # STABLE (FULL PERMISSION)
    # -----------------------------
    return {
        "severity": "low",
        "advisory": "Proceed under normal risk controls.",
        "action_policy": {
            "allow_new_risk": True,
            "allow_risk_reduction": True,
            "allow_position_increase": True,
            "allow_position_decrease": True
        }
    }


def derive_decision_status(intent: Optional[str], size: Optional[float], guardrail: Dict[str, Any]) -> str:
    normalized_intent = (intent or "").strip().lower()
    requested_size = float(size) if size is not None else None
    is_risk_increasing = normalized_intent in {
        "trade",
        "deploy_liquidity",
        "open_position",
        "increase_position",
    }
    policy = guardrail.get("action_policy", {})

    if is_risk_increasing and not policy.get("allow_new_risk", False):
        return "VETO"
    if is_risk_increasing and not policy.get("allow_position_increase", False):
        if requested_size is None or requested_size > 0:
            return "CONSTRAIN"
    return "ALLOW"


def build_adjustment(
    decision_status: str,
    size: Optional[float],
    guardrail: Dict[str, Any],
    adjustment_factor: Optional[float] = None,
) -> str:
    requested_size = float(size) if size is not None else None
    if decision_status == "VETO":
        return guardrail.get("advisory") or "Do not initiate new risk."
    if decision_status == "CONSTRAIN":
        if requested_size is not None and requested_size > 0:
            factor = adjustment_factor if adjustment_factor is not None else 0.5
            adjusted_size = max(round(requested_size * factor, 2), 1.0)
            return f"Reduce requested size from {requested_size:g} to {adjusted_size:g} and tighten execution controls."
        return "Reduce requested exposure and tighten execution controls."
    return guardrail.get("advisory") or "Proceed under normal risk controls."


def build_impact_on_outcomes(
    decision_status: str,
    size: Optional[float],
    adjustment_factor: Optional[float] = None,
) -> Dict[str, Any]:
    requested_size = float(size) if size is not None else None
    adjusted_size: Optional[float]
    explanation: str

    if requested_size is None:
        adjusted_size = None
    elif decision_status == "VETO":
        adjusted_size = 0.0
    elif decision_status == "CONSTRAIN":
        factor = adjustment_factor if adjustment_factor is not None else 0.5
        adjusted_size = max(round(requested_size * factor, 2), 1.0)
    else:
        adjusted_size = requested_size

    if decision_status == "VETO":
        explanation = "New risk is blocked under the current regime, so the requested action should not proceed."
    elif decision_status == "CONSTRAIN":
        explanation = "Risk can proceed only in reduced form, so downstream execution should be size-limited."
    else:
        explanation = "Current conditions validate the request under normal controls."

    return {
        "requested_size": requested_size,
        "adjusted_size": adjusted_size,
        "size_delta": None if requested_size is None or adjusted_size is None else round(adjusted_size - requested_size, 2),
        "why_this_happened": explanation,
    }


def build_constraint_analysis(
    *,
    intent: Optional[str],
    asset: Optional[str],
    size: Optional[float],
    guardrail: Dict[str, Any],
    decision_status: str,
) -> Dict[str, Any]:
    requested_size = float(size) if size is not None else None
    severity = guardrail.get("severity", "unknown")
    advisory = guardrail.get("advisory", "")

    if decision_status == "VETO":
        why = "Constraint analysis escalated to a veto because the requested action would add new risk under a high-fragility regime."
    elif decision_status == "CONSTRAIN":
        why = "Constraint analysis limited the request because the regime allows participation but blocks unrestricted position growth."
    else:
        why = "Constraint analysis found no active restriction on this request beyond baseline controls."

    return {
        "intent": intent,
        "asset": asset,
        "requested_size": requested_size,
        "severity": severity,
        "policy": guardrail.get("action_policy", {}),
        "advisory": advisory,
        "why_this_happened": why,
    }


def build_memory_context() -> dict:
    if DEFAULT_REGIME == "Stress":
        return {
            "sequence_type": "stress_escalation_cycle",
            "consequence_pattern": "historically associated with rapid de-risking and elevated fragility persistence"
        }

    if DEFAULT_REGIME == "Elevated Fragility":
        return {
            "sequence_type": "liquidity_deterioration_cycle",
            "consequence_pattern": "historically escalates to Stress within 3–6 epochs under worsening conditions"
        }

    return {
        "sequence_type": "stable_regime_pattern",
        "consequence_pattern": "historically associated with normal capital deployment conditions"
    }


def build_historical_reference_from_reflex(state: ReflexMemoryState) -> dict:
    if state.active_registry_id == "stress_new_risk_block":
        return {
            "sequence_type": "stress_escalation_cycle",
            "consequence_pattern": "historically associated with rapid de-risking and elevated fragility persistence",
        }

    if state.active_registry_id == "elevated_fragility_size_brake":
        return {
            "sequence_type": "liquidity_deterioration_cycle",
            "consequence_pattern": "historically escalates to Stress within 3-6 epochs under worsening conditions",
        }

    return {
        "sequence_type": "stable_regime_pattern",
        "consequence_pattern": "historically associated with normal capital deployment conditions",
    }


def apply_reflex_memory(
    *,
    record: Dict[str, Any],
    regime: str,
    intent: Optional[str],
    asset: Optional[str],
    size: Optional[float],
    decision_status: str,
) -> tuple[ReflexMemoryState, str, Optional[float], Dict[str, Any]]:
    registry = build_registry(regime)
    active_entry = select_active_entry(registry=registry, intent=intent, size=size)
    memory_fields = _evaluate_memory_governance(record=record, entry=active_entry)
    effective_decision = decision_status
    adjustment_factor: Optional[float] = None

    if active_entry and memory_fields["memory_influence_invoked"] and active_entry.decision_effect == "VETO":
        effective_decision = "VETO"
        adjustment_factor = active_entry.adjustment_factor
    elif (
        active_entry
        and memory_fields["memory_influence_invoked"]
        and active_entry.decision_effect == "CONSTRAIN"
        and decision_status != "VETO"
    ):
        effective_decision = "CONSTRAIN"
        adjustment_factor = _weighted_adjustment_factor(
            active_entry.adjustment_factor,
            memory_fields["memory_confidence_weight"],
        )

    proof_entry = active_entry if memory_fields["memory_influence_invoked"] else None

    state = ReflexMemoryState(
        persistence_state=active_entry.persistence_state if active_entry else "retained",
        validation_status=active_entry.validation_status if active_entry else "observed",
        registered_entries=registry,
        active_registry_id=active_entry.registry_id if active_entry else None,
        triggered=active_entry is not None,
        influence_applied=bool(memory_fields["memory_influence_invoked"]),
        decision_before_reflex=decision_status,
        decision_after_reflex=effective_decision,
        metadata={
            "regime": regime,
            "intent": intent,
            "asset": asset,
            "requested_size": size,
            "memory_governance": {
                "reflex_memory_class": memory_fields["reflex_memory_class"],
                "memory_confidence_weight": memory_fields["memory_confidence_weight"],
                "memory_age_state": memory_fields["memory_age_state"],
                "stale_memory_flag": memory_fields["stale_memory_flag"],
                "blocked_reason": memory_fields["blocked_reason"],
                "admissible": memory_fields["admissible"],
            },
        },
        proof=build_reflex_proof(
            entry=proof_entry,
            decision_before_reflex=decision_status,
            decision_after_reflex=effective_decision,
        ),
    )
    return validate_reflex_memory_state(state), effective_decision, adjustment_factor, {
        key: memory_fields[key] for key in _default_memory_fields().keys()
    }


def map_price_to_tier(price_id: str) -> str:
    price_map = {
        PRICE_EMERGING_ID: "emerging",
        PRICE_CORE_ID: "core",
        PRICE_ENTERPRISE_ID: "enterprise",
    }
    return price_map.get(price_id, "free")


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    if stripe is None:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Missing STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}")

    event_id = str(event.get("id") or "")
    if event_id and _is_duplicate_event(event_id):
        print(f"[DUPLICATE EVENT] {event_id}")
        log_stripe_audit(
            event_id=event_id,
            event_type=str(event.get("type") or ""),
            action="ignore_event",
            result="duplicate",
        )
        return JSONResponse({"status": "duplicate", "event_id": event_id})

    event_type = event.get("type")
    created_key: Optional[str] = None
    created_tier: Optional[str] = None
    status: str = "success"
    reason: Optional[str] = None

    if event_type in {
        "checkout.session.completed",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
        "customer.subscription.deleted",
        "customer.subscription.updated",
    }:
        obj = event.get("data", {}).get("object", {})
        customer_email = (
            obj.get("customer_details", {}).get("email")
            or obj.get("customer_email")
            or "stripe_customer"
        ).strip().lower()
        stripe_customer_id = obj.get("customer")
        stripe_subscription_id = obj.get("subscription")

        if event_type in {"checkout.session.completed", "invoice.payment_succeeded"}:
            price_id = ""
            try:
                if event_type == "checkout.session.completed":
                    session_id = obj.get("id")
                    line_items = stripe.checkout.Session.list_line_items(session_id, limit=1)
                    if not line_items or not line_items.data:
                        print("[ERROR] No line items found")
                        log_stripe_audit(
                            event_id=event_id,
                            event_type=event_type,
                            customer_email=customer_email,
                            stripe_customer_id=str(stripe_customer_id or ""),
                            action="ignore_event",
                            result="no_line_items",
                            reason="no_line_items",
                        )
                        return JSONResponse({"status": "error", "reason": "no_line_items"})
                    price_id = (line_items.data[0].get("price") or {}).get("id", "")
                else:
                    lines = obj.get("lines", {}).get("data", [])
                    if not lines:
                        print("[ERROR] Missing invoice line items")
                        log_stripe_audit(
                            event_id=event_id,
                            event_type=event_type,
                            customer_email=customer_email,
                            stripe_customer_id=str(stripe_customer_id or ""),
                            action="ignore_event",
                            result="missing_price_id",
                            reason="missing_invoice_line_items",
                        )
                        return JSONResponse({"status": "error", "reason": "missing_price_id"})
                    price_id = (lines[0].get("price") or {}).get("id", "")
            except Exception as exc:
                print(f"[ERROR] Stripe line item resolution failed: {exc}")
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="ignore_event",
                    result="price_lookup_failed",
                    reason=str(exc),
                )
                return JSONResponse({"status": "error", "reason": "price_lookup_failed"})

            if not price_id:
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="ignore_event",
                    result="missing_price_id",
                    reason="missing_price_id",
                )
                return JSONResponse({"status": "error", "reason": "missing_price_id"})

            created_tier = map_price_to_tier(price_id)
            if created_tier == "free":
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="ignore_event",
                    result="unmapped_price_id",
                    reason=f"unmapped_price_id:{price_id}",
                )
                return JSONResponse({
                    "status": "error",
                    "reason": "unmapped_price_id",
                    "price_id": price_id,
                })

            existing_key = (
                find_key_by_stripe_customer_id(stripe_customer_id)
                or find_key_by_owner(customer_email)
            )
            if existing_key:
                activate_or_renew_key(
                    existing_key,
                    created_tier,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_price_id=price_id,
                )
                created_key = existing_key
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="renew_key",
                    result="success",
                    api_key=created_key,
                    tier=created_tier,
                )
            else:
                if event_type == "invoice.payment_succeeded":
                    print(f"[ERROR] No existing key for owner on renewal: {customer_email}")
                    log_stripe_audit(
                        event_id=event_id,
                        event_type=event_type,
                        customer_email=customer_email,
                        stripe_customer_id=str(stripe_customer_id or ""),
                        action="renew_key",
                        result="not_found",
                        tier=created_tier,
                        reason="no_existing_key_for_owner",
                    )
                    return JSONResponse({"status": "error", "reason": "no_existing_key_for_owner"})

                created_key = generate_api_key()
                store_key(
                    created_key,
                    created_tier,
                    owner=customer_email,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_price_id=price_id,
                    status="active",
                    last_paid_at=datetime.now(timezone.utc).isoformat(),
                )
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="create_key",
                    result="success",
                    api_key=created_key,
                    tier=created_tier,
                )

            print(f"[STRIPE] {customer_email} -> {created_key} ({created_tier})")

        elif event_type == "invoice.payment_failed":
            suspended = False
            if stripe_customer_id:
                suspended = suspend_key_by_stripe_customer_id(stripe_customer_id)
            if not suspended and customer_email:
                suspended = suspend_keys_for_owner(customer_email) > 0
            print(f"[STRIPE] payment_failed -> suspended access for {customer_email}")
            log_stripe_audit(
                event_id=event_id,
                event_type=event_type,
                customer_email=customer_email,
                stripe_customer_id=str(stripe_customer_id or ""),
                action="suspend_key",
                result="success" if suspended else "not_found",
            )

        elif event_type == "customer.subscription.deleted":
            metadata_email = (obj.get("metadata", {}).get("customer_email", "") or "").strip().lower()
            deactivated = False
            if stripe_customer_id:
                deactivated = deactivate_key_by_stripe_customer_id(stripe_customer_id)
            if not deactivated and metadata_email:
                deactivated = deactivate_keys_for_owner(metadata_email) > 0
            print(f"[STRIPE] subscription_deleted -> deactivated access for {metadata_email or stripe_customer_id}")
            log_stripe_audit(
                event_id=event_id,
                event_type=event_type,
                customer_email=metadata_email,
                stripe_customer_id=str(stripe_customer_id or ""),
                action="deactivate_key",
                result="success" if deactivated else "not_found",
            )

        elif event_type == "customer.subscription.updated":
            stripe_customer_id = obj.get("customer")
            stripe_subscription_id = obj.get("id")
            items = obj.get("items", {}).get("data", [])
            price_id = ""
            if items:
                price_id = (items[0].get("price") or {}).get("id", "")
            if price_id:
                tier = map_price_to_tier(price_id)
                if tier != "free":
                    existing_key = find_key_by_stripe_customer_id(stripe_customer_id)
                    if existing_key:
                        activate_or_renew_key(
                            existing_key,
                            tier,
                            stripe_customer_id=stripe_customer_id,
                            stripe_subscription_id=stripe_subscription_id,
                            stripe_price_id=price_id,
                        )
                        print(f"[STRIPE] subscription_updated -> {existing_key} ({tier})")
                        log_stripe_audit(
                            event_id=event_id,
                            event_type=event_type,
                            customer_email=customer_email,
                            stripe_customer_id=str(stripe_customer_id or ""),
                            action="update_tier",
                            result="success",
                            api_key=existing_key,
                            tier=tier,
                        )
                    else:
                        log_stripe_audit(
                            event_id=event_id,
                            event_type=event_type,
                            customer_email=customer_email,
                            stripe_customer_id=str(stripe_customer_id or ""),
                            action="update_tier",
                            result="not_found",
                            tier=tier,
                            reason="no_existing_key_for_customer",
                        )
                else:
                    log_stripe_audit(
                        event_id=event_id,
                        event_type=event_type,
                        customer_email=customer_email,
                        stripe_customer_id=str(stripe_customer_id or ""),
                        action="ignore_event",
                        result="unmapped_price_id",
                        reason=f"unmapped_price_id:{price_id}",
                    )
            else:
                log_stripe_audit(
                    event_id=event_id,
                    event_type=event_type,
                    customer_email=customer_email,
                    stripe_customer_id=str(stripe_customer_id or ""),
                    action="ignore_event",
                    result="missing_price_id",
                    reason="subscription_updated_missing_price",
                )
    else:
        log_stripe_audit(
            event_id=event_id,
            event_type=str(event_type or ""),
            action="ignore_event",
            result="success",
            reason="event_not_handled",
        )

    return JSONResponse({
        "status": status,
        "event_type": event_type,
        "api_key_created": bool(created_key),
        "tier": created_tier,
        "reason": reason,
    })


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/regime")
def get_regime(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)
    epoch = get_current_epoch()
    timestamp = get_current_timestamp()

    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "regime": DEFAULT_REGIME,
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
    }
    payload = _apply_system_state(payload, entitlement["api_key"])
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/epoch")
def get_epoch(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)
    epoch = get_current_epoch()
    timestamp = get_current_timestamp()

    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "constitution_version": CONSTITUTION_VERSION,
        "hash": epoch_hash(
            epoch,
            timestamp,
            CONSTITUTION_VERSION,
            DEFAULT_REGIME
        ),
        "tier": entitlement["tier"],
    }
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/context")
def get_context(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    intent: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    size: Optional[str] = Query(default=None),
    venue: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
    telemetry_age_seconds: Optional[str] = Query(default=None),
    telemetry_reliability: Optional[str] = Query(default=None),
    telemetry_source_scores: Optional[str] = Query(default=None),
    halt_release_authority_input: Optional[str] = Query(default=None),
    halt_release_evidence_input: Optional[str] = Query(default=None),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)
    temporal_fields = _default_temporal_fields()
    loop_fields = _default_loop_fields()
    telemetry_fields = _default_telemetry_fields()
    permission_fields = _default_permission_budget_fields()
    halt_release_fields = _default_halt_release_fields()
    queue_fields = _default_queue_fields()
    memory_fields = _default_memory_fields()
    timestamp = get_current_timestamp()
    epoch = get_current_epoch()
    request_snapshot = _request_snapshot(intent=intent, asset=asset, size_raw=size, venue=venue, strategy=strategy)
    request_id = _build_request_id(timestamp, request_snapshot)
    queue_fields = _evaluate_queue_governance(
        api_key=entitlement["api_key"],
        record=entitlement["key_record"],
        intent=intent,
        asset=asset,
        request_id=request_id,
        timestamp=timestamp,
        epoch=epoch,
        snapshot=request_snapshot,
    )
    temporal_result = _evaluate_temporal_governance(
        api_key=entitlement["api_key"],
        record=entitlement["key_record"],
        intent=intent,
        asset=asset,
    )
    temporal_fields = temporal_result
    if temporal_result["triggered"]:
        return _temporal_response(
            status_code=temporal_result["status_code"],
            temporal_action=temporal_result["action"],
            api_key=entitlement["api_key"],
            tier=entitlement["tier"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            temporal_result=temporal_result,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )

    loop_result = _evaluate_loop_integrity(
        api_key=entitlement["api_key"],
        record=entitlement["key_record"],
        intent=intent,
        asset=asset,
        size_raw=size,
        venue=venue,
        strategy=strategy,
    )
    loop_fields = loop_result
    if loop_result["triggered"]:
        return _loop_response(
            status_code=loop_result["status_code"],
            loop_action=loop_result["action"],
            api_key=entitlement["api_key"],
            tier=entitlement["tier"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            temporal_fields=temporal_fields,
            loop_fields=loop_result,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )

    try:
        telemetry_age_seconds_value = float(telemetry_age_seconds) if telemetry_age_seconds is not None else None
    except ValueError:
        telemetry_age_seconds_value = None
    try:
        telemetry_reliability_value = float(telemetry_reliability) if telemetry_reliability is not None else None
    except ValueError:
        telemetry_reliability_value = None

    telemetry_result = _evaluate_telemetry_integrity(
        record=entitlement["key_record"],
        intent=intent,
        telemetry_age_seconds=telemetry_age_seconds_value,
        telemetry_reliability=telemetry_reliability_value,
        telemetry_source_scores=telemetry_source_scores,
    )
    telemetry_fields = telemetry_result
    if telemetry_result["triggered"]:
        return _telemetry_response(
            status_code=telemetry_result["status_code"],
            telemetry_action=telemetry_result["action"],
            api_key=entitlement["api_key"],
            tier=entitlement["tier"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            temporal_fields=temporal_fields,
            loop_fields=loop_fields,
            telemetry_fields=telemetry_fields,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )

    halt_release_result = _evaluate_halt_release_governance(
        api_key=entitlement["api_key"],
        record=entitlement["key_record"],
        release_authority_input=halt_release_authority_input,
        release_evidence_input=halt_release_evidence_input,
    )
    halt_release_fields = halt_release_result
    if halt_release_result["triggered"]:
        return _halt_release_response(
            status_code=halt_release_result["status_code"],
            release_action=halt_release_result["action"],
            api_key=entitlement["api_key"],
            tier=entitlement["tier"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            temporal_fields=temporal_fields,
            loop_fields=loop_fields,
            telemetry_fields=telemetry_fields,
            permission_fields=permission_fields,
            halt_release_fields=halt_release_fields,
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )

    validation_rejection = _validate_decision_fields(
        api_key=entitlement["api_key"],
        tier=entitlement["tier"],
        intent=intent,
        asset=asset,
        size_raw=size,
        venue=venue,
        strategy=strategy,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
    )
    if validation_rejection:
        return validation_rejection

    exception_rejection = _exception_response_if_needed(
        api_key=entitlement["api_key"],
        tier=entitlement["tier"],
        intent=intent,
        asset=asset,
        size_raw=size,
        venue=venue,
        strategy=strategy,
        queue_fields=queue_fields,
        memory_fields=memory_fields,
    )
    if exception_rejection:
        return exception_rejection

    parsed_size = float(size) if size is not None else None
    guardrail = build_guardrail(intent=intent, asset=asset, size=parsed_size)
    baseline_decision_status = derive_decision_status(intent=intent, size=parsed_size, guardrail=guardrail)
    reflex_memory_state, decision_status, adjustment_factor, memory_fields = apply_reflex_memory(
        record=entitlement["key_record"],
        regime=DEFAULT_REGIME,
        intent=intent,
        asset=asset,
        size=parsed_size,
        decision_status=baseline_decision_status,
    )
    adjustment = build_adjustment(
        decision_status=decision_status,
        size=parsed_size,
        guardrail=guardrail,
        adjustment_factor=adjustment_factor,
    )
    impact_on_outcomes = build_impact_on_outcomes(
        decision_status=decision_status,
        size=parsed_size,
        adjustment_factor=adjustment_factor,
    )
    permission_result = _evaluate_permission_budget(
        api_key=entitlement["api_key"],
        record=entitlement["key_record"],
        intent=intent,
        decision_status=decision_status,
        admitted_size=impact_on_outcomes["adjusted_size"],
    )
    permission_fields = permission_result
    if permission_result["triggered"] and permission_result["action"] in {"DENY", "DELAY"}:
        return _permission_budget_response(
            status_code=permission_result["status_code"],
            budget_action=permission_result["action"],
            api_key=entitlement["api_key"],
            tier=entitlement["tier"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            temporal_fields=temporal_fields,
            loop_fields=loop_fields,
            telemetry_fields=telemetry_fields,
            permission_fields=permission_fields,
            compounded_pressure=decision_status == "CONSTRAIN",
            queue_fields=queue_fields,
            memory_fields=memory_fields,
        )
    if permission_result["triggered"] and permission_result["action"] == "REDUCE":
        decision_status = "REDUCE"
        impact_on_outcomes = {
            "requested_size": impact_on_outcomes["requested_size"],
            "adjusted_size": permission_result["adjusted_size"],
            "size_delta": None
            if impact_on_outcomes["requested_size"] is None or permission_result["adjusted_size"] is None
            else round(permission_result["adjusted_size"] - impact_on_outcomes["requested_size"], 2),
            "why_this_happened": "Cumulative permission budget is nearly exhausted, so Nova reduced the admitted request to fit remaining budget capacity.",
        }
        adjustment = (
            f"Reduce requested size from {parsed_size:g} to {permission_result['adjusted_size']:g} "
            "because remaining permission budget is limited."
        )
    historical_reference = build_historical_reference_from_reflex(reflex_memory_state)
    decision_context = {
        "intent": intent,
        "asset": asset,
        "requested_size": parsed_size,
        "regime": DEFAULT_REGIME,
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
        "reflex_influence_applied": reflex_memory_state.influence_applied,
    }
    constraint_analysis = build_constraint_analysis(
        intent=intent,
        asset=asset,
        size=parsed_size,
        guardrail=guardrail,
        decision_status=decision_status,
    )
    constraint_trace = _infer_domain_trace(
        api_key=entitlement["api_key"],
        intent=intent,
        asset=asset,
        venue=venue,
        strategy=strategy,
        decision_status=decision_status,
        guardrail=guardrail,
    )
    constraint_analysis.update({
        "constraint_category": constraint_trace["constraint_category"],
        "reflex_memory_class": constraint_trace["reflex_memory_class"],
        "domain_signal": constraint_trace["domain_signal"],
        "prevented_risk_type": constraint_trace["prevented_risk_type"],
        "telemetry_domain": constraint_trace["telemetry_domain"],
        "regime_context_applied": constraint_trace["regime_context_applied"],
        "related_prior_decisions": constraint_trace["related_prior_decisions"],
        "cross_decision_pressure": constraint_trace["cross_decision_pressure"],
        "accumulated_constraint_category": constraint_trace["accumulated_constraint_category"],
        "exposure_compounding_detected": constraint_trace["exposure_compounding_detected"],
    })
    if decision_status == "REDUCE":
        constraint_analysis.update({
            "constraint_category": "permission_budgeting",
            "advisory": adjustment,
            "why_this_happened": "Permission budgeting reduced the request because cumulative admitted exposure is approaching exhaustion.",
            "accumulated_constraint_category": "permission_budgeting",
        })
        constraint_trace.update({
            "constraint_category": "permission_budgeting",
            "reflex_memory_class": "permission_budgeting",
            "domain_signal": permission_fields["permission_budget_class"],
            "prevented_risk_type": "cumulative_permission_pressure",
            "telemetry_domain": "permission_budgeting",
            "accumulated_constraint_category": "permission_budgeting",
            "exposure_compounding_detected": True,
        })

    decision_admission_record = {
        "request_id": request_id,
        "request_snapshot": request_snapshot,
        "recorded_before_execution": True,
    }

    rejection_entry = None
    if decision_status == "VETO":
        rejection_entry = _record_rejection(
            timestamp=timestamp,
            constraint_category="guardrail_veto",
            reason=constraint_analysis["why_this_happened"],
            snapshot=decision_admission_record["request_snapshot"],
        )
        _record_loop_denial(
            api_key=entitlement["api_key"],
            intent=intent,
            asset=asset,
            size_raw=size,
            venue=venue,
            strategy=strategy,
            constraint_category="guardrail_veto",
        )

    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "regime": DEFAULT_REGIME,
        "guardrail": guardrail,
        "memory_context": historical_reference,
        "reflex_memory": reflex_memory_state.model_dump(),
        "transition_state": "stable_to_elevated_recent" if DEFAULT_REGIME == "Elevated Fragility" else "stable",
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
        "decision_admission_record": decision_admission_record,
        "decision_context": decision_context,
        "constraint_analysis": constraint_analysis,
        "constraint_trace": constraint_trace,
        "historical_reference": historical_reference,
        "impact_on_outcomes": impact_on_outcomes,
        "adjustment": adjustment,
        "decision_status": decision_status,
        "exception_register": [],
        "rejection_ledger": rejection_entry,
        "escalation_flag": False,
        "halt_recommendation": None,
        "integrity_state": "operational",
        "decision_count_window": temporal_fields["decision_count_window"],
        "cooldown_state": temporal_fields["cooldown_state"],
        "cooldown_active": temporal_fields["cooldown_active"],
        "retry_cooldown_expiry": temporal_fields["retry_cooldown_expiry"],
        "post_halt_quarantine_expiry": temporal_fields["post_halt_quarantine_expiry"],
        "temporal_constraint_triggered": temporal_fields["temporal_constraint_triggered"],
        "retry_count_by_family": loop_fields["retry_count_by_family"],
        "semantic_similarity_to_prior_denial": loop_fields["semantic_similarity_to_prior_denial"],
        "loop_classification": loop_fields["loop_classification"],
        "pressure_score": loop_fields["pressure_score"],
        "loop_integrity_state": loop_fields["loop_integrity_state"],
        "telemetry_reliability_score": telemetry_fields["telemetry_reliability_score"],
        "telemetry_freshness_state": telemetry_fields["telemetry_freshness_state"],
        "cross_source_disagreement": telemetry_fields["cross_source_disagreement"],
        "telemetry_integrity_state": telemetry_fields["telemetry_integrity_state"],
        "minimum_required_reliability": telemetry_fields["minimum_required_reliability"],
        "telemetry_admissible": telemetry_fields["telemetry_admissible"],
        "permission_budget_class": permission_fields["permission_budget_class"],
        "permission_budget_remaining": permission_fields["permission_budget_remaining"],
        "budget_consumed_by_request": permission_fields["budget_consumed_by_request"],
        "budget_exhausted": permission_fields["budget_exhausted"],
        "exception_budget_remaining": permission_fields["exception_budget_remaining"],
        "halt_release_required": halt_release_fields["halt_release_required"],
        "halt_release_authority": halt_release_fields["halt_release_authority"],
        "halt_release_evidence": halt_release_fields["halt_release_evidence"],
        "post_release_cooldown": halt_release_fields["post_release_cooldown"],
        "re_evaluation_required": halt_release_fields["re_evaluation_required"],
        "queue_priority": queue_fields["queue_priority"],
        "queue_position": queue_fields["queue_position"],
        "conflict_group_id": queue_fields["conflict_group_id"],
        "batch_review_required": queue_fields["batch_review_required"],
        "request_expiry_at": queue_fields["request_expiry_at"],
        "memory_influence_invoked": memory_fields["memory_influence_invoked"],
        "reflex_memory_class": memory_fields["reflex_memory_class"],
        "memory_confidence_weight": memory_fields["memory_confidence_weight"],
        "memory_age_state": memory_fields["memory_age_state"],
        "stale_memory_flag": memory_fields["stale_memory_flag"],
        **_default_human_intervention_fields(),
        **_default_system_state_fields(),
    }

    if asset:
        payload["asset"] = asset
    if intent:
        payload["intent"] = intent
    if parsed_size is not None:
        payload["size"] = parsed_size
    if venue:
        payload["venue"] = venue
    if strategy:
        payload["strategy"] = strategy

    _record_admission_state(
        api_key=entitlement["api_key"],
        request_id=decision_admission_record["request_id"],
        intent=intent,
        asset=asset,
        requested_size=parsed_size,
        decision_status=decision_status,
    )

    if halt_release_fields["re_evaluation_required"]:
        _halt_release_state_for_api_key(entitlement["api_key"])["re_evaluation_required"] = False
    payload = _apply_system_state(payload, entitlement["api_key"])
    payload = _apply_human_intervention_taxonomy(payload)
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/key-info")
def key_info(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)

    payload = {
        "owner": entitlement["owner"],
        "tier": entitlement["tier"],
        "monthly_quota": entitlement["monthly_quota"],
        "allowed_endpoints": entitlement["allowed_endpoints"],
    }
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/usage")
def get_usage(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)

    api_key = entitlement["api_key"]
    usage = _get_redis_usage(api_key) if _get_redis_client() else USAGE_TRACKING.get(api_key, {
        "total_calls": 0,
        "by_endpoint": {},
        "last_seen": None,
    })

    payload = {
        "usage": usage,
        "tier": entitlement["tier"],
    }

    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.post("/v1/usage/reset")
def reset_usage(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization, x_api_key)

    api_key = entitlement["api_key"]

    client = _get_redis_client()
    if client:
        client.delete(f"usage:{api_key}")
        client.delete(f"usage:{api_key}:endpoints")
    else:
        USAGE_TRACKING.pop(api_key, None)
        _persist_usage()

    usage = {
        "total_calls": 0,
        "by_endpoint": {},
        "last_seen": None,
    }

    payload = {
        "usage": usage,
        "tier": entitlement["tier"],
    }

    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)
