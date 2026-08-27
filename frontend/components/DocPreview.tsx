"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DiffViewer from "./DiffViewer";
import MermaidDiagram from "./MermaidDiagram";

interface DocPreviewProps {
  docId: string;
  content: string;
  previousContent?: string;
  onSave?: (updatedDoc: any) => void;
}

type Tab = "preview" | "edit" | "changes";

export default function DocPreview({
  docId,
  content,
  previousContent,
  onSave,
}: DocPreviewProps) {
  const hasChanges = Boolean(previousContent);
  const [activeTab, setActiveTab] = useState<Tab>("preview");
  const [editableContent, setEditableContent] = useState<string>(content);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveMessage, setSaveMessage] = useState<string>("");

  const isDirty = editableContent !== content;
  const lineCount = editableContent.split("\n").length;

  const handleSaveEdits = async () => {
    setIsSaving(true);
    setSaveMessage("");
    try {
      const res = await fetch("/api/docs/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId, content: editableContent }),
      });
      if (res.ok) {
        const updatedDoc = await res.json();
        setSaveMessage("Edits saved successfully!");
        if (onSave) onSave(updatedDoc);
        setTimeout(() => setSaveMessage(""), 3000);
      } else {
        setSaveMessage("Error saving edits.");
      }
    } catch (err) {
      console.error("Save failed:", err);
      setSaveMessage("Error saving edits.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDiscard = () => {
    setEditableContent(content);
  };

  return (
    <div className="rounded-2xl border border-border overflow-hidden bg-surface shadow-sm">
      {/* Tab bar — Presidio off-white canvas header */}
      <div className="flex flex-wrap items-center justify-between border-b border-border bg-canvas px-4 pt-3 gap-2">
        <div className="flex items-center gap-2">
          {/* Preview Tab */}
          <TabButton
            id="tab-preview"
            label="Formatted Preview"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            }
            active={activeTab === "preview"}
            onClick={() => setActiveTab("preview")}
          />

          {/* Edit (Manual) Tab */}
          <TabButton
            id="tab-edit"
            label="Edit Specification"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            }
            badge={isDirty ? "Unsaved" : undefined}
            active={activeTab === "edit"}
            onClick={() => {
              setEditableContent(content);
              setActiveTab("edit");
            }}
          />

          {/* Changes / Diff Tab */}
          {hasChanges && (
            <TabButton
              id="tab-changes"
              label="Diff Viewer"
              icon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
              }
              badge="Updated"
              active={activeTab === "changes"}
              onClick={() => setActiveTab("changes")}
            />
          )}
        </div>

        {/* Action controls when in Edit tab */}
        {activeTab === "edit" && (
          <div className="flex items-center gap-3 pb-2.5 text-xs">
            {saveMessage && (
              <span className="text-xs font-semibold text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
                {saveMessage}
              </span>
            )}
            {isDirty && (
              <button
                onClick={handleDiscard}
                className="text-xs font-semibold uppercase tracking-wider text-muted hover:text-text px-3 py-1.5 transition-colors"
              >
                Discard
              </button>
            )}
            <button
              onClick={handleSaveEdits}
              disabled={isSaving || !isDirty}
              className="bg-accent-cta text-text text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-full hover:bg-yellow-300 transition-all disabled:opacity-40 flex items-center gap-1.5 shadow-xs"
            >
              {isSaving ? "Saving..." : "Save Edits"}
            </button>
          </div>
        )}
      </div>

      {/* Tab content area */}
      <div className="bg-surface">
        {activeTab === "preview" && (
          <div className="p-6 sm:p-10">
            <div className="prose prose-slate max-w-none prose-headings:font-bold prose-headings:text-text prose-a:text-teal prose-code:text-teal prose-code:bg-teal/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-pre:bg-text prose-pre:text-white prose-pre:rounded-xl">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  pre({ children }: any) {
                    // A mermaid code block (see `code` override below) renders
                    // its own light card via MermaidDiagram, marked with the
                    // `mermaid-diagram-card` class. `has-[]` strips this <pre>'s
                    // own dark code-box styling when it contains one, so the
                    // diagram isn't nested inside a code box. (Detecting this
                    // from `children`'s element type in JS was unreliable
                    // across react-markdown's render passes — CSS sidesteps
                    // that entirely.)
                    return (
                      <pre className="has-[.mermaid-diagram-card]:bg-transparent has-[.mermaid-diagram-card]:p-0 has-[.mermaid-diagram-card]:border-0 has-[.mermaid-diagram-card]:shadow-none has-[.mermaid-diagram-card]:my-0 bg-text text-white p-4.5 rounded-xl overflow-x-auto font-mono text-xs shadow-sm border border-border/40 my-4">
                        {children}
                      </pre>
                    );
                  },
                  code({ node, inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || "");
                    if (match && match[1] === "mermaid") {
                      const chart = String(children).replace(/\n$/, "");
                      return <MermaidDiagram chart={chart} />;
                    }
                    if (inline || (!match && !className)) {
                      return (
                        <code className="bg-teal/10 text-teal font-mono text-[13px] px-1.5 py-0.5 rounded border border-teal/20" {...props}>
                          {children}
                        </code>
                      );
                    }
                    return (
                      <code className={`${className || ""} font-mono text-xs`} {...props}>
                        {children}
                      </code>
                    );
                  },
                  blockquote({ children }: any) {
                    return (
                      <blockquote className="border-l-4 border-teal bg-teal/5 pl-4 py-2 pr-2 my-4 rounded-r-xl text-text font-medium italic">
                        {children}
                      </blockquote>
                    );
                  },
                  table({ children }: any) {
                    return (
                      <div className="overflow-x-auto my-4 rounded-xl border border-border">
                        <table className="w-full text-left border-collapse text-xs">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }: any) {
                    return (
                      <th className="bg-canvas border-b border-border px-4 py-2.5 font-bold text-text uppercase tracking-wider text-[11px]">
                        {children}
                      </th>
                    );
                  },
                  td({ children }: any) {
                    return (
                      <td className="border-b border-border/60 px-4 py-2 text-text/90">
                        {children}
                      </td>
                    );
                  },
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {activeTab === "edit" && (
          <div className="p-5 space-y-4 bg-canvas/40">
            <div className="flex items-center justify-between text-xs text-muted font-mono px-1">
              <span>Markdown Code Editor — Type, edit, or remove documentation text below:</span>
              <span className="font-semibold text-text">{lineCount} lines</span>
            </div>

            <div className="relative flex rounded-xl border border-border bg-surface overflow-hidden shadow-xs">
              {/* Line Numbers Column */}
              <div className="select-none py-3.5 px-3 bg-canvas border-r border-border text-right font-mono text-xs text-muted/60 min-w-[3rem]">
                {Array.from({ length: lineCount }).map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>

              {/* Textarea Editor */}
              <textarea
                value={editableContent}
                onChange={(e) => setEditableContent(e.target.value)}
                placeholder="Enter markdown content..."
                rows={Math.max(16, lineCount + 2)}
                className="w-full p-3.5 font-mono text-xs text-text leading-relaxed bg-transparent focus:outline-none resize-y"
                spellCheck={false}
              />
            </div>
          </div>
        )}

        {activeTab === "changes" && hasChanges && (
          <div className="p-6">
            <DiffViewer oldText={previousContent!} newText={content} />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab button
// ---------------------------------------------------------------------------

function TabButton({
  id,
  label,
  icon,
  badge,
  active,
  onClick,
}: {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      id={id}
      onClick={onClick}
      className={`
        relative flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider rounded-t-xl
        transition-all duration-200 select-none
        ${
          active
            ? "bg-surface text-teal border-t border-x border-border border-b-surface -mb-px z-10 shadow-2xs"
            : "text-muted hover:text-text hover:bg-surface/60"
        }
      `}
    >
      <span className={active ? "text-teal" : "opacity-60"}>{icon}</span>
      {label}
      {badge && (
        <span className={`ml-1 inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${
          active ? "bg-yellow-100 text-yellow-800 border border-yellow-300" : "bg-border text-muted"
        }`}>
          {badge}
        </span>
      )}
    </button>
  );
}
