import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function DELETE(request, { params }) {
  const { accountId } = params;
  const { searchParams } = new URL(request.url);
  const tenantId = searchParams.get("tenant_id") || "";
  if (!tenantId) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  const response = await fetch(
    `${coreBase}/gmail/accounts/${encodeURIComponent(accountId)}?tenant_id=${encodeURIComponent(tenantId)}`,
    {
      method: "DELETE",
      cache: "no-store"
    }
  );

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
