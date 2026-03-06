import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${coreBase}/health`, { cache: "no-store" });
    const data = await response.json().catch(() => ({ ok: false, service: "unknown" }));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json({ ok: false, service: "unreachable", error: String(error) }, { status: 503 });
  }
}
