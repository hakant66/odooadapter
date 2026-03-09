import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const tenantId = searchParams.get("tenant_id") || "";
  const toAddress = searchParams.get("to_address") || "";
  const fromAddress = searchParams.get("from_address") || "";
  const subjectContains = searchParams.get("subject_contains") || "";
  const hasAttachments = searchParams.get("has_attachments") || "";
  const filterLogic = searchParams.get("filter_logic") || "";
  const limit = searchParams.get("limit") || "100";

  if (!tenantId) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  const query = new URLSearchParams({ tenant_id: tenantId, limit });
  if (toAddress) {
    query.set("to_address", toAddress);
  }
  if (fromAddress) {
    query.set("from_address", fromAddress);
  }
  if (subjectContains) {
    query.set("subject_contains", subjectContains);
  }
  if (hasAttachments) {
    query.set("has_attachments", hasAttachments);
  }
  if (filterLogic) {
    query.set("filter_logic", filterLogic);
  }

  const response = await fetch(`${coreBase}/emails?${query.toString()}`, { cache: "no-store" });
  const data = await response.json().catch(() => []);
  return NextResponse.json(Array.isArray(data) ? data : [], { status: response.status });
}
