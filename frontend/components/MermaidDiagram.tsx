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
        suppressErrorRendering: true,
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

export default function MermaidDiagram({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hasError, setHasError] = useState<boolean>(false);
  const instanceId = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    let cancelled = false;
    setHasError(false);

    (async () => {
      try {
        const mermaid = await getMermaid();
        const { svg } = await mermaid.render(`mermaid-${instanceId}`, chart.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;

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
      } catch {
        if (!cancelled) {
          setHasError(true);
        }
      } finally {
        const dmermaid = document.getElementById(`dmermaid-${instanceId}`);
        if (dmermaid) dmermaid.remove();
        const rawMermaid = document.getElementById(`mermaid-${instanceId}`);
        if (rawMermaid && !containerRef.current?.contains(rawMermaid)) {
          rawMermaid.remove();
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, instanceId]);

  if (hasError) {
    return <div className="mermaid-diagram-card hidden" />;
  }

  return (
    <div className="mermaid-diagram-card not-prose my-4 flex justify-start overflow-x-auto rounded-xl border border-border bg-canvas p-4">
      <div ref={containerRef} />
    </div>
  );
}
