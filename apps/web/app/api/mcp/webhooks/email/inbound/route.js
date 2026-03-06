import crypto from "crypto";
import { NextResponse } from "next/server";

const mcpBase = process.env.MCP_INTERNAL_BASE || "http://mcp:3001";

export async function POST(request) {
  const payload = await request.json();
  const tenantSlug = String(payload.tenant_slug || "").trim();
  const webhookSecret = String(payload.webhook_secret || "").trim();

  if (!tenantSlug) {
    return NextResponse.json({ error: "tenant_slug is required" }, { status: 400 });
  }
  if (!webhookSecret) {
    return NextResponse.json({ error: "webhook_secret is required" }, { status: 400 });
  }

  const connector = String(payload.connector || "odoo");
  const targetAddress = String(payload.target_address || "");
  const emailPayload = payload.email_payload || {};

  const rawBody = Buffer.from(JSON.stringify(emailPayload));
  const signature = crypto
    .createHmac("sha256", webhookSecret)
    .update(rawBody)
    .digest("base64");

  const response = await fetch(`${mcpBase}/webhooks/email/inbound`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "x-tenant-slug": tenantSlug,
      "x-connector": connector,
      "x-email-webhook-signature": signature,
      ...(targetAddress ? { "x-inbound-target-address": targetAddress } : {})
    },
    body: rawBody
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
