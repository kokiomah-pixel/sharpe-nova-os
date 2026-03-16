import os
import json
import hmac
import hashlib
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Sharpe Nova OS API",
    version="1.0.0",
    description="Decision-context infrastructure for autonomous capital systems."
)

API_KEY = os.getenv("NOVA_API_KEY", "")
SIGNING_SECRET = os.getenv("NOVA_SIGNING_SECRET", "replace_me")
CONSTITUTION_VERSION = os.getenv("NOVA_CONSTITUTION_VERSION", "v1.0")
DEFAULT_EPOCH = int(os.getenv("NOVA_EPOCH", "2461"))
DEFAULT_TIMESTAMP = os.getenv("NOVA_TIMESTAMP_UTC", "2026-03-31T14:00:00Z")
DEFAULT_REGIME = os.getenv("NOVA_REGIME", "Elevated Fragility")


def require_api_key(authorization: Optional[str]) -> None:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    supplied = authorization.replace("Bearer ", "", 1).strip()
    if supplied != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


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
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/regime")
def get_regime(authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    require_api_key(authorization)

    payload = {
        "epoch": DEFAULT_EPOCH,
        "timestamp_utc": DEFAULT_TIMESTAMP,
        "regime": DEFAULT_REGIME,
        "constitution_version": CONSTITUTION_VERSION,
    }
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/epoch")
def get_epoch(authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    require_api_key(authorization)

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
    }
    payload["signature"] = sign_payload(payload)
    return JSONResponse(payload)


@app.get("/v1/context")
def get_context(
    authorization: Optional[str] = Header(default=None),
    intent: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    size: Optional[float] = Query(default=None),
    venue: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
) -> JSONResponse:
    require_api_key(authorization)

    payload = {
        "epoch": DEFAULT_EPOCH,
        "timestamp_utc": DEFAULT_TIMESTAMP,
        "regime": DEFAULT_REGIME,
        "guardrail": build_guardrail(intent=intent, asset=asset, size=size),
        "memory_context": build_memory_context(),
        "transition_state": "stable_to_elevated_recent" if DEFAULT_REGIME == "Elevated Fragility" else "stable",
        "constitution_version": CONSTITUTION_VERSION,
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
