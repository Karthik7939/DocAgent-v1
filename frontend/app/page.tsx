import { db } from "@/lib/db";
import Link from "next/link";
import { DocVersion, Repo } from "@/types";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const docs = await db.listDocs();
  const repos = await db.listRepos();

  const updatedDocsCount = docs.filter((d) => d.hasChanges).length;
  const publishedDocsCount = docs.filter((d) => d.status === "published" || d.status === "approved").length;

  return (
    <div className="space-y-8 pb-12">
      {/* Hero Welcome Banner */}
      <div className="relative overflow-hidden rounded-3xl border border-accent/20 bg-gradient-to-br from-surface via-amber-500/5 to-canvas p-6 sm:p-8 shadow-md">
        {/* Ambient Glow Effects */}
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
        <div className="pointer-events-none absolute -left-16 -bottom-16 h-64 w-64 rounded-full bg-amber-500/10 blur-3xl" />

        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2 max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-50/80 px-3 py-1 text-xs font-semibold text-amber-900 shadow-2xs backdrop-blur-md">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              DocAgent Engine — System Ready
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
              Documentation Command Center
            </h1>
            <p className="text-sm font-medium text-muted leading-relaxed">
              Autonomous repository analysis, incremental change tracking, and standard documentation sync for your codebase.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/review"
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-xs font-bold text-white shadow-md transition-all hover:bg-accent/90 hover:scale-[1.01] active:scale-[0.99]"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              Review Documents
            </Link>

            <Link
              href="/knowledge-base"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-white px-4 py-2.5 text-xs font-bold text-text shadow-2xs transition-all hover:bg-accent-soft hover:border-accent/40"
            >
              <svg className="w-4 h-4 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8-4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              Knowledge Base
            </Link>

            <Link
              href="/gitbook"
              className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs font-bold text-blue-800 shadow-2xs transition-all hover:bg-blue-100"
            >
              <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              GitBook Sync
            </Link>
          </div>
        </div>
      </div>

      {/* KPI Metrics Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Metric 1: Repositories */}
        <div className="group relative overflow-hidden rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all duration-200 hover:border-accent/40">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-muted">Connected Projects</span>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 text-blue-700 border border-blue-200/80">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-text">{repos.length}</span>
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-200">
              Active
            </span>
          </div>
          <p className="mt-1 text-[11px] font-medium text-muted">
            Auto-synced via webhook
          </p>
        </div>

        {/* Metric 2: Total Documents */}
        <div className="group relative overflow-hidden rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all duration-200 hover:border-accent/40">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-muted">Tracked Docs</span>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-purple-500/10 text-purple-700 border border-purple-200/80">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-text">{docs.length}</span>
            <span className="text-xs font-semibold text-purple-700 bg-purple-100 px-2 py-0.5 rounded-full border border-purple-200">
              Standard Suite
            </span>
          </div>
          <p className="mt-1 text-[11px] font-medium text-muted">
            README, Arch, Changelog, Security
          </p>
        </div>

        {/* Metric 3: Updated Diffs */}
        <div className="group relative overflow-hidden rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all duration-200 hover:border-accent/40">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-muted">Pending Updates</span>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 text-amber-700 border border-amber-200/80">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-text">{updatedDocsCount}</span>
            {updatedDocsCount > 0 ? (
              <span className="relative flex items-center gap-1 text-xs font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-300">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                Action Needed
              </span>
            ) : (
              <span className="text-xs font-medium text-muted">Up to date</span>
            )}
          </div>
          <p className="mt-1 text-[11px] font-medium text-muted">
            Modified by latest commit
          </p>
        </div>

        {/* Metric 4: Health / Published */}
        <div className="group relative overflow-hidden rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all duration-200 hover:border-accent/40">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-muted">Reviewed Docs</span>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-700 border border-emerald-200/80">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-text">{publishedDocsCount}</span>
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-200">
              {docs.length > 0 ? Math.round((publishedDocsCount / docs.length) * 100) : 100}% Ready
            </span>
          </div>
          <p className="mt-1 text-[11px] font-medium text-muted">
            Approved & Verified
          </p>
        </div>
      </div>

      {/* Main Grid: Recent Docs (Left 2/3) & Connected Projects / Quick Links (Right 1/3) */}
      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left Column: Recent Documentation Hub */}
        <div className="space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold tracking-tight text-text">
                Recent Documentation
              </h2>
              <p className="text-xs font-medium text-muted">
                Generated project overview, architecture, and security specifications
              </p>
            </div>

            <Link
              href="/review"
              className="text-xs font-bold text-accent hover:underline flex items-center gap-1"
            >
              View All ({docs.length})
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>

          <div className="overflow-hidden rounded-2xl border border-border/80 bg-surface shadow-xs">
            {docs.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 mb-3 border border-amber-200">
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                  </svg>
                </div>
                <h3 className="text-sm font-bold text-text">No documentation generated yet</h3>
                <p className="mt-1 text-xs text-muted max-w-sm">
                  Connect a GitHub repository to trigger the automated RAG understanding and documentation agent pipeline.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/60">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="group p-4 transition-all duration-200 hover:bg-white flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                  >
                    <div className="flex items-start gap-3 min-w-0">
                      <DocTypeIcon title={doc.title} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-text truncate group-hover:text-accent transition-colors">
                            {doc.title.split("/").at(-1)}
                          </h4>
                          {doc.hasChanges && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[9px] font-extrabold text-amber-800 uppercase tracking-wider">
                              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                              Modified
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted font-mono truncate">
                          {doc.title}
                        </p>
                        <p className="mt-1 text-[11px] text-muted/80">
                          Updated {new Date(doc.createdAt).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-3 flex-shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-border/40">
                      <StatusBadge status={doc.status} />
                      <Link
                        href={`/review/${doc.id}`}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-white px-3.5 py-1.5 text-xs font-bold text-text shadow-2xs transition-all hover:bg-accent-soft hover:border-accent/30 hover:text-accent"
                      >
                        Review
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                        </svg>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Connected Projects & Quick Navigation Cards */}
        <div className="space-y-6">
          {/* Connected Repositories Card */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-text flex items-center gap-2">
                <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Connected Projects
              </h3>
            </div>

            <div className="overflow-hidden rounded-2xl border border-border/80 bg-surface p-3.5 shadow-xs space-y-2">
              {repos.length === 0 ? (
                <p className="text-xs text-muted p-2">No repositories connected.</p>
              ) : (
                repos.map((repo) => (
                  <div
                    key={repo.id}
                    className="flex items-center justify-between rounded-xl border border-border/50 bg-white p-2.5 text-xs transition-colors hover:border-accent/30"
                  >
                    <div className="min-w-0 pr-2">
                      <p className="font-bold text-text truncate">{repo.fullName}</p>
                      <p className="text-[10px] font-mono text-muted">Branch: main</p>
                    </div>
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 border border-emerald-300 px-2 py-0.5 text-[9px] font-bold text-emerald-800 flex-shrink-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Active
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Quick System Navigation Shortcuts */}
          <div className="rounded-2xl border border-border/80 bg-surface p-4 shadow-xs space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted flex items-center gap-2">
              <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Quick Integration Hub
            </h3>

            <div className="space-y-2 text-xs font-semibold">
              <Link
                href="/knowledge-base"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white border border-border/60 transition-colors hover:border-purple-300 hover:bg-purple-50/50"
              >
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-purple-500" />
                  <span className="text-text">Vector Knowledge Base</span>
                </div>
                <span className="text-[10px] text-purple-700 font-mono">View Store →</span>
              </Link>

              <Link
                href="/gitbook"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white border border-border/60 transition-colors hover:border-blue-300 hover:bg-blue-50/50"
              >
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-blue-500" />
                  <span className="text-text">GitBook Integration</span>
                </div>
                <span className="text-[10px] text-blue-700 font-mono">Publish →</span>
              </Link>

              <Link
                href="/debug"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white border border-border/60 transition-colors hover:border-amber-300 hover:bg-amber-50/50"
              >
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  <span className="text-text">Workflow Telemetry</span>
                </div>
                <span className="text-[10px] text-amber-800 font-mono">Debug Logs →</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}



function DocTypeIcon({ title }: { title: string }) {
  const filename = title.split("/").at(-1)?.toUpperCase() || "";
  if (filename.includes("README")) {
    return (
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-blue-500/10 text-blue-700 border border-blue-200/80">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      </div>
    );
  }
  if (filename.includes("ARCHITECTURE")) {
    return (
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-purple-500/10 text-purple-700 border border-purple-200/80">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      </div>
    );
  }
  if (filename.includes("CHANGELOG")) {
    return (
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-700 border border-emerald-200/80">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
    );
  }
  if (filename.includes("SECURITY")) {
    return (
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-rose-500/10 text-rose-700 border border-rose-200/80">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      </div>
    );
  }
  return (
    <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-800 border border-amber-200/80">
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: "bg-slate-100 text-slate-700 border-slate-300",
    pending_review: "bg-amber-100 text-amber-800 border-amber-300",
    approved: "bg-emerald-100 text-emerald-800 border-emerald-300",
    changes_requested: "bg-rose-100 text-rose-800 border-rose-300",
    published: "bg-blue-100 text-blue-800 border-blue-300",
  };
  return (
    <span
      className={`text-[11px] px-2.5 py-1 rounded-full font-extrabold uppercase tracking-wider border ${styles[status] || "bg-slate-100 text-slate-700 border-slate-300"
        }`}
    >
      {status.replace("_", " ")}
    </span>
  );
}
