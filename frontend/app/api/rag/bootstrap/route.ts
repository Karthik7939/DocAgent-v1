import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * POST /api/rag/bootstrap
 *
 * Proxies a bootstrap request to the Python backend.
 * Body: { repositoryName: string; repositoryPath: string; commitSha?: string }
 */
export async function POST(req: NextRequest) {
  try {
    const { repositoryName, repositoryPath, commitSha } = await req.json();

    if (!repositoryName || !repositoryPath) {
      return NextResponse.json(
        { error: "repositoryName and repositoryPath are required" },
        { status: 400 }
      );
    }

    const res = await fetch(`${BACKEND_URL}/api/rag/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_name: repositoryName,
        repository_path: repositoryPath,
        commit_sha: commitSha || "HEAD",
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Bootstrap failed" },
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
