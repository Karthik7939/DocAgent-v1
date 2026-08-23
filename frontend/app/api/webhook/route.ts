import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { db } from "@/lib/db";
import { triggerGeneration } from "@/lib/agentBackend";

function verifySignature(body: string, signature: string | null) {
  if (!signature) return false;
  const secret = process.env.GITHUB_WEBHOOK_SECRET!;
  const hmac = crypto.createHmac("sha256", secret);
  const digest = "sha256=" + hmac.update(body).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(digest), Buffer.from(signature));
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const signature = req.headers.get("x-hub-signature-256");

  if (!verifySignature(rawBody, signature)) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  const payload = JSON.parse(rawBody);
  const repoFullName = payload.repository?.full_name;
  const commitSha = payload.after;

  const repos = await db.listRepos();
  const repo = repos.find((r) => r.fullName === repoFullName);

  if (!repo) {
    return NextResponse.json({ error: "Repo not connected" }, { status: 404 });
  }

  await triggerGeneration({
    repoId: repo.id,
    repoFullName: repo.fullName,
    commitSha,
  });

  return NextResponse.json({ status: "generation triggered" });
}