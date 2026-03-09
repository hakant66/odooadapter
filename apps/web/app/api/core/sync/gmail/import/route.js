import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function POST(request) {
  const payload = await request.json();
  const timeoutMs = Number(process.env.CORE_GMAIL_IMPORT_TIMEOUT_MS || 10 * 60 * 1000);
  let response;
  try {
    response = await fetch(`${coreBase}/sync/gmail/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(timeoutMs)
    });
  } catch (error) {
    const code = error?.cause?.code || error?.code || "";
    const message =
      code === "UND_ERR_HEADERS_TIMEOUT" || code === "ABORT_ERR"
        ? `core gmail import timed out after ${timeoutMs}ms`
        : `core gmail import request failed: ${error?.message || "unknown error"}`;
    return NextResponse.json({ error: message, code }, { status: 504 });
  }

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
