import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const tenantId = searchParams.get("tenant_id") || "";
  const search = searchParams.get("search") || "";
  const limit = searchParams.get("limit") || "200";

  if (!tenantId) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  const query = new URLSearchParams({ tenant_id: tenantId, limit });
  if (search) {
    query.set("search", search);
  }

  const response = await fetch(`${coreBase}/odoo/vendors?${query.toString()}`, { cache: "no-store" });
  const data = await response.json().catch(() => []);
  return NextResponse.json(Array.isArray(data) ? data : [], { status: response.status });
}
