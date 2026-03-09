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


def test_list_tenants_and_connections_include_latest_state():
    client = TestClient(app)
    tenant_id = _create_tenant(client, "persisted-ui-state-tenant")

    connection_resp = client.post(
        "/connections",
        json={
            "tenant_id": tenant_id,
            "connector": "mock",
            "external_account_id": "mock-account",
            "credential_payload": {"api_key": "secret"},
            "metadata": {"base_url": "https://example.test", "database": "prod_db", "username": "ops@example.com"},
        },
    )
    assert connection_resp.status_code == 200
    created = connection_resp.json()
    assert created["status"] == "active"
    assert created["metadata"]["username"] == "ops@example.com"

    tenants_resp = client.get("/tenants", params={"limit": 1})
    assert tenants_resp.status_code == 200
    tenants = tenants_resp.json()
    assert len(tenants) == 1
    assert tenants[0]["id"] == tenant_id

    connections_resp = client.get(
        "/connections",
        params={"tenant_id": tenant_id, "connector": "mock", "limit": 1},
    )
    assert connections_resp.status_code == 200
    rows = connections_resp.json()
    assert len(rows) == 1
    assert rows[0]["connector"] == "mock"
    assert rows[0]["external_account_id"] == "mock-account"
    assert rows[0]["metadata"]["database"] == "prod_db"


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


def test_get_emails_supports_from_subject_and_attachment_filters():
    client = TestClient(app)
    tenant_id = _create_tenant(client, "email-filter-tenant")

    db = SessionLocal()
    try:
        upsert_email_from_external(
            db,
            tenant_id=tenant_id,
            connector="gmail",
            email_payload={
                "id": "gmail-msg-1",
                "subject": "Invoice for March",
                "email_from": "billing@example.com",
                "to": ["taskin.baba@gmail.com"],
                "date": "2026-03-06T12:00:00Z",
                "attachments": [{"filename": "invoice.pdf"}],
            },
            source="gmail_mcp",
        )
        upsert_email_from_external(
            db,
            tenant_id=tenant_id,
            connector="gmail",
            email_payload={
                "id": "gmail-msg-2",
                "subject": "Meeting notes",
                "email_from": "hr@example.com",
                "to": ["taskin.baba@gmail.com"],
                "date": "2026-03-06T12:30:00Z",
                "attachments": [],
            },
            source="gmail_mcp",
        )
    finally:
        db.close()

    from_resp = client.get(
        "/emails",
        params={"tenant_id": tenant_id, "from_address": "billing@", "limit": 10},
    )
    assert from_resp.status_code == 200
    from_rows = from_resp.json()
    assert len(from_rows) == 1
    assert from_rows[0]["from_address"] == "billing@example.com"

    subject_resp = client.get(
        "/emails",
        params={"tenant_id": tenant_id, "subject_contains": "Invoice", "limit": 10},
    )
    assert subject_resp.status_code == 200
    subject_rows = subject_resp.json()
    assert len(subject_rows) == 1
    assert subject_rows[0]["subject"] == "Invoice for March"

    with_attachments_resp = client.get(
        "/emails",
        params={"tenant_id": tenant_id, "has_attachments": "true", "limit": 10},
    )
    assert with_attachments_resp.status_code == 200
    with_attachments_rows = with_attachments_resp.json()
    assert len(with_attachments_rows) == 1
    assert with_attachments_rows[0]["subject"] == "Invoice for March"

    no_attachments_resp = client.get(
        "/emails",
        params={"tenant_id": tenant_id, "has_attachments": "false", "limit": 10},
    )
    assert no_attachments_resp.status_code == 200
    no_attachments_rows = no_attachments_resp.json()
    assert len(no_attachments_rows) == 1
    assert no_attachments_rows[0]["subject"] == "Meeting notes"


def test_get_emails_supports_or_filter_logic():
    client = TestClient(app)
    tenant_id = _create_tenant(client, "email-filter-or-tenant")

    db = SessionLocal()
    try:
        upsert_email_from_external(
            db,
            tenant_id=tenant_id,
            connector="gmail",
            email_payload={
                "id": "gmail-or-1",
                "subject": "Invoice #1",
                "email_from": "billing@example.com",
                "to": ["taskin.baba@gmail.com"],
                "date": "2026-03-06T12:00:00Z",
                "attachments": [],
            },
            source="gmail_mcp",
        )
        upsert_email_from_external(
            db,
            tenant_id=tenant_id,
            connector="gmail",
            email_payload={
                "id": "gmail-or-2",
                "subject": "Weekly update",
                "email_from": "ops@example.com",
                "to": ["taskin.baba@gmail.com"],
                "date": "2026-03-06T12:30:00Z",
                "attachments": [{"filename": "report.pdf"}],
            },
            source="gmail_mcp",
        )
    finally:
        db.close()

    and_resp = client.get(
        "/emails",
        params={
            "tenant_id": tenant_id,
            "from_address": "billing@",
            "has_attachments": "true",
            "filter_logic": "and",
            "limit": 10,
        },
    )
    assert and_resp.status_code == 200
    assert len(and_resp.json()) == 0

    or_resp = client.get(
        "/emails",
        params={
            "tenant_id": tenant_id,
            "from_address": "billing@",
            "has_attachments": "true",
            "filter_logic": "or",
            "limit": 10,
        },
    )
    assert or_resp.status_code == 200
    rows = or_resp.json()
    assert len(rows) == 2


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


def test_gmail_oauth_crud_and_sync_import(monkeypatch):
    import app.main as main_module

    client = TestClient(app)
    tenant_id = _create_tenant(client, "gmail-oauth-tenant")

    create_resp = client.post(
        "/gmail/accounts",
        json={
            "tenant_id": tenant_id,
            "account_id": "ops",
            "email": "ops@gmail.com",
            "client_id": "cid",
            "client_secret": "csecret",
            "refresh_token": "rtoken",
            "access_token": "atoken",
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["account_id"] == "ops"

    list_resp = client.get("/gmail/accounts", params={"tenant_id": tenant_id})
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["email"] == "ops@gmail.com"

    calls = []

    def fake_tool_call(tool_name, payload):
        calls.append((tool_name, payload))
        oauth = payload.get("oauth", {})
        assert oauth.get("client_id") == "cid"
        assert oauth.get("client_secret") == "csecret"
        assert oauth.get("refresh_token") == "rtoken"
        if tool_name == "email.fetch_messages":
            return {"messages": [{"message_id": "m-1"}], "count": 1}
        if tool_name == "email.get_message":
            return {
                "message_id": "m-1",
                "thread_id": "t-1",
                "date": "2026-03-04T10:00:00Z",
                "from": "sender@example.com",
                "to": ["ops@gmail.com"],
                "cc": [],
                "subject": "Gmail Import",
                "snippet": "snippet",
                "mailbox": "INBOX",
                "body": "hello",
            }
        if tool_name == "email.get_attachments":
            return {
                "attachments": [
                    {
                        "id": "att-1",
                        "filename": "sample.pdf",
                        "mime_type": "application/pdf",
                        "size": 100,
                        "inline": False,
                        "extracted_text": "pdf content",
                        "extraction_status": "ok",
                    }
                ]
            }
        raise AssertionError(f"unexpected tool {tool_name}")

    monkeypatch.setattr(main_module, "_email_mcp_tool_call", fake_tool_call)

    sync_resp = client.post(
        "/sync/gmail/import",
        json={
            "tenant_id": tenant_id,
            "account_id": "ops",
            "mailbox": "INBOX",
            "window_days": 7,
            "max_messages": 10,
            "target_to_address": "ops@gmail.com",
            "include_headers": False,
            "include_snippet": True,
            "include_attachments": True,
            "extract_attachment_text": True,
        },
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["imported_count"] == 1
    assert sync_resp.json()["attachments_processed"] == 1

    assert [c[0] for c in calls] == ["email.fetch_messages", "email.get_message", "email.get_attachments"]

    db = SessionLocal()
    try:
        row = db.query(CanonicalEmail).filter(CanonicalEmail.tenant_id == tenant_id).one_or_none()
        assert row is not None
        assert row.source == "gmail_mcp"
        assert row.subject == "Gmail Import"
    finally:
        db.close()
