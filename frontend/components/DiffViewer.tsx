"use client";

import { diffLines, diffWords, Change } from "diff";
import { useState } from "react";

// Number of unchanged lines to show above/below a change block as context
const CONTEXT_LINES = 3;

interface LineEntry {
  type: "added" | "removed" | "unchanged";
  oldLineNum: number | null;
  newLineNum: number | null;
  content: string;
}

interface HunkEntry {
  type: "hunk";
  hiddenCount: number;
  startIdx: number; // index in flatLines array where collapsed lines start
}

type DisplayEntry = LineEntry | HunkEntry;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildLineEntries(oldText: string, newText: string): LineEntry[] {
  const changes: Change[] = diffLines(oldText || "", newText || "");
  const entries: LineEntry[] = [];
  let oldLineNum = 1;
  let newLineNum = 1;

  for (const change of changes) {
    const lines = change.value.split("\n");
    if (lines[lines.length - 1] === "") lines.pop();

    for (const line of lines) {
      if (change.added) {
        entries.push({ type: "added", oldLineNum: null, newLineNum: newLineNum++, content: line });
      } else if (change.removed) {
        entries.push({ type: "removed", oldLineNum: oldLineNum++, newLineNum: null, content: line });
      } else {
        entries.push({ type: "unchanged", oldLineNum: oldLineNum++, newLineNum: newLineNum++, content: line });
      }
    }
  }
  return entries;
}

function buildDisplayEntries(lines: LineEntry[]): DisplayEntry[] {
  const near = new Set<number>();
  lines.forEach((l, i) => {
    if (l.type !== "unchanged") {
      for (let d = -CONTEXT_LINES; d <= CONTEXT_LINES; d++) {
        const idx = i + d;
        if (idx >= 0 && idx < lines.length) near.add(idx);
      }
    }
  });

  const result: DisplayEntry[] = [];
  let i = 0;
  while (i < lines.length) {
    if (near.has(i) || lines[i].type !== "unchanged") {
      result.push(lines[i]);
      i++;
    } else {
      let j = i;
      while (j < lines.length && !near.has(j) && lines[j].type === "unchanged") j++;
      const hiddenCount = j - i;
      if (hiddenCount > 0) {
        result.push({ type: "hunk", hiddenCount, startIdx: i });
      }
      i = j;
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Word-level inline diff for a single line pair
// ---------------------------------------------------------------------------

function WordDiff({ oldLine, newLine }: { oldLine: string; newLine: string }) {
  const parts = diffWords(oldLine, newLine);
  return (
    <>
      {parts.map((part, i) =>
        part.added ? (
          <mark key={i} className="bg-emerald-200/80 text-emerald-950 rounded-xs px-0.5 font-semibold not-italic">
            {part.value}
          </mark>
        ) : part.removed ? null : (
          <span key={i}>{part.value}</span>
        )
      )}
    </>
  );
}

function WordDiffOld({ oldLine, newLine }: { oldLine: string; newLine: string }) {
  const parts = diffWords(oldLine, newLine);
  return (
    <>
      {parts.map((part, i) =>
        part.removed ? (
          <mark key={i} className="bg-rose-200/80 text-rose-950 rounded-xs px-0.5 font-semibold not-italic">
            {part.value}
          </mark>
        ) : part.added ? null : (
          <span key={i}>{part.value}</span>
        )
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Individual row components
// ---------------------------------------------------------------------------

function AddedRow({
  entry,
  prevRemoved,
}: {
  entry: LineEntry;
  prevRemoved: LineEntry | null;
}) {
  return (
    <tr className="bg-emerald-50/70 hover:bg-emerald-100/60 transition-colors">
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-emerald-600/50 border-r border-emerald-200/70 font-mono">
        {entry.oldLineNum ?? ""}
      </td>
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-emerald-700 font-mono font-bold border-r border-emerald-200/70">
        {entry.newLineNum}
      </td>
      <td className="select-none w-6 px-2 py-1 text-center text-[11px] text-emerald-600 font-mono font-bold border-r border-emerald-200/70">
        +
      </td>
      <td className="px-3.5 py-1 text-xs font-mono text-emerald-950 whitespace-pre-wrap break-all leading-relaxed">
        {prevRemoved ? (
          <WordDiff oldLine={prevRemoved.content} newLine={entry.content} />
        ) : (
          entry.content
        )}
      </td>
    </tr>
  );
}

function RemovedRow({ entry, nextAdded }: { entry: LineEntry; nextAdded: LineEntry | null }) {
  return (
    <tr className="bg-rose-50/70 hover:bg-rose-100/60 transition-colors">
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-rose-700 font-mono font-bold border-r border-rose-200/70">
        {entry.oldLineNum}
      </td>
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-rose-600/50 border-r border-rose-200/70 font-mono">
        {entry.newLineNum ?? ""}
      </td>
      <td className="select-none w-6 px-2 py-1 text-center text-[11px] text-rose-600 font-mono font-bold border-r border-rose-200/70">
        −
      </td>
      <td className="px-3.5 py-1 text-xs font-mono text-rose-950 whitespace-pre-wrap break-all leading-relaxed">
        {nextAdded ? (
          <WordDiffOld oldLine={entry.content} newLine={nextAdded.content} />
        ) : (
          <span className="line-through opacity-75">{entry.content}</span>
        )}
      </td>
    </tr>
  );
}

function UnchangedRow({ entry }: { entry: LineEntry }) {
  return (
    <tr className="hover:bg-canvas/60 transition-colors">
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-muted/60 border-r border-border font-mono">
        {entry.oldLineNum}
      </td>
      <td className="select-none w-10 px-3 py-1 text-right text-[11px] text-muted/60 border-r border-border font-mono">
        {entry.newLineNum}
      </td>
      <td className="select-none w-6 px-2 py-1 text-center text-[11px] text-muted/30 font-mono border-r border-border">
        {" "}
      </td>
      <td className="px-3.5 py-1 text-xs font-mono text-text/80 whitespace-pre-wrap break-all leading-relaxed">
        {entry.content}
      </td>
    </tr>
  );
}

function HunkRow({
  entry,
  onExpand,
}: {
  entry: HunkEntry;
  onExpand: () => void;
}) {
  return (
    <tr className="bg-canvas border-y border-border">
      <td colSpan={4}>
        <button
          onClick={onExpand}
          className="w-full px-4 py-2 text-xs font-mono text-muted hover:text-teal hover:bg-surface transition-all text-left flex items-center gap-2"
        >
          <svg className="w-3.5 h-3.5 text-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          Show {entry.hiddenCount} unchanged line{entry.hiddenCount === 1 ? "" : "s"}
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Summary bar
// ---------------------------------------------------------------------------

export function DiffSummary({ oldText, newText }: { oldText: string; newText: string }) {
  const changes = diffLines(oldText || "", newText || "");
  let added = 0;
  let removed = 0;
  for (const c of changes) {
    const lineCount = c.value.split("\n").filter((l) => l !== "").length;
    if (c.added) added += lineCount;
    else if (c.removed) removed += lineCount;
  }
  if (added === 0 && removed === 0) return null;
  return (
    <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
      {added > 0 && (
        <span className="inline-flex items-center gap-1 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-0.5">
          <span>+{added}</span>
          <span className="text-[10px] opacity-80">lines</span>
        </span>
      )}
      {removed > 0 && (
        <span className="inline-flex items-center gap-1 text-rose-800 bg-rose-50 border border-rose-200 rounded-full px-3 py-0.5">
          <span>−{removed}</span>
          <span className="text-[10px] opacity-80">lines</span>
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main DiffViewer component
// ---------------------------------------------------------------------------

export default function DiffViewer({ oldText, newText }: { oldText: string; newText: string }) {
  const allLines = buildLineEntries(oldText, newText);
  const [expandedHunks, setExpandedHunks] = useState<Set<number>>(new Set());

  const displayEntries: DisplayEntry[] = [];
  const baseDisplay = buildDisplayEntries(allLines);

  for (const entry of baseDisplay) {
    if (entry.type === "hunk") {
      if (expandedHunks.has(entry.startIdx)) {
        const hidden = allLines.slice(entry.startIdx, entry.startIdx + entry.hiddenCount);
        displayEntries.push(...hidden);
      } else {
        displayEntries.push(entry);
      }
    } else {
      displayEntries.push(entry);
    }
  }

  if (allLines.every((l) => l.type === "unchanged")) {
    return (
      <div className="rounded-2xl border border-border bg-canvas px-6 py-8 text-center text-xs font-semibold text-muted uppercase tracking-wider">
        No changes detected between versions.
      </div>
    );
  }

  const lineEntries = displayEntries.filter((e): e is LineEntry => e.type !== "hunk");
  const removedToNextAdded = new Map<number, LineEntry>();
  const addedToPrevRemoved = new Map<number, LineEntry>();
  for (let i = 0; i < lineEntries.length; i++) {
    if (lineEntries[i].type === "removed" && i + 1 < lineEntries.length && lineEntries[i + 1].type === "added") {
      removedToNextAdded.set(i, lineEntries[i + 1]);
      addedToPrevRemoved.set(i + 1, lineEntries[i]);
    }
  }

  let lineIdx = 0;

  return (
    <div className="rounded-2xl border border-border overflow-hidden bg-surface shadow-xs">
      {/* Presidio Theme Diff Header */}
      <div className="flex flex-wrap items-center justify-between px-5 py-3.5 bg-canvas border-b border-border gap-2">
        <div className="flex items-center gap-3 text-xs font-bold text-text uppercase tracking-wider">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
            Previous Version
          </span>
          <span className="text-teal font-extrabold">→</span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
            Current Version
          </span>
        </div>
        <DiffSummary oldText={oldText} newText={newText} />
      </div>

      {/* Diff table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <colgroup>
            <col className="w-12" />
            <col className="w-12" />
            <col className="w-8" />
            <col />
          </colgroup>
          <tbody>
            {displayEntries.map((entry, dispIdx) => {
              if (entry.type === "hunk") {
                return (
                  <HunkRow
                    key={`hunk-${entry.startIdx}`}
                    entry={entry}
                    onExpand={() =>
                      setExpandedHunks((prev) => {
                        const next = new Set(prev);
                        next.add(entry.startIdx);
                        return next;
                      })
                    }
                  />
                );
              }

              const localIdx = lineIdx++;

              if (entry.type === "added") {
                return (
                  <AddedRow
                    key={`add-${dispIdx}`}
                    entry={entry}
                    prevRemoved={addedToPrevRemoved.get(localIdx) ?? null}
                  />
                );
              }
              if (entry.type === "removed") {
                return (
                  <RemovedRow
                    key={`rem-${dispIdx}`}
                    entry={entry}
                    nextAdded={removedToNextAdded.get(localIdx) ?? null}
                  />
                );
              }
              return <UnchangedRow key={`unc-${dispIdx}`} entry={entry} />;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}