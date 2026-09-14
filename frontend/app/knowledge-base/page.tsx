import KnowledgeBasePanel from "@/components/KnowledgeBasePanel";
import { AnimatedContainer, AnimatedItem } from "@/components/AnimatedItem";

export const dynamic = "force-dynamic";

export default function KnowledgeBasePage() {
  return (
    <AnimatedContainer className="space-y-6 py-2">
      {/* Hero / Header */}
      <AnimatedItem y={15}>
        <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal/10 text-teal border border-teal/20">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8-4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                  </svg>
                </div>
                <h1 className="text-xl font-bold tracking-tight text-text">
                  RAG Knowledge Base & Vector Index
                </h1>
              </div>
              <p className="text-xs text-muted max-w-2xl leading-relaxed pt-1">
                Manage pre-computed code chunk embeddings and vector store indices used by the{" "}
                <strong className="text-text">Understanding Agent</strong>. RAG embeddings ensure document generation is grounded strictly in your real codebase context with zero cross-repository data leakage.
              </p>
            </div>

            <div className="flex items-center gap-2 self-start md:self-auto">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-teal/30 bg-teal/10 px-3 py-1 text-xs font-bold text-teal shadow-2xs">
                <span className="h-2 w-2 rounded-full bg-teal animate-pulse" />
                Vector Search Active
              </span>
            </div>
          </div>
        </div>
      </AnimatedItem>

      {/* Main Knowledge Base Management Panel */}
      <AnimatedItem y={20}>
        <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
          <KnowledgeBasePanel />
        </div>
      </AnimatedItem>

      {/* RAG Architecture Reference Card */}
      <AnimatedItem y={25}>
        <div className="rounded-2xl border border-border bg-canvas p-5 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-2">
            <svg className="w-4 h-4 text-teal" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            How RAG Embeddings Work in DocuBear
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-muted">
            <div className="rounded-xl border border-border bg-surface p-4 space-y-1">
              <span className="font-bold text-text block text-xs">1. Ingestion & Chunking</span>
              <p className="text-[11px] leading-relaxed">
                When a repository is bootstrapped, code files are chunked semantically and embedded into vector spaces.
              </p>
            </div>
            <div className="rounded-xl border border-border bg-surface p-4 space-y-1">
              <span className="font-bold text-text block text-xs">2. Namespace Isolation</span>
              <p className="text-[11px] leading-relaxed">
                Embeddings are strictly scoped by repository name to guarantee complete data isolation between projects.
              </p>
            </div>
            <div className="rounded-xl border border-border bg-surface p-4 space-y-1">
              <span className="font-bold text-text block text-xs">3. Agent Context Retrieval</span>
              <p className="text-[11px] leading-relaxed">
                Agents query the vector store to fetch exact code references when writing or revising documentation.
              </p>
            </div>
          </div>
        </div>
      </AnimatedItem>
    </AnimatedContainer>
  );
}
