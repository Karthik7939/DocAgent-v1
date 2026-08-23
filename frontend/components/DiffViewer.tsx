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
    // diffLines may leave an empty string at the end from a trailing newline
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
  // Mark which indices are "near" a change (within CONTEXT_LINES)
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
      // Find the run of hidden unchanged lines
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
          <mark key={i} className="bg-emerald-200 text-emerald-900 rounded-sm px-0.5 not-italic">
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
          <mark key={i} className="bg-red-200 text-red-900 rounded-sm px-0.5 not-italic">
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
    <tr className="bg-emerald-50 hover:bg-emerald-100/70 transition-colors">
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-emerald-400 border-r border-emerald-200 font-mono">
        {entry.oldLineNum ?? ""}
      </td>
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-emerald-600 border-r border-emerald-200 font-mono">
        {entry.newLineNum}
      </td>
      <td className="select-none w-6 px-2 py-0.5 text-center text-[11px] text-emerald-500 font-mono font-bold">
        +
      </td>
      <td className="px-3 py-0.5 text-[12px] font-mono text-emerald-900 whitespace-pre-wrap break-all">
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
    <tr className="bg-red-50 hover:bg-red-100/70 transition-colors">
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-red-600 border-r border-red-200 font-mono">
        {entry.oldLineNum}
      </td>
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-red-400 border-r border-red-200 font-mono">
        {entry.newLineNum ?? ""}
      </td>
      <td className="select-none w-6 px-2 py-0.5 text-center text-[11px] text-red-500 font-mono font-bold">
        −
      </td>
      <td className="px-3 py-0.5 text-[12px] font-mono text-red-900 whitespace-pre-wrap break-all">
        {nextAdded ? (
          <WordDiffOld oldLine={entry.content} newLine={nextAdded.content} />
        ) : (
          <span className="line-through opacity-70">{entry.content}</span>
        )}
      </td>
    </tr>
  );
}

function UnchangedRow({ entry }: { entry: LineEntry }) {
  return (
    <tr className="hover:bg-gray-50/60 transition-colors">
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-[#7a6c5a]/50 border-r border-[#e7d7bc] font-mono">
        {entry.oldLineNum}
      </td>
      <td className="select-none w-10 px-3 py-0.5 text-right text-[11px] text-[#7a6c5a]/50 border-r border-[#e7d7bc] font-mono">
        {entry.newLineNum}
      </td>
      <td className="select-none w-6 px-2 py-0.5 text-center text-[11px] text-[#7a6c5a]/30 font-mono">
        {" "}
      </td>
      <td className="px-3 py-0.5 text-[12px] font-mono text-[#443729]/60 whitespace-pre-wrap break-all">
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
    <tr className="bg-[#f4dfc6]/40 border-y border-[#e7d7bc]">
      <td colSpan={4}>
        <button
          onClick={onExpand}
          className="w-full px-4 py-1.5 text-[11px] font-medium text-[#7a6c5a] hover:text-[#a85f2d] hover:bg-[#f4dfc6]/60 transition-colors text-left flex items-center gap-2"
        >
          <svg className="w-3.5 h-3.5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      {added > 0 && (
        <span className="inline-flex items-center gap-0.5 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
          <span className="font-bold">+{added}</span>
          <span className="opacity-70">lines</span>
        </span>
      )}
      {removed > 0 && (
        <span className="inline-flex items-center gap-0.5 text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
          <span className="font-bold">−{removed}</span>
          <span className="opacity-70">lines</span>
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

  // Rebuild display entries based on which hunks have been expanded
  const displayEntries: DisplayEntry[] = [];
  const baseDisplay = buildDisplayEntries(allLines);

  for (const entry of baseDisplay) {
    if (entry.type === "hunk") {
      if (expandedHunks.has(entry.startIdx)) {
        // Render the hidden lines inline
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
      <div className="rounded-lg border border-[#e7d7bc] bg-[#fffdf6] px-5 py-6 text-center text-sm text-[#7a6c5a]">
        No changes detected between versions.
      </div>
    );
  }

  // Build a lookup of removed→next-added and added→prev-removed for word-level diff
  const lineEntries = displayEntries.filter((e): e is LineEntry => e.type !== "hunk");
  const removedToNextAdded = new Map<number, LineEntry>();
  const addedToPrevRemoved = new Map<number, LineEntry>();
  for (let i = 0; i < lineEntries.length; i++) {
    if (lineEntries[i].type === "removed" && i + 1 < lineEntries.length && lineEntries[i + 1].type === "added") {
      removedToNextAdded.set(i, lineEntries[i + 1]);
      addedToPrevRemoved.set(i + 1, lineEntries[i]);
    }
  }

  // Map display index in lineEntries to the original idx for lookup
  let lineIdx = 0;

  return (
    <div className="rounded-lg border border-[#e7d7bc] overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#f8f1e3] border-b border-[#e7d7bc]">
        <div className="flex items-center gap-3 text-[11px] font-semibold text-[#7a6c5a] uppercase tracking-wider">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-red-400/80 inline-block" />
            Previous
          </span>
          <span className="opacity-30">→</span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-400/80 inline-block" />
            Current
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