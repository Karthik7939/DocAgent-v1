export default function ReviewIndexPage() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center">
      <h1 className="text-lg font-semibold">Choose a document to review</h1>
      <p className="mt-2 text-sm text-muted">
        Select a generated document from the sidebar to view its formatted Markdown.
      </p>
    </div>
  );
}
