"use client";

import { useState } from "react";
import DocPreview from "@/components/DocPreview";
import ApprovalActions from "@/components/ApprovalActions";
import { DiffSummary } from "@/components/DiffViewer";
import { DocVersion } from "@/types";

export default function DocReviewClient({ initialDoc }: { initialDoc: DocVersion }) {
  const [doc, setDoc] = useState<DocVersion>(initialDoc);

  const handleApprove = () => {
    setDoc((prev) => ({
      ...prev,
      previousContent: undefined,
      hasChanges: false,
      status: "approved",
    }));
  };

  const handleRevise = (updatedDoc: any) => {
    if (updatedDoc && updatedDoc.content) {
      setDoc((prev) => ({
        ...prev,
        content: updatedDoc.content,
        previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.content,
        hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent),
        status: "changes_requested",
      }));
    }
  };

  const handleSave = (updatedDoc: any) => {
    if (updatedDoc && updatedDoc.content) {
      setDoc((prev) => ({
        ...prev,
        content: updatedDoc.content,
        previousContent: updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent,
        hasChanges: Boolean(updatedDoc.previous_content || updatedDoc.previousContent || prev.previousContent),
      }));
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <div className="flex flex-wrap items-start gap-3">
          <h1 className="text-xl font-semibold">{doc.title.split("/").at(-1)}</h1>
          {doc.previousContent && (
            <span className="mt-0.5">
              <DiffSummary oldText={doc.previousContent} newText={doc.content} />
            </span>
          )}
        </div>
        <p className="mt-1 break-words text-sm text-muted">{doc.title}</p>
        <p className="mt-1 text-xs text-muted">
          Generated {new Date(doc.createdAt).toLocaleString()}
          {doc.previousContent ? (
            <span className="ml-2 inline-flex items-center gap-1 text-amber-700 font-medium">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              Updated since last version (Diff mode)
            </span>
          ) : (
            <span className="ml-2 inline-flex items-center gap-1 text-emerald-700 font-medium">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              Approved (Final version)
            </span>
          )}
        </p>
      </div>

      <ApprovalActions
        docId={doc.id}
        onApprove={handleApprove}
        onRevise={handleRevise}
      />

      {/* Tabbed preview / manual editor / diff viewer */}
      <DocPreview
        key={`${doc.id}-${doc.previousContent ? 'diff' : 'clean'}-${doc.content.length}`}
        docId={doc.id}
        content={doc.content}
        previousContent={doc.previousContent}
        onSave={handleSave}
      />
    </div>
  );

}
