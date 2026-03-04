from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import CanonicalEmail, ExternalEntityMap, SyncJob, Tenant
from app.services import upsert_email_from_external
from app.workers.event_consumer import _execute_sync_job


@pytest.fixture(scope="module", autouse=True)
def ensure_schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def clean_db():
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


def _create_tenant(client: TestClient, slug: str) -> str:
    response = client.post(
        "/tenants",
        json={"name": f"Tenant {slug}", "slug": slug},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_sync_emails_import_creates_import_emails_job():
    client = TestClient(app)
    tenant_id = _create_tenant(client, "email-job-tenant")

    response = client.post(
        "/sync/emails/import",
        json={
            "tenant_id": tenant_id,
            "connector": "odoo",
            "since_cursor": "2026-03-01T00:00:00Z",
            "target_address": "support@example.com",
            "source": "odoo_alias_fetchmail",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connector"] == "odoo"
    assert body["entity_type"] == "emails"
    assert body["job_type"] == "IMPORT_EMAILS"
    assert body["trigger"] == "poll"

    db = SessionLocal()
    try:
        job = db.get(SyncJob, body["id"])
        assert job is not None
        assert job.payload_json["target_address"] == "support@example.com"
        assert job.payload_json["since_cursor"] == "2026-03-01T00:00:00Z"
        assert job.payload_json["source"] == "odoo_alias_fetchmail"
        assert job.payload_json["limit"] == 50
    finally:
        db.close()


def test_get_emails_returns_persisted_email_records():
    client = TestClient(app)
    tenant_id = _create_tenant(client, "email-list-tenant")

    db = SessionLocal()
    try:
        upsert_email_from_external(
            db,
            tenant_id=tenant_id,
            connector="odoo",
            email_payload={
                "id": "odoo-msg-1",
                "subject": "Support request",
                "email_from": "customer@example.com",
                "target_address": "support@example.com",
                "date": "2026-03-04T12:00:00Z",
                "body": "Need help with my order.",
            },
            source="odoo_alias_fetchmail",
        )
    finally:
        db.close()

    response = client.get(
        "/emails",
        params={"tenant_id": tenant_id, "to_address": "support@example.com", "limit": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["subject"] == "Support request"
    assert body[0]["from_address"] == "customer@example.com"
    assert body[0]["to_address"] == "support@example.com"
    assert body[0]["source"] == "odoo_alias_fetchmail"
    assert body[0]["status"] == "received"


def test_worker_upserts_email_from_webhook_payload():
    db = SessionLocal()
    try:
        tenant = Tenant(name="Worker Tenant", slug="worker-email-tenant")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        job = SyncJob(
            tenant_id=tenant.id,
            connector="odoo",
            entity_type="emails",
            entity_id="provider-msg-1",
            trigger="webhook",
            job_type="IMPORT_EMAILS",
            idempotency_key="test-webhook-import-emails",
            payload_json={
                "id": "provider-msg-1",
                "subject": "Inbound from provider",
                "from": "sender@example.com",
                "to": "helpdesk@example.com",
                "received_at": "2026-03-04T13:00:00Z",
                "body": "Webhook-delivered email body",
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        _execute_sync_job(db, job)

        email = db.query(CanonicalEmail).filter(CanonicalEmail.tenant_id == tenant.id).one_or_none()
        assert email is not None
        assert email.subject == "Inbound from provider"
        assert email.from_address == "sender@example.com"
        assert email.to_address == "helpdesk@example.com"
        assert email.source == "webhook"
        assert email.status == "received"
        assert isinstance(email.received_at, datetime)

        mapping = (
            db.query(ExternalEntityMap)
            .filter(
                ExternalEntityMap.tenant_id == tenant.id,
                ExternalEntityMap.connector == "odoo",
                ExternalEntityMap.entity_type == "emails",
                ExternalEntityMap.external_id == "provider-msg-1",
            )
            .one_or_none()
        )
        assert mapping is not None
        assert mapping.internal_id == email.id
    finally:
        db.close()
