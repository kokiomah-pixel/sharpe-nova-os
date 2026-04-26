# Sharpe Nova OS — Project Report

**Status:** GTM-Ready (Policy B Implementation Complete)

**Last Updated:** March 20, 2026

---

## Executive Summary

Sharpe Nova OS is a decision-context infrastructure API that provisions pre-execution context to autonomous capital systems. The system is **operationally live**, implements **Policy B usage metering and quota enforcement**, and enforces **strict separation between billable decision logic and non-billable operational endpoints**.
This report documents the implementation of a decision discipline layer designed to improve the coherence and defensibility of capital decisions prior to execution.

---

## Policy B Implementation

### What Policy B Means

Nova meters **decision value**, not introspection or system management. This means:

- **Billable endpoints** (decision logic) count toward usage and consume quota
- **Non-billable endpoints** (support operations) do not meter or consume quota
- **Admin-only endpoints** are restricted to administrative tier and do not consume quota
- Payment rails, wallet integration, and settlement are not implemented in this repository.

### Billable Endpoints (Metered)

These endpoints increment usage counters and consume monthly quota:

- `GET /v1/context` – decision admission, reflex memory, and configured decision regime transitions for a deployment
- `GET /v1/regime` – current configured decision regime and epoch
- `GET /v1/epoch` – epoch hash and constitution snapshot

### Non-Billable Endpoints (Not Metered)

These endpoints require authentication where applicable, but do not increment usage or consume quota:

- `GET /health` – public healthcheck (no auth required)
- `GET /v1/key-info` – key metadata and entitlements (auth required, not metered)
- `GET /v1/usage` – accumulated usage stats (auth required, not metered)

### Admin-Only Endpoint (Non-Billable, Restricted)

- `POST /v1/usage/reset` – clears usage counters for an API key; admin tier only, does not consume quota

---

## Authentication & Authorization

### API Key Registry

Nova supports two modes:

#### 1. Legacy Single-Key Mode
Set `NOVA_API_KEY` environment variable. The key is treated as admin tier with unlimited quota.

#### 2. Registry Mode (Recommended)
Set `NOVA_KEYS_JSON` with a JSON object mapping keys to metadata:

```json
{
  "key-id": {
    "owner": "customer-name",
    "tier": "pro",
    "status": "active",
    "monthly_quota": 10000,
    "allowed_endpoints": [
      "/v1/regime",
      "/v1/epoch",
      "/v1/context",
      "/v1/key-info",
      "/v1/usage"
    ],
    "rate_limit": {
      "window_seconds": 60,
      "max_calls": 30
    }
  }
}
```

### Tier System

- **admin** – unrestricted access to all endpoints including `/v1/usage/reset`
- **pro** – access to decision endpoints and non-billable endpoints, excluding `/v1/usage/reset`
- **free** – same as pro, with lower monthly quota

---

## Usage Tracking

### Billing Behavior

Nova meters **only billable endpoints**. This ensures operators can call non-billable endpoints without incurring charges.

### Persistence

Usage state is persisted via one of two mechanisms:

#### File-Backed Persistence (Default)
- Usage counters are stored in a JSON file (default: `.usage.json`)
- Survives server restarts
- Single-instance deployments
- Set `NOVA_USAGE_FILE` to customize location

#### Redis-Backed Persistence (Scalable)
- Usage counters are stored in Redis (requires `NOVA_REDIS_URL`)
- Shared state across multiple instances
- Recommended for multi-instance or load-balanced deployments
- Each key has per-endpoint usage tracking

### Usage Data Structure

```json
{
  "total_calls": 42,
  "by_endpoint": {
    "/v1/context": 20,
    "/v1/regime": 15,
    "/v1/epoch": 7
  },
  "last_seen": "2026-03-20T16:00:00Z"
}
```

---

## Quota Enforcement

### Monthly Quota

Each API key has a `monthly_quota` field. When a billable endpoint is called:

1. Total usage for the key is checked
2. If total usage >= monthly_quota, the request returns HTTP 429 (Too Many Requests)
3. The quota is enforced **only for billable endpoints**

Non-billable endpoints (like `/v1/key-info`, `/v1/usage`) do not count toward or consume the quota, allowing operational calls without meter impact.

### Rate Limiting (Optional)

Keys can optionally define per-window rate limits:

```json
{
  "rate_limit": {
    "window_seconds": 60,
    "max_calls": 30
  }
}
```

This allows 30 calls per 60-second window, independent of monthly quota.

---

## Payload Signing

All responses (except `/health`) include an HMAC-SHA256 signature:

```json
{
  "epoch": 2461,
  "regime": "Elevated Fragility",
  "signature": "a1b2c3d4e5f6...",
  "tier": "pro"
}
```

Signature is computed over the JSON payload (sorted keys, no spaces) using `NOVA_SIGNING_SECRET`.

---

## Deployment Status

### API is Live

Nova API is deployed and operational.

- Accepts API key authentication via Bearer token
- Enforces endpoint access control
- Meters billable endpoints only
- Persists usage state

### Authentication Works

- Invalid keys are rejected (403)
- Inactive keys are rejected (403)
- Keys without endpoint permission are rejected (403)
- Admin-only restrictions are enforced (403 for non-admin)
- Allowed keys are authenticated successfully (200)

### Usage Tracking Works

- Billable endpoints (`/v1/context`, `/v1/regime`, `/v1/epoch`) increment usage counters
- Non-billable endpoints (`/v1/key-info`, `/v1/usage`) do not increment counters
- `/v1/usage` reports accurate billable consumption only
- File and Redis persistence both available

### Quota Enforcement Works

- Billable endpoints check monthly quota
- Non-billable endpoints bypass quota checks
- Exceeded quota returns 429
- Low-quota keys can still call non-billable endpoints unlimited times

### Policy B Monetization Implemented

- Only decision endpoints are metered (Policy B)
- Support endpoints are free (non-billable)
- Admin operations are restricted and not metered
- Separation between entitlement and billing is enforced in code

---

## Current GTM Position

Sharpe Nova OS is:
- **Technically operational** — API is live with authentication, usage tracking, and quota enforcement
- **Usage-metering enabled** — Policy B endpoint metering and quota enforcement implemented and tested
- **Ready for initial external onboarding** — documentation complete, test coverage comprehensive

---

## Testing

All required test cases have been implemented and pass:

- ✅ `/health` is public
- ✅ Billable endpoints increment usage
- ✅ Non-billable endpoints do not increment usage
- ✅ `/v1/usage/reset` is admin-only
- ✅ Quota only applies to billable endpoints
- ✅ Invalid key behavior works
- ✅ Inactive key behavior works (explicit test)
- ✅ Admin-only branch is directly validated (non-admin key with reset access)

Total: 15 tests passing, including Reflex Memory state, proof, and backward-compatibility coverage
---

## Verifiability

Nova outputs are designed to be cryptographically attestable.

Each decision can be anchored to a verifiable record, ensuring that:
- inputs were consistent
- constraints were applied
- outputs were not modified post-generation

This repository focuses on the decision layer.
Attestation infrastructure is introduced separately.
If used, Base serves as an anchoring/settlement layer and does not replace application-level entitlement or billing logic.

---

## Configuration Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `NOVA_API_KEY` | Legacy single key (admin tier) | `mytestkey` |
| `NOVA_KEYS_JSON` | Registry of API keys | JSON object |
| `NOVA_SIGNING_SECRET` | HMAC secret for payload signing | `secret123` |
| `NOVA_CONSTITUTION_VERSION` | Constitution version in responses | `v1.0` |
| `NOVA_EPOCH` | Default epoch number | `2461` |
| `NOVA_TIMESTAMP_UTC` | Default timestamp | `2026-03-20T16:00:00Z` |
| `NOVA_REGIME` | Default configured decision regime | `Elevated Fragility` |
| `NOVA_USAGE_FILE` | Path to usage JSON file | `.usage.json` |
| `NOVA_REDIS_URL` | Redis connection URL (optional) | `redis://localhost:6379` |

---

## GTM Readiness Checklist

- ✅ **Policy B enforced in code** – only billable endpoints increment usage
- ✅ **Tests prove Policy B behavior** – 6 required test cases implemented and passing
- ✅ **API is live and operational** – authentication, metering, quota all working
- ✅ **README documents billable vs non-billable** – clear endpoint classification
- ✅ **`.env.example` is accurate** – matches live deployment shape
- ✅ **Project report reflects actual behavior** – this document is the source of truth

---

## Known Limitations & Future Work

- Single-region deployment (no multi-region failover)
- Monthly quota is reset on a calendar basis (not rolling 30 days)
- Rate limiting state is not persistent across restarts in file mode (use Redis for persistence)
- No built-in analytics or reporting dashboard

---

## Support & Operations

For API key provisioning, onboarding, or operational questions, contact the Nova operations team.

For technical issues, review the [README.md](README.md) quickstart or enable debug logging via `LOG_LEVEL=debug`.
