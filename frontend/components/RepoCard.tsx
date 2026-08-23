"use client";

import { useState, useEffect, useCallback } from "react";
import { Repo } from "@/types";

type BootstrapStatus = "idle" | "loading" | "success" | "error" | "no_backend";
type IndexStatus = { indexed: boolean; vector_count: number; backend: string } | null;

function repoPathFromFullName(fullName: string): string {
  return `repositories/${fullName.replace("/", "_")}`;
}

export default function RepoCard({ repo }: { repo: Repo }) {
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus>("idle");
  const [bootstrapMessage, setBootstrapMessage] = useState<string>("");
  const [indexStatus, setIndexStatus] = useState<IndexStatus>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  // Fetch real index status from backend
  const fetchStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const res = await fetch(
        `/api/rag/status?repo=${encodeURIComponent(repo.fullName)}`,
        { cache: "no-store" }
      );
      if (res.ok) {
        const data = await res.json();
        setIndexStatus(data);
      } else {
        setIndexStatus(null);
      }
    } catch {
      setIndexStatus(null);
    } finally {
      setLoadingStatus(false);
    }
  }, [repo.fullName]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  async function handleBootstrap() {
    setBootstrapStatus("loading");
    setBootstrapMessage("");

    try {
      const res = await fetch("/api/rag/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repositoryName: repo.fullName,
          repositoryPath: repoPathFromFullName(repo.fullName),
          commitSha: "HEAD",
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 503) {
          setBootstrapStatus("no_backend");
          setBootstrapMessage("Backend is offline. Start the Python server first.");
        } else {
          setBootstrapStatus("error");
          setBootstrapMessage(data?.error || "Bootstrap failed. Check backend logs.");
        }
      } else {
        setBootstrapStatus("success");
        setBootstrapMessage(
          data?.message || "Embeddings generated and stored successfully."
        );
        // Refresh real status from Pinecone after bootstrap
        setTimeout(() => fetchStatus(), 1500);
      }
    } catch {
      setBootstrapStatus("no_backend");
      setBootstrapMessage("Cannot reach backend. Is it running on port 8000?");
    }
  }

  // ── Index Status Badge ──────────────────────────────────────────────────
  function IndexBadge() {
    if (loadingStatus) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium bg-[#f0e9dc] text-[#7a6c5a]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#c4ac8e] animate-pulse" />
          Checking…
        </span>
      );
    }

    if (!indexStatus || !indexStatus.indexed) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium bg-[#f0e9dc] text-[#7a6c5a]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#c4ac8e]" />
          Not indexed
        </span>
      );
    }

    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium bg-[#e8f4f0] text-[#39705e]"
        title={`${indexStatus.vector_count} vectors in Pinecone (${indexStatus.backend})`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[#39705e]" />
        {indexStatus.vector_count > 0
          ? `${indexStatus.vector_count} vectors`
          : "Indexed"}
      </span>
    );
  }

  // ── Bootstrap Button ────────────────────────────────────────────────────
  const bootstrapConfig = {
    idle: { label: "Bootstrap RAG", icon: "★", cls: "bg-accent hover:bg-[#8f4d20]" },
    loading: { label: "Indexing…", icon: null, cls: "bg-accent opacity-70 cursor-not-allowed" },
    success: { label: "Re-index", icon: "✓", cls: "bg-accent hover:bg-[#8f4d20]" },
    error: { label: "Retry", icon: "↺", cls: "bg-[#b44a3f] hover:bg-[#8f3530]" },
    no_backend: { label: "Retry", icon: "↺", cls: "bg-[#b44a3f] hover:bg-[#8f3530]" },
  }[bootstrapStatus];

  return (
    <div className="border border-border rounded-lg bg-surface overflow-hidden">
      {/* Main row */}
      <div className="p-4 flex items-start justify-between gap-4">
        {/* Left — repo info */}
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text truncate">{repo.fullName}</p>
          <p className="text-xs text-muted mt-0.5">
            Connected {new Date(repo.connectedAt).toLocaleDateString()}
          </p>
          {indexStatus?.backend && (
            <p className="text-xs text-muted mt-0.5">
              Backend: <span className="font-medium">{indexStatus.backend}</span>
            </p>
          )}
        </div>

        {/* Right — badges + button */}
        <div className="flex flex-wrap items-center gap-2 shrink-0 justify-end">
          {/* Webhook badge — real status based on whether repo is in db */}
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              repo.webhookActive
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {repo.webhookActive ? "Webhook active" : "Inactive"}
          </span>

          {/* Real index status badge */}
          <IndexBadge />

          {/* Bootstrap button */}
          <button
            id={`bootstrap-btn-${repo.id}`}
            onClick={handleBootstrap}
            disabled={bootstrapStatus === "loading"}
            className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md
                       text-white transition-all duration-150 active:scale-95 ${bootstrapConfig.cls}`}
          >
            {bootstrapStatus === "loading" ? (
              <>
                <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                </svg>
                Indexing…
              </>
            ) : (
              <>
                {bootstrapConfig.icon && <span>{bootstrapConfig.icon}</span>}
                {bootstrapConfig.label}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Status message bar */}
      {bootstrapMessage && (
        <div
          className={`px-4 py-2.5 text-xs border-t border-border flex items-start gap-2 ${
            bootstrapStatus === "success"
              ? "bg-[#e8f4f0] text-[#39705e]"
              : "bg-[#fcecea] text-[#b44a3f]"
          }`}
        >
          {bootstrapStatus === "success" ? "✓" : "⚠"} {bootstrapMessage}
        </div>
      )}
    </div>
  );
}