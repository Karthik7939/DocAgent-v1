import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/debug/snapshot`, {
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json(
      { backend: { status: "offline" }, error: "Backend is unreachable" },
      { status: 503 }
    );
  }
}
