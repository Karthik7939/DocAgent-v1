"use client";

import { useState } from "react";
import Link from "next/link";

interface ApprovalActionsProps {
  docId: string;
  onApprove?: () => void;
  onRevise?: (revisedDoc: any) => void;
}

export default function ApprovalActions({
  docId,
  onApprove,
  onRevise,
}: ApprovalActionsProps) {
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");

  async function handleApprove() {
    setLoading(true);
    setLoadingText("Approving document...");
    try {
      await fetch("/api/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId }),
      });
      if (onApprove) onApprove();
    } catch (err) {
      console.error("Approve failed:", err);
    } finally {
      setLoading(false);
      setLoadingText("");
    }
  }

  async function handleRequestChanges() {
    if (!comment.trim()) return;
    setLoading(true);
    setLoadingText("Agent is revising documentation based on your request...");
    try {
      const res = await fetch("/api/reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId, comment }),
      });
      const data = await res.json();
      if (onRevise) onRevise(data);
      setShowComment(false);
      setComment("");
    } catch (err) {
      console.error("Request changes failed:", err);
    } finally {
      setLoading(false);
      setLoadingText("");
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {loading ? (
        <div className="flex items-center gap-3 py-1 text-sm font-medium text-amber-700">
          <svg className="w-4 h-4 animate-spin text-amber-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span>{loadingText}</span>
        </div>
      ) : !showComment ? (
        <div className="flex flex-wrap gap-3 items-center">
          {/* 1. Approve Button */}
          <button
            id="btn-approve"
            onClick={handleApprove}
            disabled={loading}
            className="bg-emerald-700 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-emerald-800 transition-colors disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Approve
          </button>

          {/* 2. Publish to GitBook Button */}
          <Link
            id="btn-gitbook-redirect"
            href="/gitbook"
            className="inline-flex items-center gap-1.5 border border-blue-300 bg-blue-50 text-blue-800 text-sm font-medium px-4 py-2 rounded-md hover:bg-blue-100 transition-colors shadow-sm"
          >
            <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Publish to GitBook
          </Link>

          {/* 3. Request Changes Button */}
          <button
            id="btn-request-changes"
            onClick={() => setShowComment(true)}
            disabled={loading}
            className="border border-border text-sm font-medium px-4 py-2 rounded-md hover:bg-accent-soft transition-colors text-text shadow-sm"
          >
            Request changes
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block text-xs font-semibold text-text">
            Specify changes for Revision Agent:
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Describe what needs to be changed in the documentation (e.g. 'Add setup instructions for Docker', 'Update API endpoint details'...)"
            rows={3}
            className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-soft font-sans"
          />
          <div className="flex gap-3">
            <button
              onClick={handleRequestChanges}
              disabled={loading || !comment.trim()}
              className="bg-accent text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-[#8f4d20] transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              Submit to Agent
            </button>
            <button
              onClick={() => setShowComment(false)}
              className="text-sm text-muted hover:text-text px-2 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

