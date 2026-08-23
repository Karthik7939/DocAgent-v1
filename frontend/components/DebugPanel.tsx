"use client";

import { useEffect, useState } from "react";

type Snapshot = {
  backend: { status: string };
  indexes: { vector: number; keyword: number };
  workflow: Record<string, unknown>;
  logs: string[];
  recent_workflows: Array<{ workflow_id?: string; repository?: string; status?: string; timestamp?: string }>;
};

const emptySnapshot: Snapshot = {
  backend: { status: "connecting" },
  indexes: { vector: 0, keyword: 0 },
  workflow: {},
  logs: [],
  recent_workflows: [],
};

export default function DebugPanel() {
  const [snapshot, setSnapshot] = useState<Snapshot>(emptySnapshot);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/debug", { cache: "no-store" });
        const data = await response.json();
        if (mounted) {
          setSnapshot(data);
          setUpdatedAt(new Date());
        }
      } catch {
        if (mounted) setSnapshot((current) => ({ ...current, backend: { status: "offline" } }));
      }
    };

    refresh();
    const interval = window.setInterval(refresh, 2000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const workflow = snapshot.workflow;
  const query = (workflow.semantic_query as Record<string, unknown> | undefined) ?? {};
  const astDetails = (workflow.ast_details as Array<Record<string, unknown>> | undefined) ?? [];
  const chunks = (workflow.retrieved_chunks as Array<Record<string, unknown>> | undefined) ?? [];
  const isHealthy = snapshot.backend.status === "healthy";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">RAG debugging</h1>
          <p className="mt-1 text-sm text-muted">Live pipeline telemetry refreshes every 2 seconds.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${isHealthy ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
          {isHealthy ? "Backend connected" : "Backend disconnected"}
        </span>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Vector chunks" value={snapshot.indexes.vector} />
        <Metric label="Keyword chunks" value={snapshot.indexes.keyword} />
        <Metric label="RAG progress" value={`${workflow.rag_progress ?? 0}%`} />
        <Metric label="Retrieved chunks" value={chunks.length} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Panel title="Active commit flow">
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <Detail label="Repository" value={String(workflow.repository ?? "Waiting for a commit")} />
            <Detail label="Status" value={String(workflow.status ?? "idle")} />
            <Detail label="Stage" value={String(workflow.rag_stage ?? "queued")} />
            <Detail label="Current file" value={String(workflow.rag_current_file ?? "—")} />
            <Detail label="Commit" value={String(workflow.commit_sha ?? "—")} />
            <Detail label="Changed files" value={String((workflow.changed_files as string[] | undefined)?.length ?? 0)} />
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-accent-soft">
            <div className="h-full bg-accent transition-all" style={{ width: `${Number(workflow.rag_progress ?? 0)}%` }} />
          </div>
        </Panel>

        <Panel title="Recent workflows">
          <div className="space-y-2">
            {snapshot.recent_workflows.map((item) => (
              <div key={item.workflow_id} className="rounded border border-border px-2.5 py-2 text-xs">
                <p className="truncate font-medium">{item.repository}</p>
                <p className="mt-0.5 text-muted">{item.status} · {item.timestamp}</p>
              </div>
            ))}
            {!snapshot.recent_workflows.length && <p className="text-sm text-muted">No workflows recorded.</p>}
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Panel title="Generated retrieval query">
          {query.query_text ? <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-canvas p-3 text-xs leading-5">{String(query.query_text)}</pre> : <Empty text="Available after the next commit is processed." />}
          {!!(query.keywords as string[] | undefined)?.length && <p className="mt-3 text-xs text-muted">Keywords: {(query.keywords as string[]).join(", ")}</p>}
        </Panel>
        <Panel title="AST analysis">
          {astDetails.length ? <div className="space-y-2">{astDetails.map((item) => <div key={String(item.file_path)} className="rounded bg-canvas p-3 text-xs"><p className="font-medium">{String(item.file_path)}</p><p className="mt-1 text-muted">{String(item.language)} · {String(item.change_type)} · symbols: {((item.symbols as string[] | undefined) ?? []).join(", ") || "none"}</p></div>)}</div> : <Empty text="AST details are captured with the next incremental run." />}
        </Panel>
      </section>

      <Panel title="Retrieved chunks">
        {chunks.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="border-b border-border text-muted"><tr><th className="p-2">#</th><th className="p-2">File</th><th className="p-2">Symbol</th><th className="p-2">Source</th><th className="p-2">Score</th></tr></thead><tbody>{chunks.map((chunk) => <tr key={String(chunk.chunk_id)} className="border-b border-border/70"><td className="p-2">{String(chunk.rank)}</td><td className="max-w-72 truncate p-2">{String(chunk.file_path)}</td><td className="p-2">{String(chunk.symbol_name ?? "—")}</td><td className="p-2">{String(chunk.source)}</td><td className="p-2">{Number(chunk.score ?? 0).toFixed(3)}</td></tr>)}</tbody></table></div> : <Empty text="No retrieval result is stored for this workflow yet." />}
      </Panel>

      <Panel title="Live pipeline logs">
        <pre className="max-h-80 overflow-auto rounded bg-[#2f261d] p-4 text-xs leading-5 text-[#f8f1e3]">{snapshot.logs.length ? snapshot.logs.join("\n") : "Waiting for pipeline log events…"}</pre>
        {updatedAt && <p className="mt-2 text-right text-xs text-muted">Updated {updatedAt.toLocaleTimeString()}</p>}
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-lg border border-border bg-surface p-4"><h2 className="mb-3 text-sm font-semibold">{title}</h2>{children}</section>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-lg border border-border bg-surface p-3"><p className="text-xs text-muted">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-muted">{label}</p><p className="mt-0.5 truncate font-medium" title={value}>{value}</p></div>;
}

function Empty({ text }: { text: string }) {
  return <p className="rounded bg-canvas p-3 text-sm text-muted">{text}</p>;
}
