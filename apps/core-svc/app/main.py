import hashlib
import hmac
import json
import re
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.adapters import AdapterError, AdapterFactory
from app.config import get_settings
from app.db import get_db
from app.schemas import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionTestRequest,
    ConnectionTestResponse,
    DeadletterResponse,
    EmailRead,
    EmailSyncTriggerRequest,
    EmailToOdooBillItemResult,
    EmailToOdooBillPreviewItem,
    EmailToOdooBillPreviewResponse,
    EmailToOdooBillRequest,
    EmailToOdooBillResponse,
    EventEnvelope,
    GmailOAuthAccountCreate,
    GmailOAuthAccountRead,
    GmailOAuthAccountTestRequest,
    GmailOAuthAccountTestResponse,
    GmailSyncResponse,
    GmailSyncTriggerRequest,
    HealthResponse,
    JobRead,
    BillFieldExtraction,
    EmailAttachmentPreview,
    AuditLogCreate,
    AuditLogRead,
    EmailToOdooBillImportFromPreviewRequest,
    ManualJobCreate,
    OdooVendorBillFromPdfRequest,
    OdooVendorBillFromPdfResponse,
    OdooVendorRead,
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
    create_audit_log,
    create_oauth_state,
    create_tenant,
    deactivate_gmail_oauth_account,
    get_oauth_state,
    get_connection,
    get_gmail_oauth_account,
    get_emails_by_ids,
    get_tenant_by_id,
    get_tenant_by_slug,
    get_decrypted_credentials,
    list_emails,
    list_connections,
    list_audit_logs,
    list_tenants,
    list_gmail_oauth_accounts,
    list_jobs,
    mark_email_imported,
    mark_job_deadletter,
    queue_job_from_event,
    retry_job,
    set_email_status,
    store_encrypted_credentials,
    upsert_gmail_oauth_account,
    upsert_email_from_external,
)
from app.security import CredentialCipher

settings = get_settings()
app = FastAPI(title="Odoo Adapter Core Service", version="0.1.0")
cipher = CredentialCipher(settings.credential_encryption_key)


def _email_mcp_tool_call(tool_name: str, payload: dict) -> dict:
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{settings.email_mcp_base_url}/tools/{tool_name}",
            json={"input": payload},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"email mcp tool call failed tool={tool_name} status={response.status_code} body={response.text}",
        )
    body = response.json()
    if body.get("ok") is False:
        raise HTTPException(status_code=502, detail=f"email mcp tool error tool={tool_name}: {body.get('error')}")
    result = body.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail=f"email mcp malformed response tool={tool_name}")
    return result


def _gmail_refresh_access_token(oauth_payload: dict) -> str:
    client_id = str(oauth_payload.get("client_id", "") or "").strip()
    client_secret = str(oauth_payload.get("client_secret", "") or "").strip()
    refresh_token = str(oauth_payload.get("refresh_token", "") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        raise HTTPException(status_code=400, detail="gmail oauth credentials missing client_id/client_secret/refresh_token")

    with httpx.Client(timeout=30) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"gmail token refresh failed status={response.status_code} body={response.text}",
        )
    token_body = response.json()
    access_token = str(token_body.get("access_token", "") or "").strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="gmail token refresh missing access_token")
    return access_token


def _gmail_api_get(*, access_token: str, path: str, params: dict | None = None) -> dict:
    with httpx.Client(timeout=60) as client:
        response = client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"gmail direct api failed path={path} status={response.status_code} body={response.text}",
        )
    body = response.json()
    return body if isinstance(body, dict) else {}


def _gmail_payload_headers(payload: dict) -> dict[str, str]:
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        return {}
    values: dict[str, str] = {}
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip().lower()
        value = str(item.get("value", "") or "").strip()
        if name and value and name not in values:
            values[name] = value
    return values


def _gmail_collect_attachments(
    *,
    access_token: str,
    message_id: str,
    payload: dict,
    include_content_base64: bool = False,
) -> list[dict]:
    attachments: list[dict] = []

    def walk(part: dict):
        if not isinstance(part, dict):
            return
        mime_type = str(part.get("mimeType", "") or "")
        filename = str(part.get("filename", "") or "")
        body = part.get("body", {}) if isinstance(part.get("body", {}), dict) else {}
        attachment_id = str(body.get("attachmentId", "") or "")
        data = str(body.get("data", "") or "")

        if filename and (attachment_id or data):
            content_base64 = ""
            if include_content_base64:
                raw_data = data
                if attachment_id:
                    att = _gmail_api_get(
                        access_token=access_token,
                        path=f"messages/{message_id}/attachments/{attachment_id}",
                    )
                    raw_data = str(att.get("data", "") or "")
                if raw_data:
                    padded = raw_data + ("=" * ((4 - len(raw_data) % 4) % 4))
                    try:
                        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
                        content_base64 = base64.b64encode(decoded).decode("ascii")
                    except Exception:
                        content_base64 = ""
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type,
                    "attachment_id": attachment_id,
                    "content_base64": content_base64,
                }
            )

        subparts = part.get("parts", [])
        if isinstance(subparts, list):
            for child in subparts:
                if isinstance(child, dict):
                    walk(child)

    walk(payload)
    return attachments


def _extract_json_object(raw_text: str) -> dict:
    if not raw_text:
        return {}
    stripped = raw_text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_bill_fields_with_openai(*, content: str) -> dict:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="missing OPENAI_API_KEY for bill extraction")
    if not content.strip():
        return {}

    instruction = (
        "Extract bill fields from the document text. Return strict JSON with these keys only: "
        "vendor, bill_reference, bill_date, invoice_date, product, accounting_date, account_id, vat_percent, "
        "billing_id, currency, discount, payment_reference, recipient_bank, price, tax, amount, due_date, "
        "overall_confidence, field_confidence. "
        "field_confidence must be an object with per-field confidence values 0..1. "
        "overall_confidence must be 0..1. "
        "Use empty string or null when unavailable."
    )
    model_name = settings.openai_bill_extractor_model.strip() or "gpt-4.1-mini"
    payload = {
        "model": model_name,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instruction}]},
            {"role": "user", "content": [{"type": "input_text", "text": content[:24000]}]},
        ],
        "max_output_tokens": 500,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60) as client:
        response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"openai extraction failed status={response.status_code} body={response.text}",
        )
    body = response.json()
    text_parts: list[str] = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for segment in item.get("content", []):
            if segment.get("type") == "output_text" and segment.get("text"):
                text_parts.append(segment["text"])
    if not text_parts and body.get("output_text"):
        text_parts.append(str(body.get("output_text")))
    parsed = _extract_json_object("\n".join(text_parts))
    if not isinstance(parsed, dict):
        return {}

    # Support either flat output or {"fields": {...}, "overall_confidence": ..., "field_confidence": {...}}.
    fields = parsed.get("fields", parsed)
    if not isinstance(fields, dict):
        fields = {}
    overall = parsed.get("overall_confidence", fields.get("overall_confidence", ""))
    per_field = parsed.get("field_confidence", fields.get("field_confidence", {}))
    fields["overall_confidence"] = overall
    fields["field_confidence"] = per_field if isinstance(per_field, dict) else {}
    return fields


def _extract_amount_fallback_from_text(content: str) -> float | None:
    text = str(content or "")
    if not text.strip():
        return None
    patterns = [
        r"(?im)^\s*total\b[^\d\-+]*([£$€]?\s*[-+]?\d[\d,]*(?:\.\d{1,2})?)",
        r"(?im)^\s*amount\s+due\b[^\d\-+]*([£$€]?\s*[-+]?\d[\d,]*(?:\.\d{1,2})?)",
        r"(?im)^\s*grand\s+total\b[^\d\-+]*([£$€]?\s*[-+]?\d[\d,]*(?:\.\d{1,2})?)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if not matches:
            continue
        for candidate in reversed(matches):
            normalized = re.sub(r"[^\d.\-+]", "", str(candidate))
            if not normalized:
                continue
            try:
                return float(normalized)
            except ValueError:
                continue
    return None


def _classify_invoice_document_with_openai(*, content: str) -> dict:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="missing OPENAI_API_KEY for invoice classification")
    if not content.strip():
        return {"is_invoice": False, "confidence": 0.0, "reason": "empty content"}

    instruction = (
        "Classify whether the provided document text is a supplier invoice/bill intended to be paid. "
        "Return strict JSON with keys: is_invoice (boolean), confidence (0..1), reason (string)."
    )
    model_name = settings.openai_bill_extractor_model.strip() or "gpt-4.1-mini"
    payload = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": "You are a strict invoice classifier. Return JSON only."}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": f"{instruction}\n\nDocument Text:\n{content[:12000]}"}],
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60) as client:
        response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"openai invoice classification failed status={response.status_code} body={response.text}",
        )
    body = response.json()
    text_parts: list[str] = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for segment in item.get("content", []):
            if segment.get("type") == "output_text" and segment.get("text"):
                text_parts.append(segment["text"])
    if not text_parts and body.get("output_text"):
        text_parts.append(str(body.get("output_text")))
    parsed = _extract_json_object("\n".join(text_parts))
    if not isinstance(parsed, dict):
        return {"is_invoice": False, "confidence": 0.0, "reason": "classifier returned malformed JSON"}
    return {
        "is_invoice": bool(parsed.get("is_invoice", False)),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "reason": str(parsed.get("reason", "") or ""),
    }


def _build_classification_text_for_email(*, email_payload: dict, attachments: list[dict]) -> str:
    subject = str(email_payload.get("subject", "") or "").strip()
    snippet = str(email_payload.get("snippet", "") or "").strip()
    body = str(email_payload.get("body", "") or "").strip()
    parts: list[str] = []
    if subject:
        parts.append(f"Subject: {subject}")
    if snippet:
        parts.append(f"Snippet: {snippet}")
    if body:
        parts.append(f"Body: {body}")
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        filename = str(attachment.get("filename", "") or "").strip()
        extracted_text = str(attachment.get("extracted_text", "") or "").strip()
        if extracted_text:
            heading = f"Attachment: {filename}" if filename else "Attachment"
            parts.append(f"{heading}\n{extracted_text}")
    return "\n\n".join(part for part in parts if part).strip()


def _auto_classify_email_status_after_fetch(*, email_payload: dict, attachments: list[dict]) -> dict:
    if not attachments:
        return {"status": str(email_payload.get("status", "") or "received"), "classification": {}}
    text = _build_classification_text_for_email(email_payload=email_payload, attachments=attachments)
    if not text:
        return {
            "status": str(email_payload.get("status", "") or "received"),
            "classification": {"skipped": True, "reason": "no text available for classification"},
        }
    result = _classify_invoice_document_with_openai(content=text)
    if not bool(result.get("is_invoice")):
        return {"status": "?", "classification": result}
    return {"status": str(email_payload.get("status", "") or "received"), "classification": result}


def _extract_bill_reference_candidates_from_text(*parts: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    patterns = [
        r"\b[A-Z0-9]{2,}(?:[-_/][A-Z0-9]{2,}){1,}\b",
        r"\b[A-Z]{1,6}\d{3,}\b",
    ]
    for part in parts:
        text = str(part or "").upper()
        if not text:
            continue
        for pattern in patterns:
            for match in re.findall(pattern, text):
                value = str(match).strip()
                if len(value) < 5:
                    continue
                if value in seen:
                    continue
                seen.add(value)
                candidates.append(value)
    return candidates


def _annotate_imported_if_exists(
    *,
    adapter,
    email_payload: dict,
) -> dict:
    if adapter is None:
        return {}
    subject = str(email_payload.get("subject", "") or "")
    snippet = str(email_payload.get("snippet", "") or "")
    body = str(email_payload.get("body", "") or "")
    candidates = _extract_bill_reference_candidates_from_text(subject, snippet, body)
    for ref in candidates:
        try:
            existing_bill_id = adapter.find_vendor_bill_by_reference(bill_reference=ref)
        except Exception:
            existing_bill_id = None
        if existing_bill_id:
            return {
                "status": "imported",
                "import_info": {
                    "status": "imported",
                    "imported_at": datetime.utcnow().isoformat(),
                    "bill_reference": ref,
                    "bill_id": int(existing_bill_id),
                    "source": "odoo_ref_match_on_fetch",
                },
            }
    return {}


def _pdf_text_parts_from_attachments(attachments: list[dict]) -> list[str]:
    parts: list[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        name = str(attachment.get("filename", "")).lower()
        mime = str(attachment.get("mime_type", "")).lower()
        extracted_text = str(attachment.get("extracted_text", "") or "").strip()
        if extracted_text and (name.endswith(".pdf") or mime == "application/pdf"):
            parts.append(extracted_text)
    return parts


def _refresh_pdf_parts_from_gmail_mcp(
    *,
    db: Session,
    tenant_id: str,
    email_payload: dict,
    include_content_base64: bool = False,
) -> tuple[list[str], dict, list[dict]]:
    account_id = str(email_payload.get("account_id", "")).strip()
    message_id = str(email_payload.get("message_id", email_payload.get("id", ""))).strip()
    if not account_id or not message_id:
        return [], {"refresh_attempted": False, "reason": "missing account_id/message_id"}, []

    account = get_gmail_oauth_account(db, tenant_id=tenant_id, account_id=account_id)
    if not account:
        return [], {"refresh_attempted": False, "reason": "gmail oauth account not found"}, []

    oauth_payload = get_decrypted_credentials(
        db,
        credential_ref=account.credential_ref,
        decrypt_fn=cipher.decrypt,
    )
    if not oauth_payload:
        return [], {"refresh_attempted": False, "reason": "gmail oauth credentials missing"}, []

    refreshed = _email_mcp_tool_call(
        "email.get_attachments",
        {
            "account_id": account_id,
            "oauth": oauth_payload,
            "message_id": message_id,
            "extract_text": True,
            "include_content_base64": include_content_base64,
        },
    )
    raw_attachments = refreshed.get("attachments", [])
    attachments = [item for item in raw_attachments if isinstance(item, dict)] if isinstance(raw_attachments, list) else []
    parts = _pdf_text_parts_from_attachments(attachments)
    return parts, {
        "refresh_attempted": True,
        "refreshed_attachment_count": len(attachments),
        "refreshed_pdf_text_parts": len(parts),
    }, attachments


def _first_pdf_attachment_preview(attachments: list[dict]) -> EmailAttachmentPreview:
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        filename = str(attachment.get("filename", "") or "")
        mime_type = str(attachment.get("mime_type", "") or "")
        lowered_name = filename.lower()
        lowered_mime = mime_type.lower()
        if lowered_name.endswith(".pdf") or lowered_mime == "application/pdf":
            return EmailAttachmentPreview(
                filename=filename,
                mime_type=mime_type or "application/pdf",
                content_base64=str(attachment.get("content_base64", "") or ""),
            )
    return EmailAttachmentPreview()


def _first_pdf_attachment_for_import(attachments: list[dict]) -> tuple[str, str]:
    preview = _first_pdf_attachment_preview(attachments)
    if preview.content_base64:
        return str(preview.content_base64), str(preview.filename or "invoice.pdf")
    return "", ""


def _validate_connector_auth(*, connector: str, metadata: dict) -> str:
    adapter = AdapterFactory.from_connection(connector, metadata)
    if connector == "odoo":
        # Force real auth check at save/test time.
        adapter._authenticate()  # type: ignore[attr-defined]
        return "odoo authentication successful"
    return "connection validation skipped for this connector"


@app.post("/gmail/accounts", response_model=GmailOAuthAccountRead)
def upsert_gmail_oauth_account_endpoint(
    body: GmailOAuthAccountCreate, db: Session = Depends(get_db)
) -> GmailOAuthAccountRead:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    encrypted = cipher.encrypt(
        json.dumps(
            {
                "client_id": body.client_id,
                "client_secret": body.client_secret,
                "refresh_token": body.refresh_token,
                "access_token": body.access_token,
                "redirect_uri": body.redirect_uri,
            }
        )
    )
    vault = store_encrypted_credentials(
        db,
        tenant_id=body.tenant_id,
        connector="gmail",
        encrypted_payload=encrypted,
        secret_type="oauth_token",
    )
    row = upsert_gmail_oauth_account(
        db,
        tenant_id=body.tenant_id,
        account_id=body.account_id,
        email=body.email,
        credential_ref=vault.id,
    )
    return GmailOAuthAccountRead(
        id=row.id,
        tenant_id=row.tenant_id,
        account_id=row.account_id,
        email=row.email,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.post("/gmail/accounts/test", response_model=GmailOAuthAccountTestResponse)
def test_gmail_oauth_account_endpoint(
    body: GmailOAuthAccountTestRequest, db: Session = Depends(get_db)
) -> GmailOAuthAccountTestResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    account = get_gmail_oauth_account(db, tenant_id=body.tenant_id, account_id=body.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="gmail oauth account not found")

    oauth_payload = get_decrypted_credentials(
        db,
        credential_ref=account.credential_ref,
        decrypt_fn=cipher.decrypt,
    )
    if not oauth_payload:
        raise HTTPException(status_code=400, detail="gmail oauth credentials missing")

    result = _email_mcp_tool_call(
        "email.test_connection",
        {
            "account_id": body.account_id,
            "oauth": oauth_payload,
        },
    )
    verified_email = str(result.get("email", "") or account.email or body.account_id)
    provider = str(result.get("provider", "") or "gmail")
    return GmailOAuthAccountTestResponse(
        ok=True,
        account_id=body.account_id,
        email=verified_email,
        provider=provider,
        message=f"Gmail access is active for account: {body.account_id}",
    )


@app.get("/gmail/accounts", response_model=list[GmailOAuthAccountRead])
def list_gmail_oauth_accounts_endpoint(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> list[GmailOAuthAccountRead]:
    rows = list_gmail_oauth_accounts(db, tenant_id=tenant_id)
    return [
        GmailOAuthAccountRead(
            id=row.id,
            tenant_id=row.tenant_id,
            account_id=row.account_id,
            email=row.email,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@app.delete("/gmail/accounts/{account_id}", response_model=GmailOAuthAccountRead)
def deactivate_gmail_oauth_account_endpoint(
    account_id: str,
    tenant_id: str,
    db: Session = Depends(get_db),
) -> GmailOAuthAccountRead:
    row = deactivate_gmail_oauth_account(db, tenant_id=tenant_id, account_id=account_id)
    if not row:
        raise HTTPException(status_code=404, detail="gmail oauth account not found")
    return GmailOAuthAccountRead(
        id=row.id,
        tenant_id=row.tenant_id,
        account_id=row.account_id,
        email=row.email,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=settings.app_name, ok=True)


@app.get("/system/llm")
def system_llm_info() -> dict:
    model_name = settings.openai_bill_extractor_model.strip() or "gpt-4.1-mini"
    configured = bool(settings.openai_api_key)
    return {
        "provider": "openai",
        "model": model_name,
        "configured": configured,
        "status": "active" if configured else "missing_api_key",
    }


@app.post("/audit/logs", response_model=AuditLogRead)
def create_audit_log_endpoint(body: AuditLogCreate, db: Session = Depends(get_db)) -> AuditLogRead:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    row = create_audit_log(
        db,
        tenant_id=body.tenant_id,
        action=body.action,
        actor=body.actor,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        details=body.details,
    )
    return AuditLogRead(
        id=row.id,
        tenant_id=row.tenant_id,
        action=row.action,
        actor=row.actor,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        details=row.details_json or {},
        created_at=row.created_at,
    )


@app.get("/audit/logs", response_model=list[AuditLogRead])
def list_audit_logs_endpoint(tenant_id: str, limit: int = 100, db: Session = Depends(get_db)) -> list[AuditLogRead]:
    rows = list_audit_logs(db, tenant_id=tenant_id, limit=limit)
    return [
        AuditLogRead(
            id=row.id,
            tenant_id=row.tenant_id,
            action=row.action,
            actor=row.actor,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            details=row.details_json or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.post("/tenants", response_model=TenantRead)
def create_tenant_endpoint(body: TenantCreate, db: Session = Depends(get_db)) -> TenantRead:
    tenant = create_tenant(db, body.name, body.slug)
    return TenantRead(id=tenant.id, name=tenant.name, slug=tenant.slug)


@app.get("/tenants", response_model=list[TenantRead])
def list_tenants_endpoint(limit: int = 100, db: Session = Depends(get_db)) -> list[TenantRead]:
    rows = list_tenants(db, limit=limit)
    return [TenantRead(id=row.id, name=row.name, slug=row.slug) for row in rows]


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
    merged_metadata = dict(body.metadata or {})
    validated = False
    message = ""
    if body.credential_payload:
        merged_metadata.update(body.credential_payload)
        try:
            message = _validate_connector_auth(connector=body.connector, metadata=merged_metadata)
            validated = True
        except AdapterError as exc:
            raise HTTPException(status_code=400, detail=f"connection test failed: {exc}") from exc
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
        metadata=conn.metadata_json or {},
        validated=validated,
        message=message,
    )


@app.get("/connections", response_model=list[ConnectionRead])
def list_connections_endpoint(
    tenant_id: str,
    connector: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[ConnectionRead]:
    rows = list_connections(
        db,
        tenant_id=tenant_id,
        connector=connector,
        limit=limit,
    )
    return [
        ConnectionRead(
            id=row.id,
            tenant_id=row.tenant_id,
            connector=row.connector,
            external_account_id=row.external_account_id,
            status=row.status,
            metadata=row.metadata_json or {},
            validated=False,
            message="",
        )
        for row in rows
    ]


@app.post("/connections/test", response_model=ConnectionTestResponse)
def test_connection_endpoint(body: ConnectionTestRequest, db: Session = Depends(get_db)) -> ConnectionTestResponse:
    conn = get_connection(db, tenant_id=body.tenant_id, connector=body.connector)
    if not conn:
        raise HTTPException(status_code=404, detail="active connection not found")

    merged_metadata = dict(conn.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=conn.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )

    try:
        message = _validate_connector_auth(connector=body.connector, metadata=merged_metadata)
    except AdapterError as exc:
        return ConnectionTestResponse(ok=False, connector=body.connector, message=str(exc))

    return ConnectionTestResponse(ok=True, connector=body.connector, message=message)


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


@app.post("/sync/gmail/import", response_model=GmailSyncResponse)
def trigger_gmail_import(body: GmailSyncTriggerRequest, db: Session = Depends(get_db)) -> GmailSyncResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    account = get_gmail_oauth_account(db, tenant_id=body.tenant_id, account_id=body.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="gmail oauth account not found")

    oauth_payload = get_decrypted_credentials(
        db,
        credential_ref=account.credential_ref,
        decrypt_fn=cipher.decrypt,
    )
    if not oauth_payload:
        raise HTTPException(status_code=400, detail="gmail oauth credentials missing")
    odoo_adapter = None
    odoo_conn = get_connection(db, tenant_id=body.tenant_id, connector="odoo")
    if odoo_conn:
        merged_odoo_metadata = dict(odoo_conn.metadata_json or {})
        merged_odoo_metadata.update(
            get_decrypted_credentials(
                db,
                credential_ref=odoo_conn.credential_ref,
                decrypt_fn=cipher.decrypt,
            )
        )
        try:
            odoo_adapter = AdapterFactory.from_connection("odoo", merged_odoo_metadata)
        except Exception:
            odoo_adapter = None
    def _run_mcp_import() -> tuple[int, int, int]:
        fetched = _email_mcp_tool_call(
            "email.fetch_messages",
            {
                "account_id": body.account_id,
                "oauth": oauth_payload,
                "mailbox": body.mailbox,
                "window_days": body.window_days,
                "max_messages": body.max_messages,
                "target_to_address": body.target_to_address,
                "include_headers": body.include_headers,
                "include_snippet": body.include_snippet,
            },
        )
        messages = fetched.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        imported_count = 0
        attachments_processed = 0
        for msg in messages:
            message_id = str(msg.get("message_id", ""))
            if not message_id:
                continue
            detail = _email_mcp_tool_call(
                "email.get_message",
                {
                    "account_id": body.account_id,
                    "oauth": oauth_payload,
                    "message_id": message_id,
                    "mailbox": body.mailbox,
                    "include_headers": body.include_headers,
                },
            )

            attachments: list[dict] = []
            if body.include_attachments:
                attachment_result = _email_mcp_tool_call(
                    "email.get_attachments",
                    {
                        "account_id": body.account_id,
                        "oauth": oauth_payload,
                        "message_id": message_id,
                        "extract_text": body.extract_attachment_text,
                    },
                )
                raw_attachments = attachment_result.get("attachments", [])
                if isinstance(raw_attachments, list):
                    attachments = [item for item in raw_attachments if isinstance(item, dict)]
                    attachments_processed += len(attachments)

            email_payload = {
                "id": detail.get("message_id", message_id),
                "message_id": detail.get("message_id", message_id),
                "thread_id": detail.get("thread_id", ""),
                "subject": detail.get("subject", ""),
                "email_from": detail.get("from", ""),
                "to": detail.get("to", []),
                "cc": detail.get("cc", []),
                "snippet": detail.get("snippet", ""),
                "body": detail.get("body", ""),
                "date": detail.get("date", ""),
                "mailbox": detail.get("mailbox", body.mailbox),
                "provider": "gmail",
                "account_id": body.account_id,
                "attachments": attachments,
                "target_address": body.target_to_address,
            }
            auto_classification = _auto_classify_email_status_after_fetch(
                email_payload=email_payload,
                attachments=attachments,
            )
            email_payload["status"] = str(auto_classification.get("status", "received") or "received")
            email_payload["classification"] = auto_classification.get("classification", {})
            imported_meta = _annotate_imported_if_exists(adapter=odoo_adapter, email_payload=email_payload)
            if imported_meta:
                email_payload["status"] = str(imported_meta.get("status", email_payload["status"]) or email_payload["status"])
                email_payload["import_info"] = imported_meta.get("import_info", {})
            upsert_email_from_external(
                db,
                tenant_id=body.tenant_id,
                connector="gmail",
                email_payload=email_payload,
                source="gmail_mcp",
            )
            imported_count += 1
        return imported_count, len(messages), attachments_processed

    def _run_direct_gmail_import() -> tuple[int, int, int]:
        access_token = _gmail_refresh_access_token(oauth_payload)
        search_terms: list[str] = []
        if body.window_days > 0:
            search_terms.append(f"newer_than:{int(body.window_days)}d")
        if body.target_to_address:
            search_terms.append(f"to:{body.target_to_address}")
        listed = _gmail_api_get(
            access_token=access_token,
            path="messages",
            params={
                "maxResults": int(body.max_messages),
                "q": " ".join(search_terms).strip(),
                "labelIds": body.mailbox or "INBOX",
            },
        )
        messages = listed.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        imported_count = 0
        attachments_processed = 0
        for msg in messages:
            message_id = str((msg or {}).get("id", "") if isinstance(msg, dict) else "")
            if not message_id:
                continue
            detail = _gmail_api_get(
                access_token=access_token,
                path=f"messages/{message_id}",
                params={"format": "full"},
            )
            payload = detail.get("payload", {}) if isinstance(detail.get("payload", {}), dict) else {}
            headers = _gmail_payload_headers(payload)
            to_header = headers.get("to", "")
            cc_header = headers.get("cc", "")
            if body.target_to_address and body.target_to_address.lower() not in to_header.lower():
                continue

            attachments: list[dict] = []
            if body.include_attachments:
                attachments = _gmail_collect_attachments(
                    access_token=access_token,
                    message_id=message_id,
                    payload=payload,
                    include_content_base64=False,
                )
                attachments_processed += len(attachments)

            internal_ms = str(detail.get("internalDate", "") or "")
            if internal_ms.isdigit():
                received_at = datetime.fromtimestamp(int(internal_ms) / 1000, tz=timezone.utc).isoformat()
            else:
                received_at = datetime.utcnow().isoformat()

            email_payload = {
                "id": message_id,
                "message_id": message_id,
                "thread_id": str(detail.get("threadId", "") or ""),
                "subject": headers.get("subject", ""),
                "email_from": headers.get("from", ""),
                "to": [to_header] if to_header else [],
                "cc": [cc_header] if cc_header else [],
                "snippet": str(detail.get("snippet", "") or "") if body.include_snippet else "",
                "body": "",
                "date": received_at,
                "mailbox": body.mailbox or "INBOX",
                "provider": "gmail",
                "account_id": body.account_id,
                "attachments": attachments,
                "target_address": body.target_to_address,
                "headers": headers if body.include_headers else {},
            }
            auto_classification = _auto_classify_email_status_after_fetch(
                email_payload=email_payload,
                attachments=attachments,
            )
            email_payload["status"] = str(auto_classification.get("status", "received") or "received")
            email_payload["classification"] = auto_classification.get("classification", {})
            imported_meta = _annotate_imported_if_exists(adapter=odoo_adapter, email_payload=email_payload)
            if imported_meta:
                email_payload["status"] = str(imported_meta.get("status", email_payload["status"]) or email_payload["status"])
                email_payload["import_info"] = imported_meta.get("import_info", {})
            upsert_email_from_external(
                db,
                tenant_id=body.tenant_id,
                connector="gmail",
                email_payload=email_payload,
                source="gmail_api_direct",
            )
            imported_count += 1
        return imported_count, len(messages), attachments_processed

    try:
        imported_count, fetched_count, attachments_processed = _run_mcp_import()
    except HTTPException as exc:
        if "unauthorized_client" not in str(exc.detail):
            raise
        imported_count, fetched_count, attachments_processed = _run_direct_gmail_import()

    return GmailSyncResponse(
        imported_count=imported_count,
        fetched_count=fetched_count,
        attachments_processed=attachments_processed,
        account_id=body.account_id,
    )


@app.post("/sync/odoo/bills/from-pdf", response_model=OdooVendorBillFromPdfResponse)
def create_odoo_vendor_bill_from_pdf(
    body: OdooVendorBillFromPdfRequest,
    db: Session = Depends(get_db),
) -> OdooVendorBillFromPdfResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    conn = get_connection(db, tenant_id=body.tenant_id, connector="odoo")
    if not conn:
        raise HTTPException(status_code=404, detail="active Odoo connection not found")

    merged_metadata = dict(conn.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=conn.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )
    adapter = AdapterFactory.from_connection("odoo", merged_metadata)
    try:
        result = adapter.create_vendor_bill_from_pdf(
            vendor_name=body.vendor_name,
            pdf_base64=body.pdf_base64,
            filename=body.filename,
        )
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=f"odoo bill import failed: {exc}") from exc
    return OdooVendorBillFromPdfResponse(
        status=str(result.get("status", "created")),
        bill_id=int(result["bill_id"]),
        attachment_id=int(result["attachment_id"]),
        vendor_name=str(result.get("vendor_name", body.vendor_name)),
        debug=result.get("debug", {}),
    )


@app.get("/odoo/vendors", response_model=list[OdooVendorRead])
def list_odoo_vendors_endpoint(
    tenant_id: str,
    search: str = "",
    limit: int = 200,
    db: Session = Depends(get_db),
) -> list[OdooVendorRead]:
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    conn = get_connection(db, tenant_id=tenant_id, connector="odoo")
    if not conn:
        raise HTTPException(status_code=404, detail="active Odoo connection not found")

    merged_metadata = dict(conn.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=conn.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )
    adapter = AdapterFactory.from_connection("odoo", merged_metadata)
    try:
        rows = adapter.list_vendors(search=search, limit=limit)
    except AdapterError as exc:
        raise HTTPException(status_code=400, detail=f"odoo vendor export failed: {exc}") from exc

    return [
        OdooVendorRead(
            id=int(row.get("id", 0)),
            name=str(row.get("name", "")),
            vat=str(row.get("vat", "") or ""),
            email=str(row.get("email", "") or ""),
            ref=str(row.get("ref", "") or ""),
            supplier_rank=int(row.get("supplier_rank", 0) or 0),
        )
        for row in rows
        if row.get("id") and row.get("name")
    ]


@app.post("/sync/odoo/bills/from-emails", response_model=EmailToOdooBillResponse)
def create_odoo_bills_from_selected_emails(
    body: EmailToOdooBillRequest,
    db: Session = Depends(get_db),
) -> EmailToOdooBillResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if not body.email_ids:
        raise HTTPException(status_code=400, detail="email_ids is required")

    conn = get_connection(db, tenant_id=body.tenant_id, connector="odoo")
    if not conn:
        raise HTTPException(status_code=404, detail="active Odoo connection not found")
    merged_metadata = dict(conn.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=conn.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )
    adapter = AdapterFactory.from_connection("odoo", merged_metadata)
    rows = get_emails_by_ids(db, tenant_id=body.tenant_id, email_ids=body.email_ids)
    row_by_id = {row.id: row for row in rows}

    items: list[EmailToOdooBillItemResult] = []
    created = 0
    for email_id in body.email_ids:
        row = row_by_id.get(email_id)
        if not row:
            items.append(
                EmailToOdooBillItemResult(
                    email_id=email_id,
                    status="not_found",
                    detail="email not found for tenant",
                )
            )
            continue

        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        attachments = payload.get("attachments", [])
        if not isinstance(attachments, list):
            attachments = []
        attachment_dicts = [item for item in attachments if isinstance(item, dict)]
        pdf_parts = _pdf_text_parts_from_attachments(attachment_dicts)
        pdf_base64, pdf_filename = _first_pdf_attachment_for_import(attachment_dicts)
        refresh_debug: dict = {"refresh_attempted": False}

        if not pdf_parts or not pdf_base64:
            try:
                refreshed_parts, refresh_debug, refreshed_attachments = _refresh_pdf_parts_from_gmail_mcp(
                    db=db,
                    tenant_id=body.tenant_id,
                    email_payload=payload,
                    include_content_base64=True,
                )
                if refreshed_parts:
                    pdf_parts = refreshed_parts
                if not pdf_base64:
                    pdf_base64, pdf_filename = _first_pdf_attachment_for_import(refreshed_attachments)
            except HTTPException as exc:
                refresh_debug = {"refresh_attempted": True, "refresh_error": str(exc.detail)}
            except Exception as exc:  # pragma: no cover
                refresh_debug = {"refresh_attempted": True, "refresh_error": str(exc)}

        combined_text = "\n\n".join(pdf_parts).strip()
        if not combined_text:
            fallback_text = [str(payload.get("body", "")).strip(), str(payload.get("snippet", "")).strip()]
            combined_text = "\n\n".join(part for part in fallback_text if part).strip()

        if not combined_text:
            items.append(
                EmailToOdooBillItemResult(
                    email_id=email_id,
                    status="skipped",
                    detail="no extractable PDF/body text found",
                    debug={"pdf_refresh": refresh_debug},
                )
            )
            continue

        invoice_check = _classify_invoice_document_with_openai(content=combined_text)
        if not bool(invoice_check.get("is_invoice")):
            set_email_status(db, tenant_id=body.tenant_id, email_id=email_id, status="?")
            items.append(
                EmailToOdooBillItemResult(
                    email_id=email_id,
                    status="skipped",
                    detail=(
                        "not an invoice document (AI check); email marked as '?'"
                        + (f": {invoice_check.get('reason')}" if invoice_check.get("reason") else "")
                    ),
                    debug={"pdf_refresh": refresh_debug, "invoice_check": invoice_check},
                )
            )
            continue

        extracted_raw = _extract_bill_fields_with_openai(content=combined_text)
        extraction_confidence = {
            "overall": extracted_raw.get("overall_confidence"),
            "field_confidence": extracted_raw.get("field_confidence", {}) if isinstance(extracted_raw.get("field_confidence", {}), dict) else {},
        }

        def _to_float(value):
            if value is None or value == "":
                return None
            try:
                return float(str(value).replace(",", ""))
            except ValueError:
                return None

        amount_value = _to_float(extracted_raw.get("amount"))
        if amount_value is None:
            amount_value = _extract_amount_fallback_from_text(combined_text)

        extracted = BillFieldExtraction(
            vendor=str(extracted_raw.get("vendor", "") or ""),
            bill_reference=str(extracted_raw.get("bill_reference", "") or ""),
            bill_date=str(extracted_raw.get("bill_date", "") or ""),
            invoice_date=str(extracted_raw.get("invoice_date", "") or ""),
            product=str(extracted_raw.get("product", "") or ""),
            accounting_date=str(extracted_raw.get("accounting_date", "") or ""),
            account_id=str(extracted_raw.get("account_id", "") or ""),
            vat_percent=str(extracted_raw.get("vat_percent", "") or ""),
            billing_id=str(extracted_raw.get("billing_id", "") or ""),
            currency=str(extracted_raw.get("currency", "") or ""),
            discount=str(extracted_raw.get("discount", "") or ""),
            payment_reference=str(extracted_raw.get("payment_reference", "") or ""),
            recipient_bank=str(extracted_raw.get("recipient_bank", "") or ""),
            price=_to_float(extracted_raw.get("price")),
            tax=str(extracted_raw.get("tax", "") or ""),
            amount=amount_value,
            due_date=str(extracted_raw.get("due_date", "") or ""),
        )

        try:
            bill_result = adapter.create_vendor_bill_from_fields(
                vendor_name=extracted.vendor or "PDF Import Vendor",
                bill_reference=extracted.bill_reference,
                bill_date=extracted.bill_date,
                invoice_date=extracted.invoice_date,
                accounting_date=extracted.accounting_date,
                account_id=extracted.account_id,
                vat_percent=extracted.vat_percent,
                billing_id=extracted.billing_id,
                currency=extracted.currency,
                discount=extracted.discount,
                payment_reference=extracted.payment_reference,
                recipient_bank=extracted.recipient_bank,
                product=extracted.product,
                price=extracted.price,
                tax=extracted.tax,
                amount=extracted.amount,
                due_date=extracted.due_date,
                pdf_base64=pdf_base64,
                pdf_filename=pdf_filename or "invoice.pdf",
            )
            bill_status = str(bill_result.get("status", "created") or "created")
            if bill_status == "already_exists":
                existing_bill_id = int(bill_result.get("bill_id", 0) or 0)
                mark_email_imported(
                    db,
                    tenant_id=body.tenant_id,
                    email_id=email_id,
                    bill_reference=extracted.bill_reference,
                    bill_id=existing_bill_id or None,
                )
                items.append(
                    EmailToOdooBillItemResult(
                        email_id=email_id,
                        status="already_imported",
                        extracted=extracted,
                        bill_id=existing_bill_id or None,
                        debug={
                            **(bill_result.get("debug", {}) if isinstance(bill_result.get("debug"), dict) else {}),
                            "pdf_refresh": refresh_debug,
                            "pdf_found_for_attachment": bool(pdf_base64),
                        },
                        detail=(
                            f"invoice already imported in Odoo for reference "
                            f"'{extracted.bill_reference or 'n/a'}' (bill_id={existing_bill_id})"
                        ),
                    )
                )
                continue
            created += 1
            created_bill_id = int(bill_result.get("bill_id", 0) or 0)
            mark_email_imported(
                db,
                tenant_id=body.tenant_id,
                email_id=email_id,
                bill_reference=extracted.bill_reference,
                bill_id=created_bill_id or None,
            )
            items.append(
                EmailToOdooBillItemResult(
                    email_id=email_id,
                    status="created",
                    extracted=extracted,
                    bill_id=created_bill_id,
                        debug={
                            **(bill_result.get("debug", {}) if isinstance(bill_result.get("debug"), dict) else {}),
                            "pdf_refresh": refresh_debug,
                            "pdf_found_for_attachment": bool(pdf_base64),
                            "invoice_check": invoice_check,
                            "extraction_confidence": extraction_confidence,
                        },
                    detail="bill created in Odoo",
                )
            )
        except AdapterError as exc:
            items.append(
                EmailToOdooBillItemResult(
                    email_id=email_id,
                    status="failed",
                    extracted=extracted,
                    debug={
                        "pdf_refresh": refresh_debug,
                        "invoice_check": invoice_check,
                        "extraction_confidence": extraction_confidence,
                    },
                    detail=str(exc),
                )
            )

    create_audit_log(
        db,
        tenant_id=body.tenant_id,
        action="bill_import_quick",
        actor=body.actor,
        entity_type="email_bill",
        entity_id=",".join(body.email_ids),
        details={
            "processed": len(body.email_ids),
            "created": created,
            "item_statuses": [{"email_id": item.email_id, "status": item.status} for item in items],
        },
    )
    return EmailToOdooBillResponse(processed=len(body.email_ids), created=created, items=items)


@app.post("/sync/odoo/bills/preview-from-emails", response_model=EmailToOdooBillPreviewResponse)
def preview_odoo_bills_from_selected_emails(
    body: EmailToOdooBillRequest,
    db: Session = Depends(get_db),
) -> EmailToOdooBillPreviewResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if not body.email_ids:
        raise HTTPException(status_code=400, detail="email_ids is required")

    rows = get_emails_by_ids(db, tenant_id=body.tenant_id, email_ids=body.email_ids)
    row_by_id = {row.id: row for row in rows}
    items: list[EmailToOdooBillPreviewItem] = []
    ready = 0

    def _to_float(value):
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    for email_id in body.email_ids:
        row = row_by_id.get(email_id)
        if not row:
            items.append(
                EmailToOdooBillPreviewItem(
                    email_id=email_id,
                    status="not_found",
                    detail="email not found for tenant",
                )
            )
            continue

        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        attachments = payload.get("attachments", [])
        attachments = [item for item in attachments if isinstance(item, dict)] if isinstance(attachments, list) else []
        pdf_parts = _pdf_text_parts_from_attachments(attachments)
        attachment_preview = _first_pdf_attachment_preview(attachments)
        refresh_debug: dict = {"refresh_attempted": False}

        if not pdf_parts or not attachment_preview.content_base64:
            try:
                refreshed_parts, refresh_debug, refreshed_attachments = _refresh_pdf_parts_from_gmail_mcp(
                    db=db,
                    tenant_id=body.tenant_id,
                    email_payload=payload,
                    include_content_base64=True,
                )
                if refreshed_parts:
                    pdf_parts = refreshed_parts
                refreshed_preview = _first_pdf_attachment_preview(refreshed_attachments)
                if refreshed_preview.content_base64:
                    attachment_preview = refreshed_preview
            except HTTPException as exc:
                refresh_debug = {"refresh_attempted": True, "refresh_error": str(exc.detail)}
            except Exception as exc:  # pragma: no cover
                refresh_debug = {"refresh_attempted": True, "refresh_error": str(exc)}

        combined_text = "\n\n".join(pdf_parts).strip()

        if not combined_text:
            items.append(
                EmailToOdooBillPreviewItem(
                    email_id=email_id,
                    status="skipped",
                    subject=str(payload.get("subject", "") or ""),
                    from_address=str(payload.get("email_from", "") or ""),
                    attachment_preview=attachment_preview,
                    detail="no extractable PDF/body text found",
                    debug={"pdf_refresh": refresh_debug},
                )
            )
            continue
        if not attachment_preview.content_base64:
            items.append(
                EmailToOdooBillPreviewItem(
                    email_id=email_id,
                    status="skipped",
                    subject=str(payload.get("subject", "") or ""),
                    from_address=str(payload.get("email_from", "") or ""),
                    extracted=BillFieldExtraction(),
                    attachment_preview=attachment_preview,
                    detail="pdf attachment preview unavailable; re-save Gmail OAuth account and retry",
                    debug={"pdf_refresh": refresh_debug},
                )
            )
            continue

        invoice_check = _classify_invoice_document_with_openai(content=combined_text)
        if not bool(invoice_check.get("is_invoice")):
            set_email_status(db, tenant_id=body.tenant_id, email_id=email_id, status="?")
            items.append(
                EmailToOdooBillPreviewItem(
                    email_id=email_id,
                    status="skipped",
                    subject=str(payload.get("subject", "") or ""),
                    from_address=str(payload.get("email_from", "") or ""),
                    attachment_preview=attachment_preview,
                    detail=(
                        "not an invoice document (AI check); email marked as '?'"
                        + (f": {invoice_check.get('reason')}" if invoice_check.get("reason") else "")
                    ),
                    debug={"pdf_refresh": refresh_debug, "invoice_check": invoice_check},
                )
            )
            continue

        extracted_raw = _extract_bill_fields_with_openai(content=combined_text)
        extraction_confidence = {
            "overall": extracted_raw.get("overall_confidence"),
            "field_confidence": extracted_raw.get("field_confidence", {}) if isinstance(extracted_raw.get("field_confidence", {}), dict) else {},
        }
        amount_value = _to_float(extracted_raw.get("amount"))
        if amount_value is None:
            amount_value = _extract_amount_fallback_from_text(combined_text)
        extracted = BillFieldExtraction(
            vendor=str(extracted_raw.get("vendor", "") or ""),
            bill_reference=str(extracted_raw.get("bill_reference", "") or ""),
            bill_date=str(extracted_raw.get("bill_date", "") or ""),
            invoice_date=str(extracted_raw.get("invoice_date", "") or ""),
            product=str(extracted_raw.get("product", "") or ""),
            accounting_date=str(extracted_raw.get("accounting_date", "") or ""),
            account_id=str(extracted_raw.get("account_id", "") or ""),
            vat_percent=str(extracted_raw.get("vat_percent", "") or ""),
            billing_id=str(extracted_raw.get("billing_id", "") or ""),
            currency=str(extracted_raw.get("currency", "") or ""),
            discount=str(extracted_raw.get("discount", "") or ""),
            payment_reference=str(extracted_raw.get("payment_reference", "") or ""),
            recipient_bank=str(extracted_raw.get("recipient_bank", "") or ""),
            price=_to_float(extracted_raw.get("price")),
            tax=str(extracted_raw.get("tax", "") or ""),
            amount=amount_value,
            due_date=str(extracted_raw.get("due_date", "") or ""),
        )

        ready += 1
        items.append(
            EmailToOdooBillPreviewItem(
                email_id=email_id,
                status="ready",
                subject=str(payload.get("subject", "") or ""),
                from_address=str(payload.get("email_from", "") or ""),
                extracted=extracted,
                attachment_preview=attachment_preview,
                detail="preview extracted; ready to import",
                debug={
                    "pdf_refresh": refresh_debug,
                    "invoice_check": invoice_check,
                    "extraction_confidence": extraction_confidence,
                },
            )
        )

    create_audit_log(
        db,
        tenant_id=body.tenant_id,
        action="bill_preview_view",
        actor=body.actor,
        entity_type="email_bill_preview",
        entity_id=",".join(body.email_ids),
        details={
            "processed": len(body.email_ids),
            "ready": ready,
            "item_statuses": [{"email_id": item.email_id, "status": item.status} for item in items],
        },
    )
    return EmailToOdooBillPreviewResponse(processed=len(body.email_ids), ready=ready, items=items)


@app.post("/sync/odoo/bills/import-from-preview", response_model=EmailToOdooBillResponse)
def import_odoo_bills_from_preview(
    body: EmailToOdooBillImportFromPreviewRequest,
    db: Session = Depends(get_db),
) -> EmailToOdooBillResponse:
    tenant = get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if not body.items:
        raise HTTPException(status_code=400, detail="items is required")

    conn = get_connection(db, tenant_id=body.tenant_id, connector="odoo")
    if not conn:
        raise HTTPException(status_code=404, detail="active Odoo connection not found")
    merged_metadata = dict(conn.metadata_json or {})
    merged_metadata.update(
        get_decrypted_credentials(
            db,
            credential_ref=conn.credential_ref,
            decrypt_fn=cipher.decrypt,
        )
    )
    adapter = AdapterFactory.from_connection("odoo", merged_metadata)
    rows = get_emails_by_ids(db, tenant_id=body.tenant_id, email_ids=[item.email_id for item in body.items])
    row_by_id = {row.id: row for row in rows}

    results: list[EmailToOdooBillItemResult] = []
    created = 0
    for item in body.items:
        extracted = item.extracted
        row = row_by_id.get(item.email_id)
        payload = row.payload_json if (row and isinstance(row.payload_json, dict)) else {}
        raw_attachments = payload.get("attachments", [])
        attachments = [a for a in raw_attachments if isinstance(a, dict)] if isinstance(raw_attachments, list) else []
        pdf_base64, pdf_filename = _first_pdf_attachment_for_import(attachments)
        if not pdf_base64:
            try:
                _, _, refreshed_attachments = _refresh_pdf_parts_from_gmail_mcp(
                    db=db,
                    tenant_id=body.tenant_id,
                    email_payload=payload,
                    include_content_base64=True,
                )
                pdf_base64, pdf_filename = _first_pdf_attachment_for_import(refreshed_attachments)
            except Exception:
                pdf_base64, pdf_filename = "", ""
        try:
            bill_result = adapter.create_vendor_bill_from_fields(
                vendor_name=extracted.vendor or "PDF Import Vendor",
                bill_reference=extracted.bill_reference,
                bill_date=extracted.bill_date,
                invoice_date=extracted.invoice_date,
                accounting_date=extracted.accounting_date,
                account_id=extracted.account_id,
                vat_percent=extracted.vat_percent,
                billing_id=extracted.billing_id,
                currency=extracted.currency,
                discount=extracted.discount,
                payment_reference=extracted.payment_reference,
                recipient_bank=extracted.recipient_bank,
                product=extracted.product,
                price=extracted.price,
                tax=extracted.tax,
                amount=extracted.amount,
                due_date=extracted.due_date,
                pdf_base64=pdf_base64,
                pdf_filename=pdf_filename or "invoice.pdf",
            )
            bill_status = str(bill_result.get("status", "created") or "created")
            if bill_status == "already_exists":
                existing_bill_id = int(bill_result.get("bill_id", 0) or 0)
                mark_email_imported(
                    db,
                    tenant_id=body.tenant_id,
                    email_id=item.email_id,
                    bill_reference=extracted.bill_reference,
                    bill_id=existing_bill_id or None,
                )
                results.append(
                    EmailToOdooBillItemResult(
                        email_id=item.email_id,
                        status="already_imported",
                        extracted=extracted,
                        bill_id=existing_bill_id or None,
                        detail=(
                            f"invoice already imported in Odoo for reference "
                            f"'{extracted.bill_reference or 'n/a'}' (bill_id={existing_bill_id})"
                        ),
                        debug={
                            **(bill_result.get("debug", {}) if isinstance(bill_result.get("debug"), dict) else {}),
                            "pdf_found_for_attachment": bool(pdf_base64),
                        },
                    )
                )
                continue
            created += 1
            created_bill_id = int(bill_result.get("bill_id", 0) or 0)
            mark_email_imported(
                db,
                tenant_id=body.tenant_id,
                email_id=item.email_id,
                bill_reference=extracted.bill_reference,
                bill_id=created_bill_id or None,
            )
            results.append(
                EmailToOdooBillItemResult(
                    email_id=item.email_id,
                    status="created",
                    extracted=extracted,
                    bill_id=created_bill_id,
                    detail="bill created in Odoo from preview fields",
                    debug={
                        **(bill_result.get("debug", {}) if isinstance(bill_result.get("debug"), dict) else {}),
                        "pdf_found_for_attachment": bool(pdf_base64),
                    },
                )
            )
        except AdapterError as exc:
            results.append(
                EmailToOdooBillItemResult(
                    email_id=item.email_id,
                    status="failed",
                    extracted=extracted,
                    detail=str(exc),
                )
            )

    create_audit_log(
        db,
        tenant_id=body.tenant_id,
        action="bill_import_from_preview",
        actor=body.actor,
        entity_type="email_bill",
        entity_id=",".join([item.email_id for item in body.items]),
        details={
            "processed": len(body.items),
            "created": created,
            "updated_fields": [
                {
                    "email_id": item.email_id,
                    "fields": item.extracted.model_dump(),
                }
                for item in body.items
            ],
            "item_statuses": [{"email_id": item.email_id, "status": item.status} for item in results],
        },
    )
    return EmailToOdooBillResponse(processed=len(body.items), created=created, items=results)


@app.get("/emails", response_model=list[EmailRead])
def list_emails_endpoint(
    tenant_id: str,
    to_address: str = "",
    from_address: str = "",
    subject_contains: str = "",
    has_attachments: bool | None = None,
    filter_logic: str = "and",
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[EmailRead]:
    if filter_logic.lower() not in {"and", "or"}:
        raise HTTPException(status_code=400, detail="filter_logic must be 'and' or 'or'")
    rows = list_emails(
        db,
        tenant_id=tenant_id,
        to_address=to_address,
        from_address=from_address,
        subject_contains=subject_contains,
        has_attachments=has_attachments,
        filter_logic=filter_logic,
        limit=limit,
    )
    return [
        EmailRead(
            id=row.id,
            tenant_id=row.tenant_id,
            subject=row.subject,
            from_address=row.from_address,
            to_address=row.to_address,
            has_attachments=bool(
                isinstance(row.payload_json, dict)
                and isinstance(row.payload_json.get("attachments", []), list)
                and len(row.payload_json.get("attachments", [])) > 0
            ),
            source=row.source,
            status=row.status,
            received_at=row.received_at,
            imported=bool(
                isinstance(row.payload_json, dict)
                and isinstance(row.payload_json.get("import_info", {}), dict)
                and str(row.payload_json.get("import_info", {}).get("status", "")).lower() == "imported"
            ),
            imported_at=str(
                row.payload_json.get("import_info", {}).get("imported_at", "")
                if isinstance(row.payload_json, dict)
                else ""
            ),
            bill_reference=str(
                row.payload_json.get("import_info", {}).get("bill_reference", "")
                if isinstance(row.payload_json, dict)
                else ""
            ),
        )
        for row in rows
    ]
    get_connection,
    get_decrypted_credentials,
