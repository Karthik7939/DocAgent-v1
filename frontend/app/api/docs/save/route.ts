import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

const BACKEND_URL = process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  const { docId, content } = await req.json();

  if (!docId || content === undefined) {
    return NextResponse.json({ error: "Missing docId or content" }, { status: 400 });
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/documents/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: docId, content }),
    });

    if (res.ok) {
      const updatedDoc = await res.json();
      await db.updateDoc(docId, { status: "pending_review" });
      return NextResponse.json(updatedDoc);
    }
  } catch (err) {
    console.error("Backend document save failed:", err);
  }

  return NextResponse.json({ error: "Failed to save manual edits" }, { status: 500 });
}
