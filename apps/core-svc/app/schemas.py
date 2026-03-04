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
