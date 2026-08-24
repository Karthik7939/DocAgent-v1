# RAG Pipeline — Complete Walkthrough (Plain English)

This document explains everything the RAG (Retrieval-Augmented Generation)
system does, in simple words, workflow by workflow. This is now the sole
RAG documentation file (an older, denser file-by-file technical reference
was retired in favor of this one). For the history of bugs found and
fixed in this pipeline, see `rag_fix_plan.md`.

---

## 1. What problem does RAG solve here?

When an AI agent has to write documentation for a code change, it has a
problem: a single Git push only shows the *diff* — the lines that changed.
The AI has no idea how the changed function is used elsewhere, what classes
it depends on, or what the rest of the codebase even looks like.

Two bad options without RAG:
- **Only look at the diff** → the AI writes docs blind, missing context,
  and guesses (hallucinates) about things it can't see.
- **Dump the entire repository into the prompt** → way too much text for
  any LLM's context window, expensive, and the AI gets lost in noise.

RAG is the middle ground: **search the repository for the specific pieces
of code that are actually relevant**, and hand the AI just those pieces.
That's it — retrieval (search) + augmented generation (give the LLM real
evidence before it writes anything).

---

## 2. The building blocks (glossary, simple terms)

| Term | Plain-English meaning |
|---|---|
| **Chunk** | A small, meaningful piece of a file — one function, one class, one doc section. Not an arbitrary character-count slice. |
| **Embedding** | A list of ~384 numbers that represents what a piece of text *means*. Similar meanings → similar number lists. This is how "search by meaning" works instead of just keyword matching. |
| **Vector store** | Where embeddings live, searchable by "find me the closest numbers to this query's numbers." This project uses **Pinecone** (cloud) by default, with **FAISS** (local file) as a fallback. |
| **BM25** | An old, reliable keyword-search algorithm (like a smarter Ctrl+F). Good at exact term matches embeddings sometimes miss — e.g. finding the literal function name `authenticate_user`. |
| **Dependency graph** | A map of which files import/call which other files. Lets retrieval pull in code that's *structurally* connected to what changed, even if it doesn't share any wording. |
| **RRF (Reciprocal Rank Fusion)** | The method used to merge results from vector search + BM25 + dependency graph into one ranked list, based on how high each result ranked in each channel. |
| **Reranker** | A second-pass judge that looks at the merged candidates and actually scores "how relevant is this to the query," instead of trusting rank position alone. |
| **MMR (Maximal Marginal Relevance)** | A final polish step that avoids picking 5 near-identical chunks when a more diverse set would cover more ground. |
| **Chunk overlap** | When a chunk is too big and has to be split in two, a small amount of the end of piece 1 is repeated at the start of piece 2 — so nothing gets lost right at the cut. |

---

## 3. Workflow A — Bootstrap (first-time indexing)

This runs **once**, the first time a repository is connected — either
automatically, or by clicking "Add to KB" in the Knowledge Base UI.

```
Repo cloned locally
   │
   ▼
1. Discover files — walk the repo, skip node_modules/.git/binaries/etc.
   │
   ▼
2. Chunk every file
   - Code files → split at AST boundaries (Tree-sitter): one chunk per
     function/class/method. If a symbol is too big, hard-split it with
     overlap (see glossary above).
   - Doc files (.md/.rst/.txt) → split by section heading.
   │
   ▼
3. Generate embeddings for every chunk (sentence-transformers model,
   runs locally, no external API call). Content already embedded before
   (same hash) is served from cache instead of recomputed.
   │
   ▼
4. Upsert every embedded chunk into the vector store (Pinecone/FAISS),
   plus a keyword index (BM25) and a dependency graph.
   │
   ▼
5. Save a local "sidecar" file recording exactly what's in the vector
   store (needed because Pinecone itself only stores lightweight
   metadata, not full chunk content).
   │
   ▼
Repository is now searchable.
```

**Where in the code:** `rag/indexing/bootstrap.py` (`BootstrapIndexer`),
orchestrated by `rag/pipeline/bootstrap_pipeline.py`.

---

## 4. Workflow B — Incremental update (every push after that)

This is what actually runs on every GitHub push to an already-indexed
repo — and it's careful not to redo work that isn't needed.

```
GitHub push webhook arrives
   │
   ▼
1. Git diff the old commit against the new one → exact list of added /
   modified / deleted / renamed files.
   │
   ▼
2. Re-chunk ONLY the changed files (everything else is left alone).
   │
   ▼
3. For every new chunk, compare its content hash against what's already
   stored for that same chunk ID:
   - Identical content  → skip, no re-embedding, nothing changes.
   - Different content  → mark the old chunk invalid, embed + store the
                           new one.
   - Brand new chunk    → embed + store it.
   │
   ▼
4. For every deleted/renamed/modified file, check for now-orphaned old
   chunks (chunks that existed before but aren't in the new version) and
   soft-delete them (marked inactive, hidden from search, not physically
   removed yet).
   │
   ▼
5. Update the BM25 keyword index and the dependency graph to match.
   │
   ▼
6. Save everything back to disk/Pinecone. If this save step fails after
   vectors were already upserted to Pinecone, those specific vectors get
   rolled back (deleted) to keep Pinecone and the local record in sync —
   this is a real safeguard added after a live bug was found and fixed.
   │
   ▼
7. If more than 25% of a repo's stored vectors are now soft-deleted,
   trigger one physical cleanup pass that actually rebuilds the index
   from only the active chunks (keeps storage from growing forever with
   dead data).
```

**The key idea:** editing one file in a 500-chunk repository only touches
that file's chunks. The other 499 chunks are never re-read, re-embedded,
or re-uploaded.

**Where in the code:** `rag/indexing/incremental.py`
(`IncrementalIndexer`), orchestrated by `rag/pipeline/rag_pipeline.py`
and `rag/pipeline/incremental_pipeline.py`.

### 4a. Building the *query* for this push

Before retrieval can run, the system needs to know what to search for.
For a push event, this isn't a hand-typed question — it's built
automatically from the diff itself:

```
Changed files + changed symbols (functions/classes touched)
   │
   ▼
QueryBuilder assembles a structured query: which files changed, which
symbols changed, what they import, keywords extracted from the diff.
   │
   ▼
(Optional) SemanticQueryRefiner sends that structured evidence to an LLM
(Gemini, in this deployment) to translate it into documentation-style
terms — e.g. turning raw code evidence into phrases like "user
authentication flow" instead of just function names.
   │
   ▼
Final SemanticQuery — ready for the retrieval workflow below.
```

**Where in the code:** `rag/preprocessing/query_builder.py`,
`rag/preprocessing/semantic_refiner.py`.

---

## 5. Workflow C — Retrieval (how a search actually happens)

This is the core workflow every other one eventually calls into. Given a
query (built above, or a plain string an agent asks for directly), here's
exactly what happens:

```
SemanticQuery comes in
   │
   ├──► Channel 1: Vector search (Pinecone/FAISS)
   │       Embed the query text with the same model used for chunks,
   │       find the closest-meaning chunks by cosine similarity.
   │
   ├──► Channel 2: BM25 keyword search
   │       Find chunks with the strongest literal keyword overlap.
   │
   └──► Channel 3: Dependency graph search
           If specific files changed, pull in chunks from files that
           import/are imported by them.
   │
   ▼
Each channel's results are filtered (remove inactive/soft-deleted
chunks, dedupe by chunk ID, drop anything below a low similarity floor)
— this floor is intentionally low; it's not the real relevance judge,
see the next step.
   │
   ▼
Merge all three channels with Reciprocal Rank Fusion (RRF): a chunk that
showed up near the top in multiple channels ranks higher overall than
one that only appeared in one channel.
   │
   ▼
Rerank: take a wider pool of the RRF-merged candidates (not just the
final top-k) and score each one against the query with a cross-encoder
model — an actual relevance judgment, not just "which channel saw it
first." This step exists specifically because RRF rank position alone
isn't a reliable enough signal for long, multi-topic queries — verified
by testing it live and finding it broken before this step was added.
   │
   ▼
Truncate to the final top-k results, now properly ranked by real
relevance instead of raw channel position.
   │
   ▼
Wrap the results into a ContextPackage — the final, structured object
that gets handed to whichever agent asked for context.
```

**Where in the code:** `rag/retrieval/hybrid_retriever.py`
(`HybridRetriever`), `rag/retrieval/reranker.py`
(`CrossEncoderReranker`), orchestrated by
`rag/pipeline/retrieval_pipeline.py`.

---

## 6. Workflow D — Handing context to the agents

Retrieval alone doesn't write documentation — it just finds the right
raw material. Here's how that material actually reaches the agents that
write and validate docs:

```
ContextPackage (from Workflow C)
   │
   ▼
Attached to SharedMemory.rag_context_package — the "whiteboard" every
agent in the documentation pipeline reads from.
   │
   ▼
UnderstandingAgent reads it first, in priority order:
  1. Use the pre-computed ContextPackage if it has real chunks in it
     (this is the commit-diff-driven path, Workflow B/C above).
  2. Otherwise, run its own on-demand retrieval — hardcoded topic
     queries like "project purpose architecture main core system..."
     for things like project overview, API discovery, folder structure,
     and dependencies. (This is the path that was found broken and
     fixed this session — see rag_fix_plan.md P0.1-P0.4, P1.3.)
  3. If neither is available, fall back to metadata-only reasoning
     (still works, just without code-level grounding).
   │
   ▼
DocumentationAgent, when it actually writes each doc (README,
ARCHITECTURE, CHANGELOG, SECURITY), calls ContextSlicer to cut the full
ContextPackage down into a focused, budgeted slice per document — with
MMR applied so near-duplicate chunks don't crowd out coverage of
different parts of the file/repo, then a hard character-budget cutoff so
the LLM prompt stays a manageable size.
```

**Where in the code:** `agents/memory/shared_memory.py`
(`rag_context_package` field), `agents/understanding/understanding_agent.py`
(`_retrieve` method), `agents/documentation/context_slicer.py`
(`ContextSlicer`).

---

## 7. The two ways a query gets built, side by side

| | Commit-diff path (webhook push) | Ad-hoc topic path (UnderstandingAgent) |
|---|---|---|
| **Used when** | A GitHub push triggers incremental indexing | UnderstandingAgent needs context for a specific topic (project overview, API discovery, etc.) |
| **Query source** | Built from the actual Git diff — real changed files/symbols | Hardcoded natural-language strings per topic |
| **Query refinement** | Optional LLM step translates evidence into doc-style terms | None — the string is used as-is |
| **Complexity** | Structured, evidence-grounded | Simple, fixed |

Both paths funnel into the *same* Workflow C retrieval pipeline once the
query is built — the difference is only in how the query gets assembled.

---

## 8. What happens when things go wrong (safety nets)

- **RAG service fails or isn't configured** → `UnderstandingAgent` falls
  back to metadata-only reasoning instead of crashing. Docs still get
  generated, just with less code-level grounding.
- **A specific retrieval channel fails** (e.g. Pinecone times out) → that
  channel just contributes nothing; the other channels still work.
- **Reranker model can't load or scoring fails** → falls back to plain
  RRF order instead of failing the whole request.
- **Embedding model version changes** → the next incremental update
  detects the mismatch and automatically triggers a full bootstrap
  rebuild instead of mixing incompatible old/new vectors.
- **A Pinecone save fails partway through an update** → the just-upserted
  vectors for that update get rolled back, so Pinecone and the local
  record of "what's indexed" never silently disagree.

---

## 9. Known limitations (honest, not hidden)

- The embedding model (`all-MiniLM-L6-v2`) is a general-purpose text
  model, not trained specifically on code. Tested against code-specific
  alternatives directly in this environment — none of the working
  alternatives actually beat it in a real side-by-side comparison, so
  this was a deliberate "don't change it" decision, not an oversight.
- The reranker reliably improves *ordering*, but doesn't yet reject a
  fully irrelevant query the way a perfectly-calibrated cutoff would —
  its absolute score isn't trustworthy for the long queries this system
  sends, only its relative ranking within a batch is.
- BM25 does a full rebuild on every incremental update (not truly
  incremental) — fine at current repo sizes, would need attention if
  repos grow much larger.
- Token counting throughout is an approximation (`characters ÷ 4`), not
  a real tokenizer — chunks are sized close to their budget, not exactly.

---

## 10. Quick reference — where everything lives

```
rag/
├── chunking/        Splits files into chunks (AST-based for code, section-based for docs)
├── embeddings/       Turns chunks into searchable number-vectors, with caching
├── retrieval/         Vector store, BM25, dependency graph, hybrid merge, reranker
├── indexing/           Bootstrap (first time) + incremental (every push) index building
├── pipeline/            Orchestrates the workflows above end-to-end
├── preprocessing/        Builds queries from commit diffs, optional LLM query refinement
├── parsing/                AST parsing (Tree-sitter) and dependency graph construction
├── schemas/                 Pydantic data contracts (Chunk, SemanticQuery, ContextPackage, ...)
├── config/                   All RAG_* settings, in one place
└── llm/                       LLM provider clients (Groq/Gemini/Ollama/Grok) for query refinement
```
