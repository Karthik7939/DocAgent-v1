"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DocVersion } from "@/types";

export default function ReviewSidebar({ documents }: { documents: DocVersion[] }) {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [selectedRepo, setSelectedRepo] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Extract unique repository IDs
  const repos = useMemo(() => {
    const repoSet = new Set(documents.map((doc) => doc.repoId));
    return Array.from(repoSet).filter(Boolean);
  }, [documents]);

  // Filter documents by repo and search query
  const filteredDocs = useMemo(() => {
    return documents.filter((doc) => {
      const matchesRepo = selectedRepo === "all" || doc.repoId === selectedRepo;
      const matchesSearch =
        !searchQuery.trim() ||
        doc.title.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesRepo && matchesSearch;
    });
  }, [documents, selectedRepo, searchQuery]);

  const updatedCount = filteredDocs.filter((d) => d.hasChanges).length;

  // Helper for document-type visual badges & icons
  const getDocTypeInfo = (title: string) => {
    const filename = title.split("/").at(-1)?.toUpperCase() || "";
    if (filename.includes("README")) {
      return {
        label: "README",
        color: "bg-blue-500/10 text-blue-700 border-blue-200/80 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800",
        icon: (
          <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        ),
      };
    }
    if (filename.includes("ARCHITECTURE")) {
      return {
        label: "Architecture",
        color: "bg-purple-500/10 text-purple-700 border-purple-200/80 dark:bg-purple-950/40 dark:text-purple-300 dark:border-purple-800",
        icon: (
          <svg className="w-4 h-4 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        ),
      };
    }
    if (filename.includes("CHANGELOG")) {
      return {
        label: "Changelog",
        color: "bg-emerald-500/10 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800",
        icon: (
          <svg className="w-4 h-4 text-emerald-600 dark:text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      };
    }
    if (filename.includes("SECURITY")) {
      return {
        label: "Security",
        color: "bg-rose-500/10 text-rose-700 border-rose-200/80 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800",
        icon: (
          <svg className="w-4 h-4 text-rose-600 dark:text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
      };
    }
    return {
      label: "Doc File",
      color: "bg-amber-500/10 text-amber-800 border-amber-200/80 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800",
      icon: (
        <svg className="w-4 h-4 text-amber-700 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    };
  };

  return (
    <div
      className={`group relative flex flex-col h-[calc(100vh-6rem)] overflow-hidden rounded-2xl border border-border/80 bg-surface shadow-xl shadow-amber-900/5 transition-all duration-300 ease-in-out ${isCollapsed ? "w-[4.25rem]" : "w-[21rem]"
        }`}
    >
      {/* Top Gradient Accent Line */}
      <div className="h-1.5 w-full bg-gradient-to-r from-amber-600 via-accent to-amber-700 flex-shrink-0" />

      {/* Header & Controls Section */}
      <div className={`space-y-3.5 border-b border-border/70 flex-shrink-0 transition-all duration-300 ${isCollapsed ? "p-2.5 flex flex-col items-center justify-between" : "p-4.5"
        }`}>
        {/* Title & Live Status Badge + Toggle Button */}
        <div className={`flex items-center ${isCollapsed ? "flex-col gap-3 justify-center" : "justify-between gap-2"}`}>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent shadow-sm border border-accent/20">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            {!isCollapsed && (
              <div className="transition-opacity duration-300">
                <h2 className="text-base font-bold tracking-tight text-text">
                  Documentation Hub
                </h2>
                <p className="text-xs font-medium text-muted">
                  {filteredDocs.length} document{filteredDocs.length === 1 ? "" : "s"} indexed
                </p>
              </div>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {!isCollapsed && updatedCount > 0 && (
              <span className="relative inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-100/90 px-2.5 py-1 text-[11px] font-bold text-amber-800 shadow-2xs">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
                </span>
                {updatedCount} Updated
              </span>
            )}

            {/* Smooth Collapse / Expand Toggle Button */}
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-border bg-white text-muted hover:bg-accent-soft hover:text-accent transition-all duration-200 shadow-2xs"
              title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <svg
                className={`w-4 h-4 transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""
                  }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>
        </div>

        {/* Search Input & Project Filter (Hidden when collapsed) */}
        {!isCollapsed && (
          <div className="space-y-3 transition-opacity duration-300">
            {/* Live Search Input */}
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-muted">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder="Search documentation files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-border bg-white/90 py-2 pl-9 pr-8 text-xs font-medium text-text placeholder-muted/70 transition-all focus:border-accent focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-muted hover:text-text"
                  title="Clear search"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            {/* Project Selector Filter */}
            {repos.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs font-medium text-muted">
                  <span className="flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    Select Repository
                  </span>
                  {selectedRepo !== "all" && (
                    <button
                      onClick={() => setSelectedRepo("all")}
                      className="text-[11px] text-accent hover:underline font-semibold"
                    >
                      Show All
                    </button>
                  )}
                </div>
                <select
                  id="repo-filter"
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="w-full rounded-xl border border-border bg-white/90 px-3 py-2 text-xs font-semibold text-text transition-all focus:border-accent focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  <option value="all">⚡ All Repositories ({documents.length})</option>
                  {repos.map((repo) => (
                    <option key={repo} value={repo}>
                      📦 {repo}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Document List Area */}
      <div className={`flex-1 overflow-y-auto ${isCollapsed ? "p-1.5 space-y-2 flex flex-col items-center" : "p-2.5 space-y-2"}`}>
        {filteredDocs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full p-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-100/60 text-amber-700 mb-2">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            {!isCollapsed && (
              <>
                <p className="text-xs font-bold text-text">No matching docs</p>
                <p className="mt-1 text-[11px] text-muted">Clear query or filter.</p>
              </>
            )}
          </div>
        ) : (
          <nav className="space-y-2 w-full">
            {filteredDocs.map((document) => {
              const isActive = pathname === `/review/${document.id}`;
              const docInfo = getDocTypeInfo(document.title);
              const fileName = document.title.split("/").at(-1) || document.title;
              const folderPath = document.title.split("/").slice(0, -1).join("/") || "root";

              if (isCollapsed) {
                return (
                  <Link
                    key={document.id}
                    href={`/review/${document.id}`}
                    className={`group relative flex items-center justify-center rounded-xl p-2 transition-all duration-200 ${isActive
                        ? "bg-white ring-2 ring-accent text-accent shadow-md"
                        : "hover:bg-accent-soft text-text/80 hover:text-text"
                      }`}
                    title={`${fileName} (${folderPath})`}
                  >
                    <div className={`flex h-9 w-9 items-center justify-center rounded-xl border shadow-2xs ${docInfo.color}`}>
                      {docInfo.icon}
                    </div>

                    {document.hasChanges && (
                      <span className="absolute top-1 right-1 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-white" />
                    )}
                  </Link>
                );
              }

              return (
                <Link
                  key={document.id}
                  href={`/review/${document.id}`}
                  className={`group relative flex items-start gap-3 rounded-xl p-3 text-xs transition-all duration-200 ${isActive
                      ? "bg-white shadow-md shadow-amber-900/10 ring-1 ring-accent/40 text-text"
                      : "hover:bg-accent-soft/70 text-text/90 hover:text-text border border-transparent hover:border-border/60"
                    }`}
                  title={document.title}
                >
                  {/* Active Bar Indicator */}
                  {isActive && (
                    <span className="absolute left-0 top-2.5 bottom-2.5 w-1.5 rounded-r-full bg-accent" />
                  )}

                  {/* File Icon Badge */}
                  <div className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border shadow-2xs transition-transform group-hover:scale-105 ${docInfo.color}`}>
                    {docInfo.icon}
                  </div>

                  {/* File Details */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1.5">
                      <span className={`truncate ${isActive ? "font-bold text-accent text-sm" : "font-semibold text-text text-xs"}`}>
                        {fileName}
                      </span>
                      {document.hasChanges && (
                        <span className="flex-shrink-0 inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-amber-800 shadow-2xs">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                          New
                        </span>
                      )}
                    </div>

                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted">
                      <span className="truncate font-mono opacity-80">{folderPath}</span>
                      <span className="font-mono text-[9px] font-semibold uppercase tracking-wider opacity-70">
                        {docInfo.label}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </nav>
        )}
      </div>

      {/* Footer Info */}
      <div className={`border-t border-border/70 bg-surface/80 px-3 py-3 flex items-center justify-between text-xs text-muted font-semibold flex-shrink-0 ${isCollapsed ? "flex-col gap-2 justify-center" : ""
        }`}>
        {!isCollapsed && (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-accent" />
            DocAgent
          </span>
        )}
        <span className={`inline-flex items-center gap-1 text-[10px] font-bold text-emerald-800 bg-emerald-100/90 px-2.5 py-0.5 rounded-full border border-emerald-300 ${isCollapsed ? "px-1.5 py-1" : ""
          }`}>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {!isCollapsed && "Live Synced"}
        </span>
      </div>
    </div>
  );
}
