const GITBOOK_API_BASE = "https://api.gitbook.com/v1";

interface PublishParams {
  spaceId: string;
  path: string; // e.g. "docs/authentication.md"
  markdown: string;
}

export async function publishToGitbook({
  spaceId,
  path,
  markdown,
}: PublishParams) {
  const token = process.env.GITBOOK_API_TOKEN;
  if (!token) throw new Error("Missing GITBOOK_API_TOKEN");

  const res = await fetch(
    `${GITBOOK_API_BASE}/spaces/${spaceId}/content/path/${encodeURIComponent(
      path
    )}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        markdown,
      }),
    }
  );

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`GitBook publish failed: ${res.status} ${errText}`);
  }

  return res.json();
}