"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DiffViewer from "./DiffViewer";

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
  const [activeTab, setActiveTab] = useState<Tab>(hasChanges ? "changes" : "preview");
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
    <div className="rounded-lg border border-[#e7d7bc] overflow-hidden bg-[#fffdf6] shadow-sm">
      {/* Tab strip */}
      <div className="flex items-center justify-between border-b border-[#e7d7bc] bg-[#f8f1e3] px-1 pt-1">
        <div className="flex items-center gap-0.5">
          {/* Preview Tab */}
          <TabButton
            id="tab-preview"
            label="Preview"
            icon={
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
            label="Edit (Manual)"
            icon={
              <svg className="w-3.5 h-3.5 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
              label="Changes"
              icon={
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
          <div className="flex items-center gap-2 pr-2 pb-1 text-xs">
            {saveMessage && (
              <span className="text-xs font-semibold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-300">
                {saveMessage}
              </span>
            )}
            {isDirty && (
              <button
                onClick={handleDiscard}
                className="text-muted hover:text-text px-2 py-1 font-medium transition-colors"
              >
                Discard
              </button>
            )}
            <button
              onClick={handleSaveEdits}
              disabled={isSaving || !isDirty}
              className="bg-accent text-white text-xs font-bold px-3 py-1 rounded-md hover:bg-[#8f4d20] transition-colors disabled:opacity-40 flex items-center gap-1 shadow-2xs"
            >
              {isSaving ? "Saving..." : "Save Edits"}
            </button>
          </div>
        )}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "preview" && (
          <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-a:text-[#a85f2d] p-5 sm:p-6">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}

        {activeTab === "edit" && (
          <div className="p-4 space-y-3 bg-[#fdfbf7]">
            <div className="flex items-center justify-between text-xs text-muted font-mono px-1">
              <span>Markdown Code Editor — Type, edit, or remove documentation text below:</span>
              <span>{lineCount} lines</span>
            </div>

            <div className="relative flex rounded-lg border border-[#e7d7bc] bg-white overflow-hidden shadow-inner">
              {/* Line Numbers Column */}
              <div className="select-none py-3 px-2 bg-[#f8f1e3]/60 border-r border-[#e7d7bc] text-right font-mono text-xs text-[#7a6c5a]/60 min-w-[2.5rem]">
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
                className="w-full p-3 font-mono text-xs text-[#3d3124] leading-relaxed bg-transparent focus:outline-none resize-y"
                spellCheck={false}
              />
            </div>
          </div>
        )}

        {activeTab === "changes" && hasChanges && (
          <div className="p-4">
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
        relative flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-t-md
        transition-colors duration-150 select-none
        ${
          active
            ? "bg-[#fffdf6] text-[#443729] border border-[#e7d7bc] border-b-[#fffdf6] -mb-px z-10"
            : "text-[#7a6c5a] hover:text-[#443729] hover:bg-[#f4dfc6]/40"
        }
      `}
    >
      <span className={active ? "text-[#a85f2d]" : "opacity-60"}>{icon}</span>
      {label}
      {badge && (
        <span className="ml-0.5 inline-flex items-center rounded-full bg-amber-100 border border-amber-300 px-1.5 py-0 text-[10px] font-semibold text-amber-700">
          {badge}
        </span>
      )}
    </button>
  );
}
