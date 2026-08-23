const AGENT_BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

export async function triggerGeneration(payload: {
  repoId: string;
  repoFullName: string;
  commitSha?: string;
}) {
  const res = await fetch(`${AGENT_BACKEND_URL}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Agent backend generation failed");
  return res.json();
}

export async function requestRegeneration(docId: string, comment: string) {
  const res = await fetch(`${AGENT_BACKEND_URL}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ docId, comment }),
  });
  if (!res.ok) throw new Error("Agent backend regeneration failed");
  return res.json();
}
