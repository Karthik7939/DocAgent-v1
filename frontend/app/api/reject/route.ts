import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

const BACKEND_URL = process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  const { docId, comment } = await req.json();

  await db.updateDoc(docId, {
    status: "changes_requested",
    reviewComment: comment,
  });

  try {
    const res = await fetch(`${BACKEND_URL}/api/documents/revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: docId, comment }),
    });

    if (res.ok) {
      const revisedDoc = await res.json();
      return NextResponse.json(revisedDoc);
    }
  } catch (err) {
    console.error("Agent backend revision failed:", err);
  }

  const updatedDoc = await db.getDoc(docId);
  return NextResponse.json(updatedDoc || { error: "Failed to revise" });
}