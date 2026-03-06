import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const tenantId = searchParams.get("tenant_id");
  const query = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";

  const response = await fetch(`${coreBase}/jobs${query}`, { cache: "no-store" });
  const data = await response.json().catch(() => []);
  return NextResponse.json(Array.isArray(data) ? data : [], { status: response.status });
}
