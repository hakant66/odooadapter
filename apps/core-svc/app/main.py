import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.schemas import (
    ConnectionCreate,
    ConnectionRead,
    DeadletterResponse,
    EmailRead,
    EmailSyncTriggerRequest,
    EventEnvelope,
    HealthResponse,
    JobRead,
    ManualJobCreate,
    OAuthCallbackResponse,
    OAuthStartResponse,
    RetryResponse,
    SyncTriggerRequest,
    TenantCreate,
    TenantRead,
)
from app.services import (
    consume_oauth_state,
    create_connection,
    create_manual_job,
    create_oauth_state,
    create_tenant,
    get_oauth_state,
    get_tenant_by_id,
    get_tenant_by_slug,
    list_emails,
    list_jobs,
    mark_job_deadletter,
    queue_job_from_event,
    retry_job,
    store_encrypted_credentials,
)
from app.security import CredentialCipher

settings = get_settings()
app = FastAPI(title="Odoo Adapter Core Service", version="0.1.0")
cipher = CredentialCipher(settings.credential_encryption_key)


@app.on_event("startup")
def startup() -> None:
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=settings.app_name, ok=True)


@app.post("/tenants", response_model=TenantRead)
def create_tenant_endpoint(body: TenantCreate, db: Session = Depends(get_db)) -> TenantRead:
    tenant = create_tenant(db, body.name, body.slug)
    return TenantRead(id=tenant.id, name=tenant.name, slug=tenant.slug)


@app.post("/connections", response_model=ConnectionRead)
def create_connection_endpoint(
    body: ConnectionCreate, db: Session = Depends(get_db)
) -> ConnectionRead:
    if not body.credential_ref and not body.credential_payload:
        raise HTTPException(
            status_code=400,
            detail="provide credential_payload (recommended) or credential_ref",
        )

    credential_ref = body.credential_ref
    if body.credential_payload:
        encrypted = cipher.encrypt(json.dumps(body.credential_payload))
        vault = store_encrypted_credentials(
            db,
            tenant_id=body.tenant_id,
            connector=body.connector,
            encrypted_payload=encrypted,
        )
        credential_ref = vault.id

    conn = create_connection(
        db,
        tenant_id=body.tenant_id,
        connector=body.connector,
        external_account_id=body.external_account_id,
        credential_ref=credential_ref,
        metadata=body.metadata,
    )
    return ConnectionRead(
        id=conn.id,
        tenant_id=conn.tenant_id,
        connector=conn.connector,
        external_account_id=conn.external_account_id,
        status=conn.status,
    )


@app.get("/oauth/shopify/start", response_model=OAuthStartResponse)
def oauth_shopify_start(
    tenant_id: str = Query(...),
    shop: str = Query(...),
    db: Session = Depends(get_db),
) -> OAuthStartResponse:
    if not settings.shopify_client_id:
        raise HTTPException(status_code=500, detail="missing shopify client configuration")

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    state_row = create_oauth_state(
        db,
        tenant_id=tenant_id,
        connector="shopify",
        payload={"shop": shop},
    )

    redirect_uri = f"{settings.core_public_base_url}/oauth/shopify/callback"
    params = urlencode(
        {
            "client_id": settings.shopify_client_id,
            "scope": settings.shopify_scopes,
            "redirect_uri": redirect_uri,
            "state": state_row.state,
        }
    )
    authorize_url = f"https://{shop}/admin/oauth/authorize?{params}"
    return OAuthStartResponse(authorize_url=authorize_url, state=state_row.state)


@app.get("/oauth/shopify/callback", response_model=OAuthCallbackResponse)
def oauth_shopify_callback(
    request: Request,
    code: str = Query(...),
    shop: str = Query(...),
    state: str = Query(...),
    hmac_value: str = Query(..., alias="hmac"),
    db: Session = Depends(get_db),
) -> OAuthCallbackResponse:
    if not settings.shopify_client_id or not settings.shopify_client_secret:
        raise HTTPException(status_code=500, detail="missing shopify client configuration")

    pairs: list[str] = []
    for key, value in request.query_params.multi_items():
        if key in {"hmac", "signature"}:
            continue
        pairs.append(f"{key}={value}")
    message = "&".join(sorted(pairs))
    expected_hmac = hmac.new(
        settings.shopify_client_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hmac, hmac_value):
        raise HTTPException(status_code=401, detail="invalid oauth callback signature")

    state_row = get_oauth_state(db, connector="shopify", state=state)
    if not state_row:
        raise HTTPException(status_code=400, detail="invalid or expired state")

    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_client_id,
                "client_secret": settings.shopify_client_secret,
                "code": code,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"token exchange failed status={response.status_code}")

    body = response.json()
    access_token = body.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="missing access token in response")

    encrypted = cipher.encrypt(json.dumps({"access_token": access_token}))
    vault = store_encrypted_credentials(
        db,
        tenant_id=state_row.tenant_id,
        connector="shopify",
        encrypted_payload=encrypted,
        secret_type="oauth_token",
    )

    conn = create_connection(
        db,
        tenant_id=state_row.tenant_id,
        connector="shopify",
        external_account_id=shop,
        credential_ref=vault.id,
        metadata={
            "shop_domain": shop,
            "api_version": "2024-10",
            "scope": body.get("scope", ""),
        },
    )
    consume_oauth_state(db, state_row)

    return OAuthCallbackResponse(
        connection_id=conn.id,
        tenant_id=conn.tenant_id,
        connector=conn.connector,
        external_account_id=conn.external_account_id,
    )


@app.post("/events", response_model=JobRead | None)
def ingest_event(body: EventEnvelope, db: Session = Depends(get_db)):
    tenant = get_tenant_by_slug(db, body.tenant_slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    job = queue_job_from_event(
        db,
        tenant_id=tenant.id,
        connector=body.connector,
        event_type=body.event_type,
        delivery_id=body.delivery_id,
        payload=body.payload,
        trigger="webhook",
    )

    if not job:
        return None

    return JobRead(
        id=job.id,
        tenant_id=job.tenant_id,
        connector=job.connector,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        trigger=job.trigger,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        status=job.status,
        attempts=job.attempts,
        next_run_at=job.next_run_at,
        error_code=job.error_code,
    )


@app.get("/jobs", response_model=list[JobRead])
def list_jobs_endpoint(tenant_id: str | None = None, db: Session = Depends(get_db)) -> list[JobRead]:
    jobs = list_jobs(db, tenant_id=tenant_id)
    return [
        JobRead(
            id=job.id,
            tenant_id=job.tenant_id,
            connector=job.connector,
            entity_type=job.entity_type,
            entity_id=job.entity_id,
            trigger=job.trigger,
            job_type=job.job_type,
            idempotency_key=job.idempotency_key,
            status=job.status,
            attempts=job.attempts,
            next_run_at=job.next_run_at,
            error_code=job.error_code,
        )
        for job in jobs
    ]


@app.post("/jobs/{job_id}/retry", response_model=RetryResponse)
def retry_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> RetryResponse:
    job = retry_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return RetryResponse(id=job.id, status=job.status)


@app.post("/jobs/{job_id}/deadletter", response_model=DeadletterResponse)
def deadletter_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> DeadletterResponse:
    job = mark_job_deadletter(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return DeadletterResponse(id=job.id, status=job.status)


@app.post("/sync/orders/import", response_model=JobRead)
def trigger_order_import(body: SyncTriggerRequest, db: Session = Depends(get_db)) -> JobRead:
    job = queue_job_from_event(
        db,
        tenant_id=body.tenant_id,
        connector=body.connector,
        event_type="orders/poll",
        delivery_id=f"poll-{body.connector}-{body.entity_type}-{datetime.utcnow().isoformat()}",
        payload={"since_cursor": body.since_cursor},
        trigger="poll",
    )
    if not job:
        raise HTTPException(status_code=409, detail="duplicate poll event")

    return JobRead(
        id=job.id,
        tenant_id=job.tenant_id,
        connector=job.connector,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        trigger=job.trigger,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        status=job.status,
        attempts=job.attempts,
        next_run_at=job.next_run_at,
        error_code=job.error_code,
    )


@app.post("/jobs/manual", response_model=JobRead)
def create_manual_job_endpoint(body: ManualJobCreate, db: Session = Depends(get_db)) -> JobRead:
    job = create_manual_job(
        db,
        tenant_id=body.tenant_id,
        connector=body.connector,
        job_type=body.job_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        payload=body.payload,
    )
    return JobRead(
        id=job.id,
        tenant_id=job.tenant_id,
        connector=job.connector,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        trigger=job.trigger,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        status=job.status,
        attempts=job.attempts,
        next_run_at=job.next_run_at,
        error_code=job.error_code,
    )


@app.post("/sync/emails/import", response_model=JobRead)
def trigger_email_import(body: EmailSyncTriggerRequest, db: Session = Depends(get_db)) -> JobRead:
    job = queue_job_from_event(
        db,
        tenant_id=body.tenant_id,
        connector=body.connector,
        event_type="emails/poll",
        delivery_id=f"poll-{body.connector}-emails-{datetime.utcnow().isoformat()}",
        payload={
            "since_cursor": body.since_cursor,
            "target_address": body.target_address,
            "source": body.source,
            "limit": body.limit,
        },
        trigger="poll",
    )
    if not job:
        raise HTTPException(status_code=409, detail="duplicate poll event")

    return JobRead(
        id=job.id,
        tenant_id=job.tenant_id,
        connector=job.connector,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        trigger=job.trigger,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        status=job.status,
        attempts=job.attempts,
        next_run_at=job.next_run_at,
        error_code=job.error_code,
    )


@app.get("/emails", response_model=list[EmailRead])
def list_emails_endpoint(
    tenant_id: str,
    to_address: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[EmailRead]:
    rows = list_emails(db, tenant_id=tenant_id, to_address=to_address, limit=limit)
    return [
        EmailRead(
            id=row.id,
            tenant_id=row.tenant_id,
            subject=row.subject,
            from_address=row.from_address,
            to_address=row.to_address,
            source=row.source,
            status=row.status,
            received_at=row.received_at,
        )
        for row in rows
    ]
