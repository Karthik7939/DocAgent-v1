"use client";

import { useEffect, useState, useCallback } from "react";

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

export default function KnowledgeBasePanel() {
  const [data, setData] = useState<KBState | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [deletingRepo, setDeletingRepo] = useState<string | null>(null);

  const fetchKB = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/rag/knowledge-base", { cache: "no-store" });
      if (res.ok) {
        setData(await res.json());
      }
    } catch {
      setData({ backend: "unknown", repos: [], error: "Backend unavailable" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKB();
  }, [fetchKB]);

  const handleDelete = async (repoName: string) => {
    if (!confirm(`Are you sure you want to delete all embeddings for ${repoName}? This cannot be undone.`)) {
      return;
    }
    setDeletingRepo(repoName);
    try {
      const res = await fetch(`/api/rag/knowledge-base?repo=${encodeURIComponent(repoName)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json();
        alert(`Delete failed: ${err.error || "Unknown error"}`);
      } else {
        // Success: refresh the list
        setSelectedRepo(null);
        await fetchKB();
      }
    } catch (e) {
      alert("Delete failed: network error");
    } finally {
      setDeletingRepo(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text">Knowledge Base</h2>
          <p className="text-xs text-muted mt-0.5">
            Repositories with embeddings stored in{" "}
            <span className="font-medium capitalize">{data?.backend ?? "…"}</span>
          </p>
        </div>
        <button
          onClick={fetchKB}
          disabled={loading || deletingRepo !== null}
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

      {/* Error banner */}
      {data?.error && (
        <div className="bg-[#fcecea] border border-[#f5c6c3] rounded-lg px-4 py-3 text-sm text-[#b44a3f]">
          ⚠ {data.error}
        </div>
      )}

      {/* Empty state */}
      {!loading && data?.repos.length === 0 && !data?.error && (
        <div className="border border-dashed border-border rounded-lg px-6 py-10 text-center">
          <div className="text-2xl mb-2">📦</div>
          <p className="text-sm font-medium text-text">No embeddings yet</p>
          <p className="text-xs text-muted mt-1">
            Click <span className="font-semibold">Bootstrap RAG</span> on a connected
            repository to generate and store embeddings.
          </p>
        </div>
      )}

      {/* Repo grid */}
      {(data?.repos ?? []).length > 0 && (
        <div className="grid gap-3">
          {(data?.repos ?? []).map((repo) => {
            const isSelected = selectedRepo === repo.repository;
            const isDeleting = deletingRepo === repo.repository;
            return (
              <div
                key={repo.repository}
                id={`kb-repo-${repo.repository.replace(/\//g, "-")}`}
                className={`w-full text-left rounded-lg border transition-all duration-150 overflow-hidden
                  ${
                    isSelected
                      ? "border-accent bg-[#fdf5ef]"
                      : "border-border bg-surface hover:border-accent/50"
                  }
                  ${isDeleting ? "opacity-50 pointer-events-none" : ""}`}
              >
                {/* Main row */}
                <div 
                  className="px-4 py-3 flex items-center justify-between gap-4 cursor-pointer"
                  onClick={() => setSelectedRepo(isSelected ? null : repo.repository)}
                >
                  {/* Left */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {/* Green dot — indexed */}
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

                  {/* Right — stats pills */}
                  <div className="flex items-center gap-2 shrink-0">
                    <Pill
                      label="vectors"
                      value={
                        repo.vector_count >= 0
                          ? repo.vector_count.toLocaleString()
                          : "N/A"
                      }
                      color="blue"
                    />
                    {repo.chunk_count > 0 && (
                      <Pill
                        label="chunks"
                        value={repo.chunk_count.toLocaleString()}
                        color="purple"
                      />
                    )}
                    {repo.file_count > 0 && (
                      <Pill
                        label="files"
                        value={repo.file_count.toLocaleString()}
                        color="green"
                      />
                    )}
                    {/* Expand chevron */}
                    <svg
                      className={`w-4 h-4 text-muted transition-transform duration-200 ${isSelected ? "rotate-180" : ""}`}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </div>

                {/* Expanded detail row */}
                {isSelected && (
                  <div className="border-t border-border bg-white px-4 py-3 space-y-3">
                    <div className="text-xs text-muted space-y-1">
                      <p>
                        <span className="font-medium text-text">Namespace / scope: </span>
                        {repo.repository}
                      </p>
                      <p>
                        <span className="font-medium text-text">Retrieval scoping: </span>
                        When the agent runs for{" "}
                        <span className="font-mono">{repo.repository}</span>, it
                        queries <strong>only</strong> the{" "}
                        <span className="font-mono">{repo.repository}</span> namespace
                        in {repo.backend}. No cross-repo bleed.
                      </p>
                      <p>
                        <span className="font-medium text-text">Re-index: </span>
                        Push a commit or click{" "}
                        <span className="font-semibold">Bootstrap RAG</span> on the
                        repository card above.
                      </p>
                    </div>
                    
                    <div className="flex justify-end pt-2 border-t border-border/50">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(repo.repository);
                        }}
                        disabled={isDeleting}
                        className="text-xs px-3 py-1.5 rounded bg-red-50 text-red-600 hover:bg-red-100 font-medium transition-colors border border-red-100 flex items-center gap-1.5"
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
                              <path d="M3 6h18"></path>
                              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
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
      )}
    </div>
  );
}

// ── Stat pill ───────────────────────────────────────────────────────────────
function Pill({
  label,
  value,
  color,
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
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[color]}`}
    >
      {value} {label}
    </span>
  );
}
