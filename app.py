import json
import os
import hmac
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import redis
import fakeredis
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()


def get_current_timestamp() -> str:
    fixed = os.getenv("NOVA_TIMESTAMP_UTC")
    if fixed:
        return fixed
    return datetime.now(timezone.utc).isoformat()


def get_current_epoch() -> int:
    fixed = os.getenv("NOVA_EPOCH")
    if fixed:
        return int(fixed)
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc).isoformat()

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
    if NOVA_KEYS_JSON.strip():
        try:
            parsed = json.loads(NOVA_KEYS_JSON)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            raise RuntimeError("Invalid NOVA_KEYS_JSON format")

    # fallback so your current live key keeps working
    if LEGACY_API_KEY:
        return {
            LEGACY_API_KEY: {
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
            }
        }

    return {}


def get_api_key_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.replace("Bearer ", "", 1).strip()


def get_key_record(api_key: str) -> Dict[str, Any]:
    registry = load_key_registry()

    if api_key not in registry:
        raise HTTPException(status_code=403, detail="Invalid API key")

    record = registry[api_key]

    if record.get("status") != "active":
        raise HTTPException(status_code=403, detail="Inactive API key")

    return record


def require_entitlement(
    request: Request,
    authorization: Optional[str]
) -> Dict[str, Any]:
    api_key = get_api_key_from_header(authorization)
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
    }


def sign_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(
        SIGNING_SECRET.encode("utf-8"),
        encoded,
        hashlib.sha256
    ).hexdigest()


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
        if intent == "deploy_liquidity":
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/regime")
def get_regime(
    request: Request,
    authorization: Optional[str] = Header(default=None)
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)
    epoch = get_current_epoch()
    timestamp = get_current_timestamp()

    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "regime": DEFAULT_REGIME,
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
    }
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/epoch")
def get_epoch(
    request: Request,
    authorization: Optional[str] = Header(default=None)
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)
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
    intent: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    size: Optional[float] = Query(default=None),
    venue: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)
    epoch = get_current_epoch()
    timestamp = get_current_timestamp()

    payload = {
        "epoch": epoch,
        "timestamp_utc": timestamp,
        "regime": DEFAULT_REGIME,
        "guardrail": build_guardrail(intent=intent, asset=asset, size=size),
        "memory_context": build_memory_context(),
        "transition_state": "stable_to_elevated_recent" if DEFAULT_REGIME == "Elevated Fragility" else "stable",
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
    }

    if asset:
        payload["asset"] = asset
    if intent:
        payload["intent"] = intent
    if size is not None:
        payload["size"] = size
    if venue:
        payload["venue"] = venue
    if strategy:
        payload["strategy"] = strategy

    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/key-info")
def key_info(
    request: Request,
    authorization: Optional[str] = Header(default=None)
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)

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
    authorization: Optional[str] = Header(default=None)
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)

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
    authorization: Optional[str] = Header(default=None)
) -> JSONResponse:
    entitlement = require_entitlement(request, authorization)

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
