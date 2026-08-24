/**
 * lib/db.ts
 * ----------
 * Persistent JSON file-backed store for repos and document status overrides.
 *
 * Why file-based instead of in-memory?
 * The original implementation used module-level arrays (`let repos = []`)
 * which are wiped on every Next.js server restart or hot-reload, causing
 * all connected repositories to disappear.
 *
 * This implementation reads from `data/repos.json` on first access and
 * writes on every mutation. It requires no additional npm dependencies
 * and works correctly in Next.js API routes.
 *
 * NOTE: docs are still sourced from the Python backend (via backendDocs.ts).
 * Only repo records and doc status overrides are persisted locally here.
 */

import fs from "fs";
import path from "path";
import { Repo, DocVersion, DocStatus } from "@/types";
import { getGeneratedDoc, listGeneratedDocs } from "@/lib/backendDocs";

// ---------------------------------------------------------------------------
// File paths (relative to the Next.js project root)
// ---------------------------------------------------------------------------
const DATA_DIR = path.join(process.cwd(), "data");
const REPOS_FILE = path.join(DATA_DIR, "repos.json");
const DOC_STATUS_FILE = path.join(DATA_DIR, "doc_status.json");

// ---------------------------------------------------------------------------
// File I/O helpers
// ---------------------------------------------------------------------------

function ensureDataDir(): void {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

function readJSON<T>(filePath: string, fallback: T): T {
  ensureDataDir();
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJSON<T>(filePath: string, data: T): void {
  ensureDataDir();
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

// ---------------------------------------------------------------------------
// Typed accessors
// ---------------------------------------------------------------------------

function readRepos(): Repo[] {
  return readJSON<Repo[]>(REPOS_FILE, []);
}

function saveRepos(repos: Repo[]): void {
  writeJSON(REPOS_FILE, repos);
}

/** doc_status.json stores only manual status overrides keyed by doc id */
type DocStatusMap = Record<string, DocStatus>;

function readDocStatuses(): DocStatusMap {
  return readJSON<DocStatusMap>(DOC_STATUS_FILE, {});
}

function saveDocStatuses(map: DocStatusMap): void {
  writeJSON(DOC_STATUS_FILE, map);
}

// ---------------------------------------------------------------------------
// In-memory doc cache for the current request cycle
// (still sourced from backend, status overrides come from the JSON file)
// ---------------------------------------------------------------------------
let docsCache: DocVersion[] = [];

// ---------------------------------------------------------------------------
// Public database interface
// ---------------------------------------------------------------------------

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000";

export const db = {
  // ── Repos ────────────────────────────────────────────────────────────────

  listRepos: async (): Promise<Repo[]> => {
    const savedRepos = readRepos();
    const repoSet = new Map<string, Repo>();

    // Add saved repos from local storage
    for (const r of savedRepos) {
      repoSet.set(r.fullName, r);
      repoSet.set(r.id, r);
    }

    // Auto-discover active repos from generated docs backend
    try {
      const res = await fetch(`${BACKEND_URL}/api/documents/repos`, { cache: "no-store" });
      if (res.ok) {
        const backendRepos: string[] = await res.json();
        for (const repoName of backendRepos) {
          if (!repoSet.has(repoName)) {
            const repoId = repoName.replace("/", "_");
            const [owner, name] = repoName.includes("/")
              ? repoName.split("/", 2)
              : ["", repoName];
            const repoObj: Repo = {
              id: repoId,
              owner,
              name,
              fullName: repoName,
              connectedAt: new Date().toISOString(),
              webhookActive: false,
              gitbookSpaceId: "",
            };
            repoSet.set(repoName, repoObj);
          }
        }
      }
    } catch {
      // Degrade gracefully if backend call fails
    }

    return Array.from(new Set(repoSet.values()));
  },

  getRepo: async (id: string): Promise<Repo | undefined> => {
    const repos = await db.listRepos();
    return repos.find((r) => r.id === id || r.fullName === id);
  },


  addRepo: async (repo: Repo): Promise<Repo> => {
    const repos = readRepos();
    // Prevent duplicate repos (same fullName)
    const exists = repos.find((r) => r.fullName === repo.fullName);
    if (exists) return exists;
    repos.push(repo);
    saveRepos(repos);
    return repo;
  },

  /**
   * Mark a repo's webhook as actively receiving events. Called by the
   * webhook receiver route whenever a valid GitHub event is processed for
   * a known repo, so the "Webhook active" badge reflects reality instead
   * of being hardcoded true at connect time.
   */
  markWebhookReceived: async (fullName: string): Promise<Repo | undefined> => {
    const repos = readRepos();
    const idx = repos.findIndex((r) => r.fullName === fullName);
    if (idx === -1) return undefined;
    repos[idx] = {
      ...repos[idx],
      webhookActive: true,
      lastWebhookAt: new Date().toISOString(),
    };
    saveRepos(repos);
    return repos[idx];
  },

  // ── Docs ─────────────────────────────────────────────────────────────────

  listDocs: async (): Promise<DocVersion[]> => {
    const generatedDocs = await listGeneratedDocs();
    const statuses = readDocStatuses();
    docsCache = generatedDocs.map((doc) => {
      const overriddenStatus = statuses[doc.id];
      return overriddenStatus ? { ...doc, status: overriddenStatus } : doc;
    });
    return docsCache;
  },

  getDoc: async (id: string): Promise<DocVersion | undefined> => {
    const generatedDoc = await getGeneratedDoc(id);
    if (!generatedDoc) return undefined;

    const statuses = readDocStatuses();
    const overriddenStatus = statuses[id];
    const doc = overriddenStatus
      ? { ...generatedDoc, status: overriddenStatus }
      : generatedDoc;

    // Update local cache
    const idx = docsCache.findIndex((d) => d.id === id);
    if (idx === -1) docsCache.push(doc);
    else docsCache[idx] = doc;

    return doc;
  },

  addDoc: async (doc: DocVersion): Promise<DocVersion> => {
    docsCache.push(doc);
    return doc;
  },

  updateDoc: async (
    id: string,
    updates: Partial<DocVersion>
  ): Promise<DocVersion | undefined> => {
    const doc = await db.getDoc(id);
    if (!doc) return undefined;

    const updated = { ...doc, ...updates };

    // Persist status change to file
    if (updates.status) {
      const statuses = readDocStatuses();
      statuses[id] = updates.status;
      saveDocStatuses(statuses);
    }

    // Update cache
    const idx = docsCache.findIndex((d) => d.id === id);
    if (idx === -1) docsCache.push(updated);
    else docsCache[idx] = updated;

    return updated;
  },

  setDocStatus: async (
    id: string,
    status: DocStatus
  ): Promise<DocVersion | undefined> => db.updateDoc(id, { status }),
};
