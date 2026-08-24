"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

interface ConnectedRepo {
  id: string;
  fullName: string;
  owner?: string;
  name?: string;
  url?: string;
}

interface EmbeddedRepo {
  repository: string;
  vector_count: number;
  file_count: number;
  chunk_count: number;
  indexed: boolean;
  backend: string;
  pinecone_index?: string;
}

interface KBState {
  backend: string;
  repos: EmbeddedRepo[];
  error?: string;
}

type IndexStatus = "idle" | "running" | "done" | "error";

// ── Component ────────────────────────────────────────────────────────────────

// Normalize a repo name to slash form (owner/repo).
// Pinecone namespaces may be stored either as the slug form (owner_repo)
// or already in slash form (owner/repo), depending on which code path
// indexed them. Only convert the slug form — if a slash is already present,
// the name must be left untouched, since the repo name itself can contain
// underscores (e.g. "Blrm123/Doc_generation_test") and blindly replacing
// the first underscore would corrupt it into "Blrm123/Doc/generation_test",
// breaking the match against the connected repo's fullName.
function toSlashForm(name: string): string {
  if (name.includes("/")) return name;
  return name.replace("_", "/");
}

export default function KnowledgeBasePanel() {
  const [kbData, setKbData] = useState<KBState | null>(null);
  const [connectedRepos, setConnectedRepos] = useState<ConnectedRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [deletingRepo, setDeletingRepo] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<Record<string, IndexStatus>>({});
  const [indexError, setIndexError] = useState<Record<string, string>>({});
  const [pendingRepos, setPendingRepos] = useState<Set<string>>(new Set());
  // Manual "add repo" input
  const [manualInput, setManualInput] = useState("");
  const [manualAdding, setManualAdding] = useState(false);
  const [manualError, setManualError] = useState("");

  // ── Fetch data ────────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [kbRes, reposRes] = await Promise.all([
        fetch("/api/rag/knowledge-base", { cache: "no-store" }),
        fetch("/api/repos", { cache: "no-store" }),
      ]);

      if (kbRes.ok) setKbData(await kbRes.json());
      else setKbData({ backend: "unknown", repos: [], error: "Failed to load KB" });

      if (reposRes.ok) {
        const repos: ConnectedRepo[] = await reposRes.json();
        setConnectedRepos(repos);
      }
    } catch {
      setKbData({ backend: "unknown", repos: [], error: "Backend unavailable" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Auto-refresh while there are pending indexing jobs (poll every 10s)
  useEffect(() => {
    if (pendingRepos.size === 0) return;
    const timer = setInterval(() => {
      fetchAll();
    }, 10000);
    return () => clearInterval(timer);
  }, [pendingRepos, fetchAll]);

  // ── When KB refreshes, resolve any done pending repos ─────────────────────

  useEffect(() => {
    if (!kbData || pendingRepos.size === 0) return;
    // Normalize KB names to slash form for comparison
    const kbSlashNames = new Set(kbData.repos.map((r) => toSlashForm(r.repository)));
    const nowDone = [...pendingRepos].filter((r) => kbSlashNames.has(r));
    if (nowDone.length > 0) {
      setPendingRepos((prev) => {
        const next = new Set(prev);
        nowDone.forEach((r) => next.delete(r));
        return next;
      });
      setIndexStatus((prev) => {
        const next = { ...prev };
        nowDone.forEach((r) => { next[r] = "done"; });
        return next;
      });
    }
  }, [kbData, pendingRepos]);

  // ── Delete handler ────────────────────────────────────────────────────────

  const handleDelete = async (repoName: string) => {
    if (
      !confirm(
        `Are you sure you want to delete all embeddings for "${repoName}"? This cannot be undone.`
      )
    )
      return;

    setDeletingRepo(repoName);
    try {
      const res = await fetch(
        `/api/rag/knowledge-base?repo=${encodeURIComponent(repoName)}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const err = await res.json();
        alert(`Delete failed: ${err.error || "Unknown error"}`);
      } else {
        setSelectedRepo(null);
        await fetchAll();
      }
    } catch {
      alert("Delete failed: network error");
    } finally {
      setDeletingRepo(null);
    }
  };

  // ── Manual add handler (for repos not in auto-discovered list) ─────────────

  const handleManualAdd = async () => {
    const raw = manualInput.trim();
    if (!raw || !raw.includes("/")) {
      setManualError("Enter a valid repo name, e.g. owner/repo");
      return;
    }
    const [owner, ...rest] = raw.split("/");
    const name = rest.join("/");
    if (!owner || !name) {
      setManualError("Format must be owner/repo");
      return;
    }
    setManualError("");
    setManualAdding(true);
    try {
      // Register in repos.json so it shows in the list
      await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner, name }),
      });
      // Start indexing
      const repoName = raw;
      setIndexStatus((prev) => ({ ...prev, [repoName]: "running" }));
      const res = await fetch("/api/rag/index-repo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repositoryName: repoName }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Failed to start indexing");
      }
      setPendingRepos((prev) => new Set([...prev, repoName]));
      setManualInput("");
      await fetchAll();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setManualError(msg);
    } finally {
      setManualAdding(false);
    }
  };

  // ── Add to KB handler ─────────────────────────────────────────────────────

  const handleAddToKB = async (repo: ConnectedRepo) => {
    const repoName = repo.fullName;
    setIndexStatus((prev) => ({ ...prev, [repoName]: "running" }));
    setIndexError((prev) => {
      const next = { ...prev };
      delete next[repoName];
      return next;
    });

    try {
      const res = await fetch("/api/rag/index-repo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repositoryName: repoName }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Failed to start indexing");
      }

      // 202 accepted — indexing is happening in background
      // Mark as pending so we keep polling
      setPendingRepos((prev) => new Set([...prev, repoName]));
      setIndexStatus((prev) => ({ ...prev, [repoName]: "running" }));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setIndexStatus((prev) => ({ ...prev, [repoName]: "error" }));
      setIndexError((prev) => ({ ...prev, [repoName]: message }));
    }
  };

  // ── Derived state ─────────────────────────────────────────────────────────

  // Normalize KB repo names to slash form (Pinecone may store them as owner_repo)
  const indexedNamesSlash = new Set(
    (kbData?.repos ?? []).map((r) => toSlashForm(r.repository))
  );

  // Connected repos not yet in KB (compare both in slash form)
  const unindexedRepos = connectedRepos.filter(
    (r) => !indexedNamesSlash.has(r.fullName)
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* ── Header row ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text">Knowledge Base</h2>
          <p className="text-xs text-muted mt-0.5">
            Vector embeddings stored in{" "}
            <span className="font-medium capitalize">
              {kbData?.backend ?? "…"}
            </span>
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="text-xs text-muted hover:text-text transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {loading ? (
            <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
          )}
          Refresh
        </button>
      </div>

      {/* ── Error banner ── */}
      {kbData?.error && (
        <div className="bg-[#fcecea] border border-[#f5c6c3] rounded-lg px-4 py-3 text-sm text-[#b44a3f]">
          ⚠ {kbData.error}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 1 — Add to Knowledge Base (manual entry + auto-discovered)
      ══════════════════════════════════════════════════════════════════ */}
      {!loading && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text">Add to Knowledge Base</h3>
            {unindexedRepos.length > 0 && (
              <span className="inline-flex items-center rounded-full bg-amber-100 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                {unindexedRepos.length} not indexed
              </span>
            )}
          </div>

          {/* Manual entry — for brand-new webhook repos not yet in the list */}
          <div className="flex gap-2">
            <input
              id="manual-repo-input"
              type="text"
              placeholder="owner/repo  (e.g. Blrm123/MyProject)"
              value={manualInput}
              onChange={(e) => { setManualInput(e.target.value); setManualError(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleManualAdd()}
              className="flex-1 text-xs rounded-lg border border-border bg-white px-3 py-2 text-text placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:border-purple-400"
            />
            <button
              onClick={handleManualAdd}
              disabled={manualAdding || !manualInput.trim()}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-purple-600 text-white border border-purple-700 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {manualAdding ? (
                <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              )}
              Add
            </button>
          </div>
          {manualError && (
            <p className="text-[11px] text-red-600 font-medium">{manualError}</p>
          )}

          {unindexedRepos.length > 0 && (
            <p className="text-xs text-muted">
              These connected repositories have not been indexed yet.
              Click <strong>Add to KB</strong> — DocAgent will clone and embed them automatically.
            </p>
          )}

          <div className="grid gap-2">
            {unindexedRepos.map((repo) => {
              const status = indexStatus[repo.fullName] ?? "idle";
              const errMsg = indexError[repo.fullName];
              const isRunning = status === "running";
              const isDone = status === "done";
              const isError = status === "error";

              return (
                <div
                  key={repo.fullName}
                  id={`kb-add-${repo.fullName.replace(/\//g, "-")}`}
                  className={`rounded-xl border px-4 py-3 flex items-center justify-between gap-4 transition-all duration-200
                    ${isDone ? "border-emerald-300 bg-emerald-50/60" : ""}
                    ${isError ? "border-red-200 bg-red-50/60" : ""}
                    ${isRunning ? "border-purple-200 bg-purple-50/40" : ""}
                    ${status === "idle" ? "border-dashed border-border/80 bg-canvas/50 hover:border-purple-300/60 hover:bg-purple-50/20" : ""}`}
                >
                  {/* Left */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {isRunning ? (
                        <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse shrink-0" />
                      ) : isDone ? (
                        <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                      ) : isError ? (
                        <span className="w-2 h-2 rounded-full bg-red-400 shrink-0" />
                      ) : (
                        <span className="w-2 h-2 rounded-full bg-slate-300 shrink-0" />
                      )}
                      <p className="text-sm font-semibold text-text truncate">
                        {repo.fullName}
                      </p>
                    </div>

                    {isRunning && (
                      <p className="text-[11px] text-purple-600 mt-1 pl-4 font-medium">
                        ⏳ Cloning &amp; indexing in background… refresh in a minute to see it appear.
                      </p>
                    )}
                    {isDone && (
                      <p className="text-[11px] text-emerald-700 mt-1 pl-4 font-medium">
                        ✓ Successfully added to knowledge base
                      </p>
                    )}
                    {isError && errMsg && (
                      <p className="text-[11px] text-red-600 mt-1 pl-4 font-medium">
                        ✗ {errMsg}
                      </p>
                    )}
                  </div>

                  {/* Right — Action button */}
                  <div className="shrink-0">
                    {isDone ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-100 border border-emerald-300 rounded-full px-3 py-1">
                        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        Indexed
                      </span>
                    ) : isRunning ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-purple-700 bg-purple-100 border border-purple-200 rounded-full px-3 py-1.5">
                        <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                        </svg>
                        Indexing…
                      </span>
                    ) : (
                      <button
                        onClick={() => handleAddToKB(repo)}
                        id={`btn-add-kb-${repo.fullName.replace(/\//g, "-")}`}
                        className={`inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg transition-all border shadow-xs
                          ${isError
                            ? "bg-red-50 text-red-700 border-red-200 hover:bg-red-100"
                            : "bg-purple-600 text-white border-purple-700 hover:bg-purple-700 hover:shadow-sm active:scale-[0.98]"
                          }`}
                      >
                        {isError ? (
                          <>
                            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                            </svg>
                            Retry
                          </>
                        ) : (
                          <>
                            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                            </svg>
                            Add to KB
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}


      {/* ══════════════════════════════════════════════════════════════════
          SECTION 2 — Already indexed repositories
      ══════════════════════════════════════════════════════════════════ */}
      {(kbData?.repos ?? []).length > 0 && (
        <div className="space-y-3">
          {/* Divider only when both sections exist */}
          {unindexedRepos.length > 0 && (
            <div className="border-t border-border/50 pt-2" />
          )}
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text">Indexed Repositories</h3>
            <span className="inline-flex items-center rounded-full bg-emerald-100 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
              {kbData!.repos.length} indexed
            </span>
          </div>

          <div className="grid gap-3">
            {(kbData?.repos ?? []).map((repo) => {
              const isSelected = selectedRepo === repo.repository;
              const isDeleting = deletingRepo === repo.repository;
              return (
                <div
                  key={repo.repository}
                  id={`kb-repo-${repo.repository.replace(/\//g, "-")}`}
                  className={`w-full text-left rounded-xl border transition-all duration-150 overflow-hidden
                    ${isSelected ? "border-accent bg-[#fdf5ef]" : "border-border bg-surface hover:border-accent/50"}
                    ${isDeleting ? "opacity-50 pointer-events-none" : ""}`}
                >
                  {/* Main row */}
                  <div
                    className="px-4 py-3 flex items-center justify-between gap-4 cursor-pointer"
                    onClick={() => setSelectedRepo(isSelected ? null : repo.repository)}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-[#39705e] shrink-0" />
                        <p className="text-sm font-semibold text-text truncate">
                          {repo.repository}
                        </p>
                      </div>
                      <p className="text-xs text-muted mt-0.5 pl-4">
                        {repo.backend === "pinecone"
                          ? `Index: ${repo.pinecone_index}`
                          : "Local FAISS"}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Pill
                        label="vectors"
                        value={repo.vector_count >= 0 ? repo.vector_count.toLocaleString() : "N/A"}
                        color="blue"
                      />
                      {repo.chunk_count > 0 && (
                        <Pill label="chunks" value={repo.chunk_count.toLocaleString()} color="purple" />
                      )}
                      {repo.file_count > 0 && (
                        <Pill label="files" value={repo.file_count.toLocaleString()} color="green" />
                      )}
                      <svg
                        className={`w-4 h-4 text-muted transition-transform duration-200 ${isSelected ? "rotate-180" : ""}`}
                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </div>
                  </div>

                  {/* Expanded row */}
                  {isSelected && (
                    <div className="border-t border-border bg-white px-4 py-3 space-y-3">
                      <div className="text-xs text-muted space-y-1">
                        <p>
                          <span className="font-medium text-text">Namespace / scope: </span>
                          {repo.repository}
                        </p>
                        <p>
                          <span className="font-medium text-text">Retrieval scoping: </span>
                          Agents query <strong>only</strong> the{" "}
                          <span className="font-mono">{repo.repository}</span> namespace —
                          zero cross-repo data bleed.
                        </p>
                        <p>
                          <span className="font-medium text-text">Re-index: </span>
                          Delete embeddings and use <strong>Add to KB</strong> to re-index,
                          or push a commit to trigger automatic incremental updates.
                        </p>
                      </div>

                      <div className="flex justify-end pt-2 border-t border-border/50">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(repo.repository);
                          }}
                          disabled={isDeleting}
                          className="text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 font-medium transition-colors border border-red-100 flex items-center gap-1.5"
                        >
                          {isDeleting ? (
                            <>
                              <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                              </svg>
                              Deleting...
                            </>
                          ) : (
                            <>
                              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                                <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                              </svg>
                              Delete Embeddings
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Indexed = 0 but has connected repos */}
      {!loading && (kbData?.repos ?? []).length === 0 && connectedRepos.length > 0 && !kbData?.error && (
        <div className="border border-dashed border-border rounded-xl px-6 py-6 text-center">
          <div className="text-lg mb-1">🔍</div>
          <p className="text-sm font-medium text-text">No embeddings indexed yet</p>
          <p className="text-xs text-muted mt-1">
            Use <strong>Add to KB</strong> above to start indexing your repositories.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Stat pill ─────────────────────────────────────────────────────────────────
function Pill({
  label, value, color,
}: {
  label: string;
  value: string;
  color: "blue" | "purple" | "green";
}) {
  const colors = {
    blue: "bg-blue-50 text-blue-700",
    purple: "bg-purple-50 text-purple-700",
    green: "bg-[#e8f4f0] text-[#39705e]",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[color]}`}>
      {value} {label}
    </span>
  );
}
