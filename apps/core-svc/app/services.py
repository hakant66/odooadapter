import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
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


def list_tenants(db: Session, limit: int = 100) -> list[Tenant]:
    return list(
        db.scalars(
            select(Tenant)
            .order_by(Tenant.created_at.desc())
            .limit(limit)
        ).all()
    )


def list_connections(
    db: Session,
    *,
    tenant_id: str,
    connector: str | None = None,
    limit: int = 20,
) -> list[Connection]:
    stmt = (
        select(Connection)
        .where(
            Connection.tenant_id == tenant_id,
            Connection.status == "active",
        )
        .order_by(Connection.updated_at.desc())
        .limit(limit)
    )
    if connector:
        stmt = stmt.where(Connection.connector == connector)
    return list(db.scalars(stmt).all())


def list_jobs(db: Session, tenant_id: str | None = None, limit: int = 100) -> list[SyncJob]:
    stmt = select(SyncJob).order_by(SyncJob.created_at.desc()).limit(limit)
    if tenant_id:
        stmt = stmt.where(SyncJob.tenant_id == tenant_id)
    return list(db.scalars(stmt).all())


def create_audit_log(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    actor: str,
    entity_type: str = "",
    entity_id: str = "",
    details: dict | None = None,
) -> AuditLog:
    # Keep values within DB column limits to avoid 500s on large batch operations.
    action_value = (action or "")[:80]
    actor_value = (actor or "ui-user")[:120]
    entity_type_value = (entity_type or "")[:80]
    entity_id_value = (entity_id or "")[:120]
    row = AuditLog(
        tenant_id=tenant_id,
        action=action_value,
        actor=actor_value,
        entity_type=entity_type_value,
        entity_id=entity_id_value,
        details_json=details or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_audit_logs(db: Session, *, tenant_id: str, limit: int = 100) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).all()
    )


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
    from_address: str = "",
    subject_contains: str = "",
    has_attachments: bool | None = None,
    filter_logic: str = "and",
    limit: int = 100,
) -> list[CanonicalEmail]:
    normalized_logic = filter_logic.strip().lower()
    is_or = normalized_logic == "or"

    stmt = (
        select(CanonicalEmail)
        .where(CanonicalEmail.tenant_id == tenant_id)
        .order_by(CanonicalEmail.received_at.desc(), CanonicalEmail.created_at.desc())
    )

    # We evaluate mixed SQL/JSON conditions in Python to support AND/OR consistently.
    preload_limit = min(max(limit * 20, 500), 5000)
    candidates = list(db.scalars(stmt.limit(preload_limit)).all())

    def _contains(value: str, needle: str) -> bool:
        return needle.lower() in value.lower()

    filtered: list[CanonicalEmail] = []
    for row in candidates:
        checks: list[bool] = []
        if to_address:
            checks.append(_contains(row.to_address or "", to_address))
        if from_address:
            checks.append(_contains(row.from_address or "", from_address))
        if subject_contains:
            checks.append(_contains(row.subject or "", subject_contains))
        if has_attachments is not None:
            attachments = row.payload_json.get("attachments", []) if isinstance(row.payload_json, dict) else []
            attachment_count = len(attachments) if isinstance(attachments, list) else 0
            checks.append(attachment_count > 0 if has_attachments else attachment_count == 0)

        if not checks:
            matched = True
        else:
            matched = any(checks) if is_or else all(checks)

        if matched:
            filtered.append(row)
        if len(filtered) >= limit:
            break
    return filtered


def get_emails_by_ids(
    db: Session,
    *,
    tenant_id: str,
    email_ids: list[str],
) -> list[CanonicalEmail]:
    if not email_ids:
        return []
    rows = list(
        db.scalars(
            select(CanonicalEmail).where(
                CanonicalEmail.tenant_id == tenant_id,
                CanonicalEmail.id.in_(email_ids),
            )
        ).all()
    )
    index = {row.id: row for row in rows}
    return [index[email_id] for email_id in email_ids if email_id in index]


def set_email_status(
    db: Session,
    *,
    tenant_id: str,
    email_id: str,
    status: str,
) -> CanonicalEmail | None:
    row = db.scalar(
        select(CanonicalEmail).where(
            CanonicalEmail.tenant_id == tenant_id,
            CanonicalEmail.id == email_id,
        )
    )
    if not row:
        return None
    row.status = str(status or "").strip() or row.status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mark_email_imported(
    db: Session,
    *,
    tenant_id: str,
    email_id: str,
    bill_reference: str = "",
    bill_id: int | None = None,
    imported_at: datetime | None = None,
) -> CanonicalEmail | None:
    row = db.scalar(
        select(CanonicalEmail).where(
            CanonicalEmail.tenant_id == tenant_id,
            CanonicalEmail.id == email_id,
        )
    )
    if not row:
        return None
    payload = row.payload_json if isinstance(row.payload_json, dict) else {}
    import_info = payload.get("import_info", {}) if isinstance(payload.get("import_info"), dict) else {}
    timestamp = (imported_at or datetime.utcnow()).isoformat()
    import_info.update(
        {
            "status": "imported",
            "imported_at": timestamp,
            "bill_reference": str(bill_reference or import_info.get("bill_reference", "") or ""),
            "bill_id": int(bill_id) if bill_id else import_info.get("bill_id"),
        }
    )
    payload["import_info"] = import_info
    row.payload_json = payload
    row.status = "imported"
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
            existing_payload = email.payload_json if isinstance(email.payload_json, dict) else {}
            existing_import_info = (
                existing_payload.get("import_info", {})
                if isinstance(existing_payload.get("import_info", {}), dict)
                else {}
            )
            merged_payload = dict(email_payload or {})
            if existing_import_info and "import_info" not in merged_payload:
                merged_payload["import_info"] = existing_import_info

            email.subject = subject
            email.from_address = from_address
            email.to_address = to_address
            email.source = source
            if str(existing_import_info.get("status", "")).lower() == "imported":
                email.status = "imported"
            else:
                email.status = str(email_payload.get("status") or "received")
            email.received_at = _coerce_datetime(
                str(email_payload.get("date") or email_payload.get("received_at") or "")
            )
            email.payload_json = merged_payload
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
