import importlib
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure the repo root is on sys.path so we can import the app module
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _make_client(tmp_path, env: dict):
    # Ensure environment is clean & deterministic for each test
    # Remove any known vars that may have been set by previous tests
    for key in [
        "NOVA_API_KEY",
        "NOVA_KEYS_JSON",
        "NOVA_USAGE_FILE",
        "NOVA_REDIS_URL",
    ]:
        os.environ.pop(key, None)

    os.environ.update(env)

    # Reload app module after environment changes so config is applied
    import app
    importlib.reload(app)

    return TestClient(app.app)


def test_health_endpoint():
    client = _make_client(tmp_path=None, env={"NOVA_API_KEY": "mytestkey"})
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_protected_endpoints_require_bearer():
    client = _make_client(tmp_path=None, env={"NOVA_API_KEY": "mytestkey"})
    r = client.get("/v1/regime")
    assert r.status_code == 401


def test_invalid_key_is_rejected():
    client = _make_client(tmp_path=None, env={"NOVA_API_KEY": "mytestkey"})
    r = client.get("/v1/regime", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 403


def test_usage_and_reset_persist(tmp_path):
    usage_file = tmp_path / "usage.json"
    client = _make_client(
        tmp_path,
        env={
            "NOVA_API_KEY": "mytestkey",
            "NOVA_USAGE_FILE": str(usage_file),
        },
    )

    # first call increments
    r1 = client.get("/v1/usage", headers={"Authorization": "Bearer mytestkey"})
    assert r1.status_code == 200
    assert r1.json()["usage"]["total_calls"] >= 1

    # reset clears counts
    r2 = client.post("/v1/usage/reset", headers={"Authorization": "Bearer mytestkey"})
    assert r2.status_code == 200
    assert r2.json()["usage"]["total_calls"] == 0

    # ensure persisted file exists and is valid JSON
    assert usage_file.exists()
    data = json.loads(usage_file.read_text(encoding="utf-8"))
    # After reset, the file may be empty (usage cleared) or still contain a zero record
    assert data == {} or ("mytestkey" in data)


def test_monthly_quota_enforced(tmp_path):
    # Create a key that only allows 1 call per month
    key_data = {
        "quota_user": {
            "owner": "test",
            "tier": "standard",
            "status": "active",
            "monthly_quota": 1,
            "allowed_endpoints": ["/v1/regime"],
        }
    }
    client = _make_client(
        tmp_path,
        env={
            "NOVA_KEYS_JSON": json.dumps(key_data),
            "NOVA_USAGE_FILE": str(tmp_path / "usage_quota.json"),
        },
    )

    r1 = client.get("/v1/regime", headers={"Authorization": "Bearer quota_user"})
    assert r1.status_code == 200

    r2 = client.get("/v1/regime", headers={"Authorization": "Bearer quota_user"})
    assert r2.status_code == 429


def test_rate_limit_enforced(tmp_path):
    key_data = {
        "rate_user": {
            "owner": "test",
            "tier": "standard",
            "status": "active",
            "monthly_quota": 1000,
            "rate_limit": {"window_seconds": 60, "max_calls": 1},
            "allowed_endpoints": ["/v1/regime"],
        }
    }
    client = _make_client(
        tmp_path,
        env={
            "NOVA_KEYS_JSON": json.dumps(key_data),
            "NOVA_USAGE_FILE": str(tmp_path / "usage_rate.json"),
        },
    )

    r1 = client.get("/v1/regime", headers={"Authorization": "Bearer rate_user"})
    assert r1.status_code == 200

    r2 = client.get("/v1/regime", headers={"Authorization": "Bearer rate_user"})
    assert r2.status_code == 429


def test_redis_backend_usage_and_quota(tmp_path):
    key_data = {
        "redis_user": {
            "owner": "test",
            "tier": "admin",
            "status": "active",
            "monthly_quota": 2,
            "allowed_endpoints": ["/v1/usage"],
        }
    }
    client = _make_client(
        tmp_path,
        env={
            "NOVA_KEYS_JSON": json.dumps(key_data),
            "NOVA_REDIS_URL": "fakeredis://",
        },
    )

    # First call works
    r1 = client.get("/v1/usage", headers={"Authorization": "Bearer redis_user"})
    assert r1.status_code == 200

    # Second call works (monthly quota is 2)
    r2 = client.get("/v1/usage", headers={"Authorization": "Bearer redis_user"})
    assert r2.status_code == 200

    # Third call should be refused by quota
    r3 = client.get("/v1/usage", headers={"Authorization": "Bearer redis_user"})
    assert r3.status_code == 429
