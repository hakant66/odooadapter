import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const response = await fetch(`${coreBase}/audit/logs?${searchParams.toString()}`, {
    method: "GET",
    cache: "no-store"
  });
  const data = await response.json().catch(() => ([]));
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request) {
  const payload = await request.json();
  const response = await fetch(`${coreBase}/audit/logs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
