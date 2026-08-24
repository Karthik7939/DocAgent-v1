import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * POST /api/rag/index-repo
 *
 * Proxies to the Python backend to clone (if needed) and bootstrap
 * a repository into the RAG knowledge base without requiring a push event.
 *
 * Body: { repositoryName: string; cloneUrl?: string }
 */
export async function POST(req: NextRequest) {
  try {
    const { repositoryName, cloneUrl } = await req.json();

    if (!repositoryName) {
      return NextResponse.json(
        { error: "repositoryName is required" },
        { status: 400 }
      );
    }

    const res = await fetch(`${BACKEND_URL}/api/rag/index-repo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_name: repositoryName,
        clone_url: cloneUrl || "",
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Index failed" },
        { status: res.status }
      );
    }

    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Backend unavailable: ${message}` },
      { status: 503 }
    );
  }
}
