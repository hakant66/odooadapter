# OdooSyncO-like Connector Platform (Monorepo)

This repository implements a production-oriented scaffold for a bi-directional integration platform inspired by OdooSyncO.

## Stack

- `apps/core-svc`: FastAPI core integration brain
- `apps/mcp`: Express-based webhook gateway and connector edge
- `apps/web`: Next.js control plane UI
- Postgres: system of record
- Redis: queue + ephemeral state
- Qdrant: vector matching (for mapping suggestions)
- Ollama: assistive SLM for explainability/suggestions

## Quick Start

1. Start all services (auto-creates `.env` and auto-resolves busy ports):

```bash
./scripts/dev-up.sh
```

Or bootstrap DB schema only:

```bash
./scripts/db-bootstrap.sh
```

2. Endpoints (ports may differ if defaults were busy; script prints final URLs):

- Core API: `http://localhost:8000/docs`
- MCP health: `http://localhost:3001/health`
- Web UI: `http://localhost:3000`
- Qdrant: `http://localhost:6333/dashboard`
- Ollama API: `http://localhost:11434`

## Core Concepts Implemented

- Multi-tenant entities and connection/account linking
- Canonical model + external mapping table
- Idempotent event ingestion
- Sync jobs with retries and dead-letter status
- Outbox pattern table for reliable publication intent
- Webhook ingestion decoupled from heavy processing
- Background worker consuming Redis queue
- Alembic migration-based DB lifecycle
- Real connector adapters for Shopify and Odoo (JSON-RPC/XML-RPC)

## Connector Credentials

Secrets are stored in encrypted `credential_vault` rows and referenced by `connections.credential_ref`.
Do not place raw tokens/passwords in `metadata`.

Create a connection with encrypted credential payload:

```json
{
  "tenant_id": "TENANT_ID",
  "connector": "shopify",
  "external_account_id": "your-store.myshopify.com",
  "credential_payload": { "access_token": "shpat_xxx" },
  "metadata": {
    "shop_domain": "your-store.myshopify.com",
    "api_version": "2024-10"
  }
}
```

Odoo connection example:

```json
{
  "tenant_id": "TENANT_ID",
  "connector": "odoo",
  "external_account_id": "prod_db",
  "credential_payload": {
    "username": "admin@example.com",
    "password": "secret"
  },
  "metadata": {
    "base_url": "https://odoo.example.com",
    "database": "prod_db",
    "protocol": "jsonrpc"
  }
}
```

## Shopify OAuth Install Flow

Configure `.env`:

- `SHOPIFY_CLIENT_ID`
- `SHOPIFY_CLIENT_SECRET`
- `CORE_PUBLIC_BASE_URL` (public URL to core API callback)

Start OAuth:

`GET /oauth/shopify/start?tenant_id=TENANT_ID&shop=your-store.myshopify.com`

Response includes `authorize_url`. Redirect merchant to that URL.

Shopify callback endpoint:

`GET /oauth/shopify/callback`

On success, core:

- Exchanges `code` for access token
- Encrypts token into `credential_vault`
- Upserts active `shopify` connection with non-secret metadata

Legacy fallback: JSON in `credential_ref` is still supported for older rows, but new integrations should always use vault-backed credentials.

Non-secret Shopify metadata:

```json
{
  "shop_domain": "your-store.myshopify.com",
  "api_version": "2024-10"
}
```

## Triggering Adapter Jobs

Use `POST /jobs/manual`:

```json
{
  "tenant_id": "TENANT_ID",
  "connector": "shopify",
  "job_type": "IMPORT_ORDERS",
  "entity_type": "orders",
  "payload": { "since_cursor": "2026-03-01T00:00:00Z" }
}
```

Supported `job_type` values in worker:

- `IMPORT_ORDERS`
- `IMPORT_PRODUCTS`
- `IMPORT_REFUNDS`
- `IMPORT_EMAILS`
- `EXPORT_PRODUCT`
- `EXPORT_FULFILLMENT`

Trigger Odoo inbound email sync (messages created by Odoo mail aliases/fetchmail):

`POST /sync/emails/import`

```json
{
  "tenant_id": "TENANT_ID",
  "connector": "odoo",
  "since_cursor": "2026-03-01T00:00:00Z",
  "target_address": "support@example.com",
  "source": "odoo_alias_fetchmail",
  "limit": 200
}
```

List synced inbound emails:

`GET /emails?tenant_id=TENANT_ID&to_address=support@example.com&limit=100`

## Inbound Email Webhook Flow

MCP now accepts provider-posted inbound emails:

`POST /webhooks/email/inbound`

Required headers:

- `x-tenant-slug`
- `x-email-webhook-signature` (base64 `HMAC-SHA256(raw_body, INBOUND_EMAIL_WEBHOOK_SECRET)`)

Optional headers:

- `x-email-delivery-id`
- `x-inbound-target-address`
- `x-connector` (defaults to `odoo`)

Webhook payload is normalized into an `emails/inbound` event and queued to `sync:events`.
Core worker creates/upserts canonical email rows from these webhook events.

## UI Operations

In the jobs table:

- `Retry` appears for `failed` and `deadletter` jobs.
- `Dead-letter` appears for `queued`, `running`, and `failed` jobs.

## Service Contracts

- MCP receives external webhooks and writes normalized envelopes to Redis list `sync:events`
- Core worker consumes `sync:events`, deduplicates by idempotency key, and creates `sync_jobs`
- Core API exposes control-plane endpoints for tenants, connections, jobs, and replay/retry
