"use client";

import { useEffect, useId, useRef, useState } from "react";

// Mermaid's init is process-wide and expensive to repeat — do it once and
// share the promise across every diagram instance on the page.
let mermaidPromise: Promise<typeof import("mermaid").default> | null = null;

function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "strict",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

export default function MermaidDiagram({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const instanceId = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    let cancelled = false;
    setError(null);

    (async () => {
      try {
        const mermaid = await getMermaid();
        const { svg } = await mermaid.render(`mermaid-${instanceId}`, chart.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;

          // Mermaid's default output is `width="100%"` plus a `max-width`
          // style capped at the diagram's natural size — that scales the
          // SVG DOWN to fit whatever container it lands in. A simple 3-node
          // diagram happens to fit and looks fine; a wide multi-branch
          // flowchart gets squeezed to the same container width and its
          // text becomes illegible. Force the SVG to its true intrinsic
          // pixel size instead (from its own viewBox) so diagrams are only
          // ever as big or small as their actual content — the card's
          // `overflow-x-auto` handles anything wider than the visible area.
          const svgEl = containerRef.current.querySelector("svg");
          if (svgEl) {
            const viewBox = svgEl.getAttribute("viewBox");
            const dims = viewBox?.split(/\s+/).map(Number);
            if (dims && dims.length === 4 && dims[2] > 0 && dims[3] > 0) {
              svgEl.setAttribute("width", String(dims[2]));
              svgEl.setAttribute("height", String(dims[3]));
            }
            svgEl.style.maxWidth = "none";
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to render diagram");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, instanceId]);

  if (error) {
    return (
      <div className="mermaid-diagram-card not-prose my-4 rounded-xl border border-danger/30 bg-danger/5 p-4">
        <p className="mb-2 text-xs font-semibold text-danger">
          Diagram failed to render: {error}
        </p>
        <pre className="overflow-x-auto rounded-lg bg-text p-3 font-mono text-[11px] text-white">
          {chart}
        </pre>
      </div>
    );
  }

  return (
    // `mermaid-diagram-card` is a plain marker class (no styles of its own)
    // that the parent markdown renderer's <pre> wrapper detects via a CSS
    // `has-[.mermaid-diagram-card]` selector to strip its own dark code-box
    // styling — inspecting react-markdown's children prop in JS to detect
    // "is this a mermaid block" proved unreliable across its render passes,
    // so this diagram announces itself via a class instead.
    // justify-start (not center) — a diagram wider than the card scrolls
    // predictably from its left edge instead of overflowing both sides.
    <div className="mermaid-diagram-card not-prose my-4 flex justify-start overflow-x-auto rounded-xl border border-border bg-canvas p-4">
      <div ref={containerRef} />
    </div>
  );
}
