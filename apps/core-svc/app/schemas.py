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
    metadata: dict = Field(default_factory=dict)
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
    has_attachments: bool = False
    source: str
    status: str
    received_at: datetime
    imported: bool = False
    imported_at: str = ""
    bill_reference: str = ""


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


class OdooVendorBillFromPdfRequest(BaseModel):
    tenant_id: str
    pdf_base64: str
    filename: str = "invoice.pdf"
    vendor_name: str = "PDF Import Vendor"


class OdooVendorBillFromPdfResponse(BaseModel):
    status: str
    bill_id: int
    attachment_id: int
    vendor_name: str
    debug: dict = Field(default_factory=dict)


class OdooVendorRead(BaseModel):
    id: int
    name: str
    vat: str = ""
    email: str = ""
    ref: str = ""
    supplier_rank: int = 0


class BillFieldExtraction(BaseModel):
    vendor: str = ""
    bill_reference: str = ""
    bill_date: str = ""
    invoice_date: str = ""
    product: str = ""
    accounting_date: str = ""
    account_id: str = ""
    vat_percent: str = ""
    billing_id: str = ""
    currency: str = ""
    discount: str = ""
    payment_reference: str = ""
    recipient_bank: str = ""
    price: float | None = None
    tax: str = ""
    amount: float | None = None
    due_date: str = ""


class EmailToOdooBillRequest(BaseModel):
    tenant_id: str
    email_ids: list[str] = Field(default_factory=list)
    actor: str = "ui-user"


class EmailToOdooBillItemResult(BaseModel):
    email_id: str
    status: str
    extracted: BillFieldExtraction = Field(default_factory=BillFieldExtraction)
    bill_id: int | None = None
    detail: str = ""
    debug: dict = Field(default_factory=dict)


class EmailToOdooBillResponse(BaseModel):
    processed: int
    created: int
    items: list[EmailToOdooBillItemResult] = Field(default_factory=list)


class EmailAttachmentPreview(BaseModel):
    filename: str = ""
    mime_type: str = ""
    content_base64: str = ""


class EmailToOdooBillPreviewItem(BaseModel):
    email_id: str
    status: str
    subject: str = ""
    from_address: str = ""
    extracted: BillFieldExtraction = Field(default_factory=BillFieldExtraction)
    attachment_preview: EmailAttachmentPreview = Field(default_factory=EmailAttachmentPreview)
    detail: str = ""
    debug: dict = Field(default_factory=dict)


class EmailToOdooBillPreviewResponse(BaseModel):
    processed: int
    ready: int
    items: list[EmailToOdooBillPreviewItem] = Field(default_factory=list)


class EmailToOdooBillImportItem(BaseModel):
    email_id: str
    extracted: BillFieldExtraction = Field(default_factory=BillFieldExtraction)


class EmailToOdooBillImportFromPreviewRequest(BaseModel):
    tenant_id: str
    actor: str = "ui-user"
    items: list[EmailToOdooBillImportItem] = Field(default_factory=list)


class AuditLogCreate(BaseModel):
    tenant_id: str
    action: str
    actor: str = "ui-user"
    entity_type: str = ""
    entity_id: str = ""
    details: dict = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    id: str
    tenant_id: str
    action: str
    actor: str
    entity_type: str
    entity_id: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


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


class GmailOAuthAccountTestRequest(BaseModel):
    tenant_id: str
    account_id: str


class GmailOAuthAccountTestResponse(BaseModel):
    ok: bool
    account_id: str
    email: str = ""
    provider: str = "gmail"
    message: str


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
