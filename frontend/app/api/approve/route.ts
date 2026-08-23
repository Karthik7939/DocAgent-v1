import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

const BACKEND_URL = process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  const { docId } = await req.json();
  const doc = await db.getDoc(docId);

  if (!doc) return NextResponse.json({ error: "Doc not found" }, { status: 404 });

  // Call Python backend to delete the .prev.md sidecar file so red/green diff lines disappear
  try {
    await fetch(`${BACKEND_URL}/api/documents/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: docId }),
    });
  } catch (err) {
    console.error("Failed to approve in backend:", err);
  }

  const updated = await db.setDocStatus(docId, "approved");
  return NextResponse.json(updated);
}