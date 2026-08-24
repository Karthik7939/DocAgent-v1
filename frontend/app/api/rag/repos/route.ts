import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * GET /api/rag/repos
 *
 * Proxies to the Python backend and returns all locally cloned repositories
 * along with their RAG indexing status (indexed vs. not yet in knowledge base).
 */
export async function GET() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const res = await fetch(`${BACKEND_URL}/api/rag/repos`, {
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { repos: [], backend: "unknown", error: "Backend unavailable" },
      { status: 200 }
    );
  }
}
