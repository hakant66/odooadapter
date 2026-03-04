import logging
import time

from sqlalchemy.orm import Session

from app.adapters import AdapterError, AdapterFactory
from app.config import get_settings
from app.db import SessionLocal
from app.models import Tenant
from app.queue import consume_job
from app.security import CredentialCipher
from app.services import (
    get_connection,
    get_decrypted_credentials,
    get_next_due_job,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
    queue_job_from_event,
    upsert_email_from_external,
    upsert_order_from_external,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("event-consumer")
settings = get_settings()
cipher = CredentialCipher(settings.credential_encryption_key)


def resolve_tenant_id(db: Session, tenant_slug: str) -> str | None:
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if not tenant:
        return None
    return tenant.id


def _ingest_redis_events() -> None:
    # Drain a small batch each iteration so webhook load and job execution coexist.
    for _ in range(20):
        item = consume_job("sync:events", timeout_seconds=1)
        if not item:
            break

        db = SessionLocal()
        try:
            tenant_id = resolve_tenant_id(db, item.get("tenant_slug", ""))
            if not tenant_id:
                logger.warning("unknown tenant slug=%s", item.get("tenant_slug"))
                continue

            job = queue_job_from_event(
                db,
                tenant_id=tenant_id,
                connector=item.get("connector", "unknown"),
                event_type=item.get("event_type", "unknown"),
                delivery_id=item.get("delivery_id", ""),
                payload=item.get("payload", {}),
                trigger="webhook",
            )
            if job:
                logger.info("queued sync job id=%s connector=%s type=%s", job.id, job.connector, job.job_type)
            else:
                logger.info("skipped duplicate webhook delivery id=%s", item.get("delivery_id"))
        finally:
            db.close()


def _execute_sync_job(db: Session, job) -> None:
    if job.job_type == "IMPORT_ORDERS" and job.payload_json.get("id"):
        upsert_order_from_external(
            db,
            tenant_id=job.tenant_id,
            connector=job.connector,
            order_payload=job.payload_json,
        )
        return

    if job.job_type == "IMPORT_EMAILS" and job.trigger == "webhook":
        upsert_email_from_external(
            db,
            tenant_id=job.tenant_id,
            connector=job.connector,
            email_payload=job.payload_json,
            source="webhook",
        )
        return

    connection = get_connection(db, tenant_id=job.tenant_id, connector=job.connector)
    if not connection:
        raise AdapterError(f"no active connection for connector={job.connector}")

    merged_metadata = dict(connection.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=connection.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )
    adapter = AdapterFactory.from_connection(job.connector, merged_metadata)

    if job.job_type == "IMPORT_ORDERS":
        since_cursor = str(job.payload_json.get("since_cursor", ""))
        batch = adapter.pull_orders(since_cursor=since_cursor)
        for order in batch.get("items", []):
            upsert_order_from_external(
                db,
                tenant_id=job.tenant_id,
                connector=job.connector,
                order_payload=order,
            )
        return

    if job.job_type == "IMPORT_PRODUCTS":
        adapter.pull_products(since_cursor=str(job.payload_json.get("since_cursor", "")))
        return

    if job.job_type == "IMPORT_REFUNDS":
        adapter.pull_refunds(since_cursor=str(job.payload_json.get("since_cursor", "")))
        return

    if job.job_type == "IMPORT_EMAILS":
        batch = adapter.pull_inbound_emails(
            since_cursor=str(job.payload_json.get("since_cursor", "")),
            target_address=str(job.payload_json.get("target_address", "")),
            source=str(job.payload_json.get("source", "odoo_alias_fetchmail")),
            limit=int(job.payload_json.get("limit", 200)),
        )
        for email in batch.get("items", []):
            upsert_email_from_external(
                db,
                tenant_id=job.tenant_id,
                connector=job.connector,
                email_payload=email,
                source=str(job.payload_json.get("source", "odoo_alias_fetchmail")),
            )
        return

    if job.job_type == "EXPORT_PRODUCT":
        adapter.push_product(job.payload_json)
        return

    if job.job_type == "EXPORT_FULFILLMENT":
        adapter.ack_fulfillment(job.entity_id, job.payload_json)
        return

    raise AdapterError(f"unsupported job_type={job.job_type}")


def _process_next_db_job() -> bool:
    db = SessionLocal()
    try:
        job = get_next_due_job(db)
        if not job:
            return False

        mark_job_running(db, job)
        try:
            _execute_sync_job(db, job)
            mark_job_succeeded(db, job)
            logger.info("job succeeded id=%s type=%s", job.id, job.job_type)
        except Exception as exc:
            mark_job_failed(db, job, code=type(exc).__name__, payload={"message": str(exc)})
            logger.exception("job failed id=%s error=%s", job.id, exc)
        return True
    finally:
        db.close()


def run_forever() -> None:
    logger.info("event consumer started")
    while True:
        _ingest_redis_events()
        ran_job = _process_next_db_job()
        if not ran_job:
            time.sleep(0.5)


if __name__ == "__main__":
    run_forever()
