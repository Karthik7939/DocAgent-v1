import "server-only";

import { DocVersion } from "@/types";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

interface BackendDocumentSummary {
  id: string;
  repo_id: string;
  title: string;
  source_path: string;
  status: DocVersion["status"];
  created_at: string;
  has_changes: boolean;
}

interface BackendDocument extends BackendDocumentSummary {
  content: string;
  previous_content: string | null;
}

function toDocVersion(document: BackendDocument): DocVersion {
  return {
    id: document.id,
    repoId: document.repo_id,
    title: document.title,
    content: document.content,
    previousContent: document.previous_content ?? undefined,
    hasChanges: document.has_changes,
    status: document.status,
    createdAt: document.created_at,
  };
}

export async function listGeneratedDocs(): Promise<DocVersion[]> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/documents`, {
      cache: "no-store",
    });
  } catch (error) {
    console.error("Generated-document backend is unavailable:", error);
    return [];
  }

  if (!response.ok) {
    throw new Error(`Could not load generated documents (${response.status})`);
  }

  const documents: BackendDocumentSummary[] = await response.json();
  return documents.map((document) => ({
    id: document.id,
    repoId: document.repo_id,
    title: document.title,
    content: "",
    previousContent: undefined,
    hasChanges: document.has_changes,
    status: document.status,
    createdAt: document.created_at,
  }));
}

export async function getGeneratedDoc(id: string): Promise<DocVersion | undefined> {
  let response: Response;
  try {
    response = await fetch(
      `${BACKEND_URL}/api/documents/content?id=${encodeURIComponent(id)}`,
      { cache: "no-store" }
    );
  } catch (error) {
    console.error("Generated-document backend is unavailable:", error);
    return undefined;
  }

  if (response.status === 404) return undefined;
  if (!response.ok) {
    throw new Error(`Could not load generated document (${response.status})`);
  }

  return toDocVersion(await response.json());
}
