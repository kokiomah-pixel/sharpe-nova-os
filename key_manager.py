import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple

KEY_STORE = Path("keys.json")
_KEY_LOCK = Lock()


def get_quota(tier: str) -> Optional[int]:
    return {
        "emerging": 50000,
        "core": 200000,
        "enterprise": None,
        "free": 1000,
        "pro": 100000,
        "admin": 1000000,
    }.get((tier or "").lower(), 1000)


def generate_api_key() -> str:
    return f"nova_{uuid.uuid4().hex[:24]}"


def load_keys() -> Dict[str, Dict[str, Any]]:
    if not KEY_STORE.exists():
        return {}
    try:
        return json.loads(KEY_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_keys(data: Dict[str, Dict[str, Any]]) -> None:
    KEY_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = KEY_STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(KEY_STORE)


def _normalize_owner(owner: str) -> str:
    return (owner or "stripe_customer").strip().lower()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_stripe_identity(
    record: Dict[str, Any],
    stripe_customer_id: Optional[str],
    stripe_subscription_id: Optional[str],
    stripe_price_id: Optional[str],
    status: Optional[str],
    last_paid_at: Optional[str],
) -> None:
    if stripe_customer_id:
        record["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        record["stripe_subscription_id"] = stripe_subscription_id
    if stripe_price_id:
        record["stripe_price_id"] = stripe_price_id
    if status:
        record["status"] = status
    if last_paid_at:
        record["last_paid_at"] = last_paid_at


def store_key(
    api_key: str,
    tier: str,
    owner: str = "stripe",
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    stripe_price_id: Optional[str] = None,
    status: str = "active",
    last_paid_at: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_tier = (tier or "free").lower()
    quota = get_quota(normalized_tier)
    now = _now_utc_iso()
    record = {
        "owner": _normalize_owner(owner),
        "tier": normalized_tier,
        "created_at": now,
        "updated_at": now,
        "status": status,
        "quota": quota,
        "monthly_quota": quota,
        "allowed_endpoints": [
            "/v1/regime",
            "/v1/epoch",
            "/v1/context",
            "/v1/key-info",
            "/v1/usage",
            "/health",
        ],
    }
    _merge_stripe_identity(
        record,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        status=status,
        last_paid_at=last_paid_at,
    )

    with _KEY_LOCK:
        data = load_keys()
        data[api_key] = record
        _write_keys(data)

    return record


def find_key_by_owner(owner: str) -> Optional[str]:
    normalized_owner = _normalize_owner(owner)
    with _KEY_LOCK:
        data = load_keys()
        matches: list[Tuple[str, Dict[str, Any]]] = [
            (api_key, record)
            for api_key, record in data.items()
            if isinstance(record, dict) and _normalize_owner(str(record.get("owner", ""))) == normalized_owner
        ]
        if not matches:
            return None

        # Prefer active key; otherwise latest record.
        active = [item for item in matches if item[1].get("status") == "active"]
        candidate_pool = active or matches
        candidate_pool.sort(key=lambda item: str(item[1].get("created_at", "")), reverse=True)
        return candidate_pool[0][0]


def find_key_by_stripe_customer_id(stripe_customer_id: str) -> Optional[str]:
    if not stripe_customer_id:
        return None

    with _KEY_LOCK:
        data = load_keys()
    for api_key, record in data.items():
        if record.get("stripe_customer_id") == stripe_customer_id:
            return api_key

    return None


def update_key_record(api_key: str, **updates: Any) -> Optional[Dict[str, Any]]:
    with _KEY_LOCK:
        data = load_keys()
        record = data.get(api_key)
        if not record:
            return None

        if "owner" in updates and updates["owner"] is not None:
            updates["owner"] = _normalize_owner(str(updates["owner"]))

        if "tier" in updates and updates["tier"] is not None:
            normalized_tier = str(updates["tier"]).lower()
            updates["tier"] = normalized_tier
            updates["quota"] = get_quota(normalized_tier)
            updates["monthly_quota"] = get_quota(normalized_tier)

        record.update({k: v for k, v in updates.items() if v is not None})
        record["updated_at"] = _now_utc_iso()
        data[api_key] = record
        _write_keys(data)
        return record


def activate_or_renew_key(
    api_key: str,
    tier: str,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    stripe_price_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return update_key_record(
        api_key,
        tier=tier,
        status="active",
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        last_paid_at=_now_utc_iso(),
    )


# Backward-compatible wrappers used by app.py before lifecycle refactor.
def update_key_tier(
    api_key: str,
    tier: str,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    stripe_price_id: Optional[str] = None,
    last_paid_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return update_key_record(
        api_key,
        tier=tier,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        last_paid_at=last_paid_at,
    )


def mark_key_active(api_key: str, last_paid_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return update_key_record(api_key, status="active", last_paid_at=last_paid_at)


def suspend_keys_for_owner(owner: str) -> int:
    normalized_owner = _normalize_owner(owner)
    count = 0
    with _KEY_LOCK:
        data = load_keys()
        for api_key, record in data.items():
            if not isinstance(record, dict):
                continue
            if _normalize_owner(str(record.get("owner", ""))) != normalized_owner:
                continue
            if (record.get("status") or "").lower() != "inactive":
                record["status"] = "suspended"
                record["updated_at"] = _now_utc_iso()
                data[api_key] = record
                count += 1
        _write_keys(data)
    return count


def deactivate_keys_for_owner(owner: str) -> int:
    normalized_owner = _normalize_owner(owner)
    count = 0
    with _KEY_LOCK:
        data = load_keys()
        for api_key, record in data.items():
            if not isinstance(record, dict):
                continue
            if _normalize_owner(str(record.get("owner", ""))) != normalized_owner:
                continue
            record["status"] = "inactive"
            record["updated_at"] = _now_utc_iso()
            data[api_key] = record
            count += 1
        _write_keys(data)
    return count


def suspend_key_by_stripe_customer_id(stripe_customer_id: str) -> bool:
    api_key = find_key_by_stripe_customer_id(stripe_customer_id)
    if not api_key:
        return False
    return update_key_record(api_key, status="suspended") is not None


def deactivate_key_by_stripe_customer_id(stripe_customer_id: str) -> bool:
    api_key = find_key_by_stripe_customer_id(stripe_customer_id)
    if not api_key:
        return False
    return update_key_record(api_key, status="inactive") is not None


def manual_create_key(email: str, tier: str) -> str:
    api_key = generate_api_key()
    store_key(api_key, tier=tier, owner=email, status="active")
    print(f"[MANUAL] {email} -> {api_key}")
    return api_key
