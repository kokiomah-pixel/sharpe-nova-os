import os
import json
import hmac
import hashlib
from typing import Optional, Dict, Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Sharpe Nova OS API",
    version="1.2.0",
    description="Decision-context infrastructure for autonomous capital systems."
)

SIGNING_SECRET = os.getenv("NOVA_SIGNING_SECRET", "replace_me")
CONSTITUTION_VERSION = os.getenv("NOVA_CONSTITUTION_VERSION", "v1.0")
DEFAULT_EPOCH = int(os.getenv("NOVA_EPOCH", "2461"))
DEFAULT_TIMESTAMP = os.getenv("NOVA_TIMESTAMP_UTC", "2026-03-16T16:00:00Z")
DEFAULT_REGIME = os.getenv("NOVA_REGIME", "Elevated Fragility")

LEGACY_API_KEY = os.getenv("NOVA_API_KEY", "")
NOVA_KEYS_JSON = os.getenv("NOVA_KEYS_JSON", "")

# v1 in-memory usage tracking
USAGE_COUNTERS: Dict[str, int] = {}
ENDPOINT_COUNTERS: Dict[str, Dict[str, int]] = {}


def load_key_registry() -> Dict[str, Dict[str, Any]]:
    if NOVA_KEYS_JSON.strip():
        try:
            parsed = json.loads(NOVA_KEYS_JSON)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            raise RuntimeError("Invalid NOVA_KEYS_JSON format")

    if LEGACY_API_KEY:
        return {
            LEGACY_API_KEY: {
                "owner": "legacy",
                "tier": "admin",
                "status": "active",
                "monthly_quota": 1000000,
                "allowed_endpoints": ["/v1/regime", "/v1/epoch", "/v1/context", "/v1/key-info", "/v1/usage"]
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


def increment_usage(api_key: str, path: str) -> None:
    USAGE_COUNTERS[api_key] = USAGE_COUNTERS.get(api_key, 0) + 1

    if api_key not in ENDPOINT_COUNTERS:
        ENDPOINT_COUNTERS[api_key] = {}

    ENDPOINT_COUNTERS[api_key][path] = ENDPOINT_COUNTERS[api_key].get(path, 0) + 1


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

    increment_usage(api_key, path)

    current_usage = USAGE_COUNTERS.get(api_key, 0)
    monthly_quota = record.get("monthly_quota", 0)

    return {
        "api_key": api_key,
        "owner": record.get("owner"),
        "tier": record.get("tier"),
        "monthly_quota": monthly_quota,
        "current_usage": current_usage,
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
    if DEFAULT_REGIME == "Stress":
        return {
            "severity": "high",
            "advisory": "Avoid new risk and reduce exposure."
        }

    if DEFAULT_REGIME == "Elevated Fragility":
        if intent == "deploy_liquidity":
            return {
                "severity": "medium",
                "advisory": "Reduce size and avoid low-liquidity venues."
            }
        return {
            "severity": "medium",
            "advisory": "Tighten risk and reduce deployment pace."
        }

    return {
        "severity": "low",
        "advisory": "Proceed under normal risk controls."
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
def health():
    return {"status": "ok"}


@app.get("/v1/key-info")
def key_info(
    request: Request,
    authorization: Optional[str] = Header(default=None)
):
    entitlement = require_entitlement(request, authorization)

    payload = {
        "owner": entitlement["owner"],
        "tier": entitlement["tier"],
        "monthly_quota": entitlement["monthly_quota"],
        "current_usage": entitlement["current_usage"],
        "allowed_endpoints": entitlement["allowed_endpoints"],
    }
    payload["signature"] = sign_payload(payload)
    return payload


@app.get("/v1/usage")
def usage(
    request: Request,
    authorization: Optional[str] = Header(default=None)
):
    entitlement = require_entitlement(request, authorization)
    api_key = entitlement["api_key"]

    payload = {
        "owner": entitlement["owner"],
        "tier": entitlement["tier"],
        "monthly_quota": entitlement["monthly_quota"],
        "current_usage": entitlement["current_usage"],
        "remaining_quota_estimate": max(entitlement["monthly_quota"] - entitlement["current_usage"], 0),
        "endpoint_usage": ENDPOINT_COUNTERS.get(api_key, {}),
    }
    payload["signature"] = sign_payload(payload)
    return payload


@app.get("/v1/regime")
def regime(
    request: Request,
    authorization: Optional[str] = Header(default=None)
):
    entitlement = require_entitlement(request, authorization)

    payload = {
        "epoch": DEFAULT_EPOCH,
        "timestamp_utc": DEFAULT_TIMESTAMP,
        "regime": DEFAULT_REGIME,
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
    }
    payload["signature"] = sign_payload(payload)
    return payload


@app.get("/v1/epoch")
def epoch(
    request: Request,
    authorization: Optional[str] = Header(default=None)
):
    entitlement = require_entitlement(request, authorization)

    payload = {
        "epoch": DEFAULT_EPOCH,
        "timestamp_utc": DEFAULT_TIMESTAMP,
        "constitution_version": CONSTITUTION_VERSION,
        "hash": epoch_hash(
            DEFAULT_EPOCH,
            DEFAULT_TIMESTAMP,
            CONSTITUTION_VERSION,
            DEFAULT_REGIME
        ),
        "tier": entitlement["tier"],
    }
    payload["signature"] = sign_payload(payload)
    return payload


@app.get("/v1/context")
def context(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    intent: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    size: Optional[float] = Query(default=None),
):
    entitlement = require_entitlement(request, authorization)

    payload = {
        "epoch": DEFAULT_EPOCH,
        "timestamp_utc": DEFAULT_TIMESTAMP,
        "regime": DEFAULT_REGIME,
        "guardrail": build_guardrail(intent, asset, size),
        "memory_context": build_memory_context(),
        "constitution_version": CONSTITUTION_VERSION,
        "tier": entitlement["tier"],
    }

    if asset:
        payload["asset"] = asset
    if intent:
        payload["intent"] = intent
    if size is not None:
        payload["size"] = size

    payload["signature"] = sign_payload(payload)
    return payload
