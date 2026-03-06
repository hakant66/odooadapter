import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function POST(_request, { params }) {
  const { jobId } = params;
  const response = await fetch(`${coreBase}/jobs/${jobId}/deadletter`, {
    method: "POST",
    cache: "no-store"
  });

  const data = await response.json().catch(() => ({}));
  return NextResponse.json(data, { status: response.status });
}
