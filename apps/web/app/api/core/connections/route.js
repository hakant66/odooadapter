import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const tenantId = searchParams.get("tenant_id") || "";
  if (!tenantId) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  const connector = searchParams.get("connector");
  const limit = searchParams.get("limit");
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (connector) params.set("connector", connector);
  if (limit) params.set("limit", limit);

  const response = await fetch(`${coreBase}/connections?${params.toString()}`, {
    cache: "no-store"
  });
  const data = await response.json().catch(() => []);
  return NextResponse.json(Array.isArray(data) ? data : [], { status: response.status });
}

export async function POST(request) {
  const payload = await request.json();
  const response = await fetch(`${coreBase}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload)
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
