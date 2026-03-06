import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    CanonicalEmail,
    Connection,
    ExternalEntityMap,
    CanonicalOrder,
    CredentialVault,
    GmailOAuthAccount,
    OAuthState,
    OutboxEvent,
    SyncJob,
    Tenant,
    WebhookEvent,
)


def create_tenant(db: Session, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def create_connection(
    db: Session,
    tenant_id: str,
    connector: str,
    external_account_id: str,
    credential_ref: str,
    metadata: dict,
) -> Connection:
    existing = db.scalar(
        select(Connection).where(
            Connection.tenant_id == tenant_id,
            Connection.connector == connector,
        )
    )
    if existing:
        existing.external_account_id = external_account_id
        existing.credential_ref = credential_ref
        existing.metadata_json = metadata
        existing.status = "active"
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    connection = Connection(
        tenant_id=tenant_id,
        connector=connector,
        external_account_id=external_account_id,
        credential_ref=credential_ref,
        metadata_json=metadata,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def store_encrypted_credentials(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    encrypted_payload: str,
    secret_type: str = "api_token",
) -> CredentialVault:
    row = CredentialVault(
        tenant_id=tenant_id,
        connector=connector,
        secret_type=secret_type,
        encrypted_payload=encrypted_payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_decrypted_credentials(
    db: Session,
    *,
    credential_ref: str,
    decrypt_fn,
) -> dict:
    # Backward compatibility for legacy rows that stored JSON in credential_ref.
    try:
        legacy = json.loads(credential_ref)
        if isinstance(legacy, dict):
            return legacy
    except json.JSONDecodeError:
        pass

    vault = db.scalar(select(CredentialVault).where(CredentialVault.id == credential_ref))
    if not vault:
        return {}
    plaintext = decrypt_fn(vault.encrypted_payload)
    value = json.loads(plaintext)
    return value if isinstance(value, dict) else {}


def get_connection(db: Session, tenant_id: str, connector: str) -> Connection | None:
    return db.scalar(
        select(Connection).where(
            Connection.tenant_id == tenant_id,
            Connection.connector == connector,
            Connection.status == "active",
        )
    )


def get_tenant_by_slug(db: Session, slug: str) -> Tenant | None:
    return db.scalar(select(Tenant).where(Tenant.slug == slug))


def get_tenant_by_id(db: Session, tenant_id: str) -> Tenant | None:
    return db.scalar(select(Tenant).where(Tenant.id == tenant_id))


def list_jobs(db: Session, tenant_id: str | None = None, limit: int = 100) -> list[SyncJob]:
    stmt = select(SyncJob).order_by(SyncJob.created_at.desc()).limit(limit)
    if tenant_id:
        stmt = stmt.where(SyncJob.tenant_id == tenant_id)
    return list(db.scalars(stmt).all())


def upsert_gmail_oauth_account(
    db: Session,
    *,
    tenant_id: str,
    account_id: str,
    email: str,
    credential_ref: str,
) -> GmailOAuthAccount:
    existing = db.scalar(
        select(GmailOAuthAccount).where(
            GmailOAuthAccount.tenant_id == tenant_id,
            GmailOAuthAccount.account_id == account_id,
        )
    )
    if existing:
        existing.email = email
        existing.credential_ref = credential_ref
        existing.status = "active"
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    row = GmailOAuthAccount(
        tenant_id=tenant_id,
        account_id=account_id,
        email=email,
        credential_ref=credential_ref,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_gmail_oauth_accounts(db: Session, *, tenant_id: str) -> list[GmailOAuthAccount]:
    return list(
        db.scalars(
            select(GmailOAuthAccount)
            .where(
                GmailOAuthAccount.tenant_id == tenant_id,
                GmailOAuthAccount.status == "active",
            )
            .order_by(GmailOAuthAccount.created_at.desc())
        ).all()
    )


def get_gmail_oauth_account(
    db: Session,
    *,
    tenant_id: str,
    account_id: str,
) -> GmailOAuthAccount | None:
    return db.scalar(
        select(GmailOAuthAccount).where(
            GmailOAuthAccount.tenant_id == tenant_id,
            GmailOAuthAccount.account_id == account_id,
            GmailOAuthAccount.status == "active",
        )
    )


def deactivate_gmail_oauth_account(
    db: Session,
    *,
    tenant_id: str,
    account_id: str,
) -> GmailOAuthAccount | None:
    row = get_gmail_oauth_account(db, tenant_id=tenant_id, account_id=account_id)
    if not row:
        return None
    row.status = "inactive"
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_emails(
    db: Session,
    *,
    tenant_id: str,
    to_address: str = "",
    limit: int = 100,
) -> list[CanonicalEmail]:
    stmt = (
        select(CanonicalEmail)
        .where(CanonicalEmail.tenant_id == tenant_id)
        .order_by(CanonicalEmail.received_at.desc(), CanonicalEmail.created_at.desc())
        .limit(limit)
    )
    if to_address:
        stmt = stmt.where(CanonicalEmail.to_address.ilike(f"%{to_address}%"))
    return list(db.scalars(stmt).all())


def create_oauth_state(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    payload: dict,
    expires_in_seconds: int = 600,
) -> OAuthState:
    row = OAuthState(
        tenant_id=tenant_id,
        connector=connector,
        state=str(uuid4()),
        payload_json=payload,
        expires_at=datetime.utcnow() + timedelta(seconds=expires_in_seconds),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_oauth_state(db: Session, *, connector: str, state: str) -> OAuthState | None:
    row = db.scalar(
        select(OAuthState).where(
            OAuthState.connector == connector,
            OAuthState.state == state,
            OAuthState.consumed_at.is_(None),
        )
    )
    if not row:
        return None
    if row.expires_at < datetime.utcnow():
        return None
    return row


def consume_oauth_state(db: Session, row: OAuthState) -> OAuthState:
    row.consumed_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def queue_job_from_event(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    event_type: str,
    delivery_id: str,
    payload: dict,
    trigger: str,
) -> SyncJob | None:
    webhook_event = WebhookEvent(
        tenant_id=tenant_id,
        connector=connector,
        delivery_id=delivery_id,
        event_type=event_type,
        payload_json=payload,
    )

    entity_type = event_type.split("/")[0] if "/" in event_type else event_type
    entity_id = str(payload.get("id", ""))
    idempotency_key = f"{connector}:{delivery_id}:{event_type}"

    job = SyncJob(
        tenant_id=tenant_id,
        connector=connector,
        entity_type=entity_type,
        entity_id=entity_id,
        trigger=trigger,
        job_type=f"IMPORT_{entity_type.upper()}",
        idempotency_key=idempotency_key,
        payload_json=payload,
    )

    outbox = OutboxEvent(
        tenant_id=tenant_id,
        topic="sync.job.queued",
        payload_json={
            "idempotency_key": idempotency_key,
            "connector": connector,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )

    try:
        db.add(webhook_event)
        db.add(job)
        db.add(outbox)
        db.commit()
        db.refresh(job)
        return job
    except IntegrityError:
        db.rollback()
        return None


def create_manual_job(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    job_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> SyncJob:
    idempotency_key = f"manual:{connector}:{job_type}:{entity_id}:{uuid4()}"
    job = SyncJob(
        tenant_id=tenant_id,
        connector=connector,
        entity_type=entity_type or "generic",
        entity_id=entity_id,
        trigger="manual",
        job_type=job_type,
        idempotency_key=idempotency_key,
        payload_json=payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job: SyncJob, code: str, payload: dict) -> SyncJob:
    job.attempts += 1
    if job.attempts >= 5:
        job.status = "deadletter"
    else:
        job.status = "failed"
        delay = 2**job.attempts
        job.next_run_at = datetime.utcnow() + timedelta(seconds=delay)
    job.error_code = code
    job.error_payload = payload
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_running(db: Session, job: SyncJob) -> SyncJob:
    job.status = "running"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_succeeded(db: Session, job: SyncJob) -> SyncJob:
    job.status = "succeeded"
    job.error_code = ""
    job.error_payload = {}
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_deadletter(db: Session, job_id: str) -> SyncJob | None:
    job = db.scalar(select(SyncJob).where(SyncJob.id == job_id))
    if not job:
        return None
    job.status = "deadletter"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, job_id: str) -> SyncJob | None:
    job = db.scalar(select(SyncJob).where(SyncJob.id == job_id))
    if not job:
        return None
    job.status = "queued"
    job.next_run_at = datetime.utcnow()
    job.error_code = ""
    job.error_payload = {}
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_next_due_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(
            SyncJob.status.in_(["queued", "failed"]),
            SyncJob.next_run_at <= datetime.utcnow(),
        )
        .order_by(SyncJob.next_run_at.asc(), SyncJob.created_at.asc())
        .limit(1)
    )


def upsert_order_from_external(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    order_payload: dict,
) -> CanonicalOrder:
    external_id = str(order_payload.get("id", ""))
    order_number = str(order_payload.get("name") or order_payload.get("order_number") or external_id)

    mapping = db.scalar(
        select(ExternalEntityMap).where(
            ExternalEntityMap.tenant_id == tenant_id,
            ExternalEntityMap.connector == connector,
            ExternalEntityMap.entity_type == "orders",
            ExternalEntityMap.external_id == external_id,
        )
    )

    if mapping:
        order = db.scalar(select(CanonicalOrder).where(CanonicalOrder.id == mapping.internal_id))
        if order:
            order.payload_json = order_payload
            order.status = str(order_payload.get("financial_status", order.status))
            order.total = float(order_payload.get("total_price") or order_payload.get("amount_total") or order.total)
            db.add(order)
            db.commit()
            db.refresh(order)
            return order

    order = CanonicalOrder(
        tenant_id=tenant_id,
        order_number=order_number,
        status=str(order_payload.get("financial_status", order_payload.get("state", "new"))),
        total=float(order_payload.get("total_price") or order_payload.get("amount_total") or 0),
        payload_json=order_payload,
    )
    db.add(order)
    db.flush()

    map_row = ExternalEntityMap(
        tenant_id=tenant_id,
        connector=connector,
        entity_type="orders",
        external_id=external_id,
        internal_id=order.id,
        snapshot_json=order_payload,
    )
    db.add(map_row)
    db.commit()
    db.refresh(order)
    return order


def _coerce_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return datetime.utcnow()


def upsert_email_from_external(
    db: Session,
    *,
    tenant_id: str,
    connector: str,
    email_payload: dict,
    source: str,
) -> CanonicalEmail:
    external_id = str(
        email_payload.get("id")
        or email_payload.get("message_id")
        or email_payload.get("delivery_id")
        or ""
    )
    if not external_id:
        external_id = str(uuid4())

    subject = str(email_payload.get("subject") or "")
    from_address = str(email_payload.get("email_from") or email_payload.get("from") or "")

    to_address_raw = (
        email_payload.get("to")
        or email_payload.get("email_to")
        or email_payload.get("target_address")
        or email_payload.get("reply_to")
        or ""
    )
    if isinstance(to_address_raw, list):
        to_address = ",".join(str(item) for item in to_address_raw if item)
    else:
        to_address = str(to_address_raw)

    mapping = db.scalar(
        select(ExternalEntityMap).where(
            ExternalEntityMap.tenant_id == tenant_id,
            ExternalEntityMap.connector == connector,
            ExternalEntityMap.entity_type == "emails",
            ExternalEntityMap.external_id == external_id,
        )
    )

    if mapping:
        email = db.scalar(select(CanonicalEmail).where(CanonicalEmail.id == mapping.internal_id))
        if email:
            email.subject = subject
            email.from_address = from_address
            email.to_address = to_address
            email.source = source
            email.status = str(email_payload.get("status") or "received")
            email.received_at = _coerce_datetime(
                str(email_payload.get("date") or email_payload.get("received_at") or "")
            )
            email.payload_json = email_payload
            db.add(email)
            db.commit()
            db.refresh(email)
            return email

    email = CanonicalEmail(
        tenant_id=tenant_id,
        subject=subject,
        from_address=from_address,
        to_address=to_address,
        source=source,
        status=str(email_payload.get("status") or "received"),
        received_at=_coerce_datetime(
            str(email_payload.get("date") or email_payload.get("received_at") or "")
        ),
        payload_json=email_payload,
    )
    db.add(email)
    db.flush()

    map_row = ExternalEntityMap(
        tenant_id=tenant_id,
        connector=connector,
        entity_type="emails",
        external_id=external_id,
        internal_id=email.id,
        snapshot_json=email_payload,
    )
    db.add(map_row)
    db.commit()
    db.refresh(email)
    return email
