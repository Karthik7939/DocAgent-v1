"use client";

import { useEffect, useState, useCallback } from "react";

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
  const [manualInput, setManualInput] = useState("");
  const [manualAdding, setManualAdding] = useState(false);
  const [manualError, setManualError] = useState("");

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

  useEffect(() => {
    if (pendingRepos.size === 0) return;
    const timer = setInterval(() => {
      fetchAll();
    }, 10000);
    return () => clearInterval(timer);
  }, [pendingRepos, fetchAll]);

  useEffect(() => {
    if (!kbData || pendingRepos.size === 0) return;
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
      await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner, name }),
      });
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

      setPendingRepos((prev) => new Set([...prev, repoName]));
      setIndexStatus((prev) => ({ ...prev, [repoName]: "running" }));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setIndexStatus((prev) => ({ ...prev, [repoName]: "error" }));
      setIndexError((prev) => ({ ...prev, [repoName]: message }));
    }
  };

  const indexedNamesSlash = new Set(
    (kbData?.repos ?? []).map((r) => toSlashForm(r.repository))
  );

  const unindexedRepos = connectedRepos.filter(
    (r) => !indexedNamesSlash.has(r.fullName)
  );

  return (
    <div className="space-y-8">
      {/* Header section */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal mb-1">Vector Storage</p>
          <h2 className="text-2xl font-bold text-text">Knowledge Base</h2>
          <p className="text-xs text-muted mt-1">
            Vector embeddings stored in{" "}
            <span className="font-semibold capitalize text-text">
              {kbData?.backend ?? "…"}
            </span>
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-text border border-text/20 bg-surface hover:bg-canvas rounded-full px-4 py-2 transition-all disabled:opacity-50"
        >
          {loading ? (
            <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5 text-teal" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
          )}
          Refresh
        </button>
      </div>

      {kbData?.error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4 text-xs font-medium text-danger flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          {kbData.error}
        </div>
      )}

      {/* SECTION 1 — Add to KB */}
      {!loading && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-text">Add to Knowledge Base</h3>
            {unindexedRepos.length > 0 && (
              <span className="inline-flex items-center rounded-full bg-yellow-50 border border-yellow-300 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-yellow-800">
                {unindexedRepos.length} pending
              </span>
            )}
          </div>

          <div className="flex gap-2">
            <input
              id="manual-repo-input"
              type="text"
              placeholder="owner/repo  (e.g. Blrm123/MyProject)"
              value={manualInput}
              onChange={(e) => { setManualInput(e.target.value); setManualError(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleManualAdd()}
              className="flex-1 text-xs rounded-xl border border-border bg-canvas px-4 py-3 text-text placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-teal/20 focus:border-teal"
            />
            <button
              onClick={handleManualAdd}
              disabled={manualAdding || !manualInput.trim()}
              className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-5 py-3 rounded-full bg-accent-cta text-text hover:bg-yellow-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {manualAdding ? (
                <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              )}
              Add Repository
            </button>
          </div>
          {manualError && (
            <p className="text-[11px] text-danger font-medium">{manualError}</p>
          )}

          {unindexedRepos.length > 0 && (
            <p className="text-xs text-muted">
              These connected repositories have not been indexed yet. Click <strong className="text-text">Add to KB</strong> to start background embedding.
            </p>
          )}

          <div className="grid gap-3">
            {unindexedRepos.map((repo) => {
              const status = indexStatus[repo.fullName] ?? "idle";
              const errMsg = indexError[repo.fullName];
              const isRunning = status === "running";
              const isDone = status === "done";
              const isError = status === "error";

              return (
                <div
                  key={repo.fullName}
                  className={`rounded-2xl border px-5 py-4 flex items-center justify-between gap-4 transition-all
                    ${isDone ? "border-emerald-300 bg-emerald-50/60" : ""}
                    ${isError ? "border-red-200 bg-red-50/60" : ""}
                    ${isRunning ? "border-teal/30 bg-teal/5" : ""}
                    ${status === "idle" ? "border-border bg-surface hover:border-teal/40" : ""}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {isRunning ? (
                        <span className="w-2 h-2 rounded-full bg-teal animate-pulse shrink-0" />
                      ) : isDone ? (
                        <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                      ) : isError ? (
                        <span className="w-2 h-2 rounded-full bg-danger shrink-0" />
                      ) : (
                        <span className="w-2 h-2 rounded-full bg-border shrink-0" />
                      )}
                      <p className="text-sm font-bold text-text truncate">
                        {repo.fullName}
                      </p>
                    </div>

                    {isRunning && (
                      <p className="text-[11px] text-teal mt-1 font-medium">
                        Cloning & indexing in background… refresh shortly to view.
                      </p>
                    )}
                    {isDone && (
                      <p className="text-[11px] text-emerald-700 mt-1 font-medium">
                        ✓ Successfully added to knowledge base
                      </p>
                    )}
                    {isError && errMsg && (
                      <p className="text-[11px] text-danger mt-1 font-medium">
                        ✗ {errMsg}
                      </p>
                    )}
                  </div>

                  <div className="shrink-0">
                    {isDone ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-100 border border-emerald-300 rounded-full px-3.5 py-1">
                        Indexed
                      </span>
                    ) : isRunning ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-teal bg-teal/10 border border-teal/20 rounded-full px-3.5 py-1.5">
                        <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                        </svg>
                        Indexing…
                      </span>
                    ) : (
                      <button
                        onClick={() => handleAddToKB(repo)}
                        className={`inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-full transition-all border shadow-xs
                          ${isError
                            ? "bg-red-50 text-danger border-red-200 hover:bg-red-100"
                            : "bg-text text-white border-text hover:bg-text/80"
                          }`}
                      >
                        Add to KB
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SECTION 2 — Indexed Repositories */}
      {(kbData?.repos ?? []).length > 0 && (
        <div className="space-y-4 pt-4 border-t border-border">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-text">Indexed Repositories</h3>
            <span className="inline-flex items-center rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-800">
              {kbData!.repos.length} ready
            </span>
          </div>

          <div className="grid gap-3">
            {(kbData?.repos ?? []).map((repo) => {
              const isSelected = selectedRepo === repo.repository;
              const isDeleting = deletingRepo === repo.repository;
              return (
                <div
                  key={repo.repository}
                  className={`w-full text-left rounded-2xl border transition-all overflow-hidden
                    ${isSelected ? "border-teal bg-teal/5" : "border-border bg-surface hover:border-teal/40"}`}
                >
                  <div
                    className="px-5 py-4 flex items-center justify-between gap-4 cursor-pointer"
                    onClick={() => setSelectedRepo(isSelected ? null : repo.repository)}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                        <p className="text-sm font-bold text-text truncate">
                          {repo.repository}
                        </p>
                      </div>
                      <p className="text-xs text-muted mt-0.5 font-mono">
                        {repo.backend === "pinecone"
                          ? `Index: ${repo.pinecone_index}`
                          : "Local FAISS"}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Pill label="vectors" value={repo.vector_count >= 0 ? repo.vector_count.toLocaleString() : "N/A"} color="teal" />
                      {repo.chunk_count > 0 && <Pill label="chunks" value={repo.chunk_count.toLocaleString()} color="blue" />}
                      {repo.file_count > 0 && <Pill label="files" value={repo.file_count.toLocaleString()} color="green" />}
                      <svg
                        className={`w-4 h-4 text-muted transition-transform duration-200 ${isSelected ? "rotate-180" : ""}`}
                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </div>
                  </div>

                  {isSelected && (
                    <div className="border-t border-border bg-canvas px-5 py-4 space-y-3">
                      <div className="text-xs text-muted space-y-1">
                        <p><span className="font-semibold text-text">Namespace: </span>{repo.repository}</p>
                        <p><span className="font-semibold text-text">Scoping: </span>Queries isolated to <span className="font-mono">{repo.repository}</span>.</p>
                      </div>

                      <div className="flex justify-end pt-2 border-t border-border">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(repo.repository);
                          }}
                          disabled={isDeleting}
                          className="text-xs font-semibold uppercase tracking-wider px-4 py-2 rounded-full bg-red-50 text-danger hover:bg-red-100 transition-colors border border-red-200 flex items-center gap-1.5"
                        >
                          Delete Embeddings
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
    </div>
  );
}

function Pill({ label, value, color }: { label: string; value: string; color: "teal" | "blue" | "green" }) {
  const colors = {
    teal: "bg-teal/10 text-teal border-teal/20",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-semibold uppercase tracking-wider border ${colors[color]}`}>
      {value} {label}
    </span>
  );
}
