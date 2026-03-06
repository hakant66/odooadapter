from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    service: str
    ok: bool


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=120)


class TenantRead(BaseModel):
    id: str
    name: str
    slug: str


class ConnectionCreate(BaseModel):
    tenant_id: str
    connector: str
    external_account_id: str
    credential_ref: str = ""
    credential_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ConnectionRead(BaseModel):
    id: str
    tenant_id: str
    connector: str
    external_account_id: str
    status: str
    validated: bool = False
    message: str = ""


class ConnectionTestRequest(BaseModel):
    tenant_id: str
    connector: str


class ConnectionTestResponse(BaseModel):
    ok: bool
    connector: str
    message: str


class EventEnvelope(BaseModel):
    tenant_slug: str
    connector: str
    event_type: str
    delivery_id: str
    payload: dict = Field(default_factory=dict)
    received_at: datetime | None = None


class JobRead(BaseModel):
    id: str
    tenant_id: str
    connector: str
    entity_type: str
    entity_id: str
    trigger: str
    job_type: str
    idempotency_key: str
    status: str
    attempts: int
    next_run_at: datetime
    error_code: str


class EmailRead(BaseModel):
    id: str
    tenant_id: str
    subject: str
    from_address: str
    to_address: str
    source: str
    status: str
    received_at: datetime


class RetryResponse(BaseModel):
    id: str
    status: str


class DeadletterResponse(BaseModel):
    id: str
    status: str


class SyncTriggerRequest(BaseModel):
    tenant_id: str
    connector: str
    entity_type: str
    since_cursor: str = ""


class EmailSyncTriggerRequest(BaseModel):
    tenant_id: str
    connector: str = "odoo"
    since_cursor: str = ""
    target_address: str = ""
    source: str = "odoo_alias_fetchmail"
    limit: int = 200


class GmailSyncTriggerRequest(BaseModel):
    tenant_id: str
    account_id: str = "default"
    mailbox: str = "INBOX"
    window_days: int = 7
    max_messages: int = 20
    target_to_address: str = ""
    include_headers: bool = False
    include_snippet: bool = True
    include_attachments: bool = True
    extract_attachment_text: bool = True


class GmailSyncResponse(BaseModel):
    imported_count: int
    fetched_count: int
    attachments_processed: int
    account_id: str


class GmailOAuthAccountCreate(BaseModel):
    tenant_id: str
    account_id: str
    email: str = ""
    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str = ""
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"


class GmailOAuthAccountRead(BaseModel):
    id: str
    tenant_id: str
    account_id: str
    email: str
    status: str
    created_at: datetime
    updated_at: datetime


class ManualJobCreate(BaseModel):
    tenant_id: str
    connector: str
    job_type: str
    entity_type: str = ""
    entity_id: str = ""
    payload: dict = Field(default_factory=dict)


class OAuthStartResponse(BaseModel):
    authorize_url: str
    state: str


class OAuthCallbackResponse(BaseModel):
    connection_id: str
    tenant_id: str
    connector: str
    external_account_id: str
