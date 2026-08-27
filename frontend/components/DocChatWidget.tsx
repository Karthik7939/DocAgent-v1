"use client";

import { useEffect, useRef, useState, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MermaidDiagram from "./MermaidDiagram";

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

interface DocChatWidgetProps {
  /** Full repository name in "owner/repo" form. */
  repositoryName: string;
}

// Conversations are per-repository, not per-doc — the same chat should
// still be there when you navigate from README.md to ARCHITECTURE.md for
// the same repo. Next.js remounts this component on every doc navigation
// (each /review/[docId] is a separate page), so in-memory state alone
// doesn't survive that; localStorage does.
const MAX_STORED_TURNS = 40;

function storageKey(repositoryName: string): string {
  return `docagent_chat:${repositoryName}`;
}

function loadHistory(repositoryName: string): ChatTurn[] {
  try {
    const raw = window.localStorage.getItem(storageKey(repositoryName));
    return raw ? (JSON.parse(raw) as ChatTurn[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(repositoryName: string, messages: ChatTurn[]): void {
  try {
    window.localStorage.setItem(
      storageKey(repositoryName),
      JSON.stringify(messages.slice(-MAX_STORED_TURNS))
    );
  } catch {
    // Storage unavailable (private browsing, quota) — chat still works,
    // it just won't survive navigating to another doc.
  }
}

export default function DocChatWidget({ repositoryName }: DocChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Restore this repository's saved conversation whenever the widget mounts
  // for it — covers both a fresh page load and navigating between docs of
  // the same repo (a new DocChatWidget instance, same repositoryName).
  useEffect(() => {
    setMessages(loadHistory(repositoryName));
    setError(null);
  }, [repositoryName]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading, open]);

  async function handleSend() {
    const question = input.trim();
    if (!question || loading) return;

    const historyBeforeThisTurn = messages;
    const withUserTurn: ChatTurn[] = [...messages, { role: "user", content: question }];
    setMessages(withUserTurn);
    saveHistory(repositoryName, withUserTurn);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repositoryName,
          question,
          history: historyBeforeThisTurn,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error || "Chat request failed");
      }
      const withAnswer: ChatTurn[] = [...withUserTurn, { role: "assistant", content: data.answer }];
      setMessages(withAnswer);
      saveHistory(repositoryName, withAnswer);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setMessages([]);
    saveHistory(repositoryName, []);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-text text-white px-5 py-3.5 text-xs font-bold uppercase tracking-wider shadow-lg hover:bg-accent transition-all"
        aria-label={open ? "Close documentation chat" : "Ask about this repo"}
      >
        {open ? (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        )}
        {open ? "Close" : "Ask about this repo"}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 flex h-[520px] w-[380px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
          {/* Header */}
          <div className="relative flex items-center justify-between border-b border-border px-4 py-3 shrink-0">
            <div className="absolute top-0 left-0 right-0 h-1 bg-presidio-gradient" />
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-teal">
                Documentation Assistant
              </p>
              <p className="text-xs font-mono text-muted truncate">{repositoryName}</p>
            </div>
            {messages.length > 0 && (
              <button
                onClick={handleClear}
                className="shrink-0 text-[10px] font-bold uppercase tracking-wider text-muted hover:text-danger transition-colors"
                aria-label="Clear conversation"
              >
                Clear
              </button>
            )}
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {messages.length === 0 && (
              <p className="text-xs text-muted leading-relaxed">
                Ask me anything about this repository — how something works, what&apos;s in a
                file, or who last edited it.
              </p>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" ? (
                  <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-canvas px-3.5 py-2.5 text-xs text-text">
                    <div className="prose prose-sm prose-slate max-w-none prose-headings:font-bold prose-headings:text-text prose-a:text-teal prose-code:text-teal prose-code:bg-teal/5 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          pre({ children }: any) {
                            // Same has-[] technique as DocPreview.tsx — see
                            // MermaidDiagram.tsx for why. Styling is set
                            // directly here rather than via prose-pre: so the
                            // has-[] conditional can target it.
                            return (
                              <pre className="has-[.mermaid-diagram-card]:bg-transparent has-[.mermaid-diagram-card]:p-0 has-[.mermaid-diagram-card]:my-0 bg-text text-white rounded-xl p-3 my-2 overflow-x-auto">
                                {children}
                              </pre>
                            );
                          },
                          code({ inline, className, children, ...props }: any) {
                            const match = /language-(\w+)/.exec(className || "");
                            if (match && match[1] === "mermaid") {
                              return <MermaidDiagram chart={String(children).replace(/\n$/, "")} />;
                            }
                            return (
                              <code className={className} {...props}>
                                {children}
                              </code>
                            );
                          },
                        }}
                      >
                        {m.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-text text-white px-3.5 py-2.5 text-xs whitespace-pre-wrap">
                    {m.content}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm border border-border bg-canvas px-3.5 py-2.5">
                  <svg className="w-4 h-4 animate-spin text-teal" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                </div>
              </div>
            )}

            {error && <p className="text-[11px] font-semibold text-danger">{error}</p>}
          </div>

          {/* Input */}
          <div className="border-t border-border p-3 shrink-0">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question..."
                rows={1}
                className="flex-1 resize-none rounded-xl border border-border bg-canvas px-3 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal/20 focus:border-teal placeholder:text-muted/60"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="shrink-0 rounded-full bg-accent-cta text-text p-2.5 hover:bg-yellow-300 transition-all disabled:opacity-50"
                aria-label="Send"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
