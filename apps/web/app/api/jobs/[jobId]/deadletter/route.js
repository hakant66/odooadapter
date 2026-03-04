import { NextResponse } from "next/server";

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

export async function POST(request, { params }) {
  const { jobId } = params;

  await fetch(`${coreBase}/jobs/${jobId}/deadletter`, {
    method: "POST",
    cache: "no-store"
  });

  return NextResponse.redirect(new URL("/", request.url), 303);
}
