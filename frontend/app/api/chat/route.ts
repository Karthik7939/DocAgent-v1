import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * POST /api/chat
 *
 * Proxies a documentation-chatbot question to the Python backend.
 * Body: { repositoryName: string; question: string; history?: {role, content}[] }
 */
export async function POST(req: NextRequest) {
  try {
    const { repositoryName, question, history } = await req.json();

    if (!repositoryName || !question) {
      return NextResponse.json(
        { error: "repositoryName and question are required" },
        { status: 400 }
      );
    }

    const res = await fetch(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_name: repositoryName,
        question,
        history: history || [],
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Chat request failed" },
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
