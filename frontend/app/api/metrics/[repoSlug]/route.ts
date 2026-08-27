import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * GET /api/metrics/[repoSlug]
 *
 * Proxies to the Python backend's analytics endpoint for one repository.
 * repoSlug is the underscored form, e.g. "Owner_repo-name".
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ repoSlug: string }> }
) {
  const { repoSlug } = await params;

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/metrics/${encodeURIComponent(repoSlug)}`,
      { cache: "no-store" }
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Metrics request failed" },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Backend unavailable: ${message}` },
      { status: 503 }
    );
  }
}
