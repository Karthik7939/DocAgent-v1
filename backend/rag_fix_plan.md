# RAG Pipeline Fix Plan

Based on a full architecture review (backend/rag/, backend/agents/understanding/,
backend/agents/documentation/context_slicer.py) plus live testing against the
already-indexed `Blrm123/canonyx` repository (555 real vectors in Pinecone) on
2026-08-24. Every finding below was either read directly in source or
reproduced with a live `/api/rag/retrieve` call — nothing here is speculative.

Ordered by priority. P0 = fixes a live production defect, low implementation
risk. P1 = real robustness/quality gap, moderate effort. P2 = larger
architecture/infra decision that needs explicit sign-off (cost, downtime, or
a full reindex) before starting.

---

## P0 — Fix first (low risk, high impact)

### P0.1 — No reranking step after RRF fusion (root cause of the threshold failure)

**Evidence:** `backend/rag/retrieval/hybrid_retriever.py` fuses vector + BM25
+ dependency-graph results via RRF (`rrf()`, lines 120-170) using **rank
position only** — each channel's raw score (cosine similarity, BM25 score,
dependency-hop score) is discarded after fusion. There is no cross-encoder,
LLM-based, or any other reranking step anywhere under `backend/rag/retrieval/`.

Live proof this actually hurts output: the exact query
`understanding_agent.py` sends for the project-overview document
(`"project purpose architecture main core system application overview
README feature functionality"`) returns **0 results** at the default
`similarity_threshold=0.30`, but 10 genuinely relevant results
(`frontend/README.md` ×3, `backend/main.py`, `page.tsx`) at threshold 0.0.
Lowering the threshold to fix that, however, makes a *nonsense* query
(`"quantum blockchain xyzabc123"`) also return 10 results — garbage ones
(`skeleton.tsx`, `badge.tsx`, `requirements.txt`). **No single threshold
value gets both cases right** — proof that raw cosine magnitude from the
configured embedding model (`all-MiniLM-L6-v2`) doesn't reliably separate
relevant from irrelevant for these query styles. A cutoff on that signal
alone cannot be trusted; something has to actually judge relevance.

**Fix:** After `HybridRetriever.rank()` produces the RRF-fused, threshold-free
candidate list (over-fetch ~30-50 candidates instead of just `top_k`),
add a reranking pass before final truncation to `top_k`:
- Minimum viable version: a small local cross-encoder
  (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`, similar footprint to the
  current embedding model, no new infra) scoring (query, chunk) pairs.
- Alternative if avoiding a new model dependency: one cheap LLM call that
  scores/filters the ~30-50 candidates for relevance (reuses the existing
  Groq/Gemini client already in the pipeline, no new dependency, but adds
  latency + API cost per retrieval call).

**Also required as part of this fix:** widen the pre-RRF per-channel
`similarity_threshold` gate (or drop it) so the reranker actually gets a
real candidate pool to work with — see P0.2.

**Effort:** Moderate (new scoring step + top_k widening + threshold
adjustment). **Risk:** Low — additive, doesn't change chunking/indexing/storage.

**Status: DONE (2026-08-24).** Added `backend/rag/retrieval/reranker.py`
(`CrossEncoderReranker`, `cross-encoder/ms-marco-MiniLM-L-6-v2`, already
available via the existing `sentence-transformers` dependency — no new
package). Wired into `HybridRetriever.rank()`: widens the candidate pool to
`rerank_candidate_pool` (default 40) before truncating to `top_k`, with a
`None`-vs-`[]` return contract so "reranker unavailable" (falls back to RRF
order) is distinguishable from "reranker ran, found nothing relevant" (an
empty result is honored, not treated as a failure).

**Caught and corrected a real mistake before shipping**: the first version
added an absolute relevance cutoff (`rerank_min_score=0.5`, filtering out
anything the cross-encoder scored below "more likely relevant than not").
Testing against the *actual* indexed content proved this wrong — genuinely
relevant chunks (`## Highlighted Features`, `FEATURE_SECTIONS`) scored
sigmoid ≈0.00001-0.00007, indistinguishable in absolute terms from
irrelevant ones. This model was trained on short, natural search queries;
this system's 19-word keyword-bag queries are out-of-distribution for it,
so absolute score magnitude isn't trustworthy — only relative ordering
within a batch is. Removed the cutoff entirely; kept relative reranking
only. Documented this limitation plainly in code rather than pretend it's
fully solved: the reranker reliably improves *ordering*, but doesn't yet
reject a fully irrelevant query the way a well-calibrated cutoff would —
see P1.3, which is the more durable fix for that remaining gap.

Verified live end-to-end: the exact `understanding_agent.py` production
query for the project-overview document, previously returning 0 results,
now returns `frontend/README.md` at rank 1 among 5 relevant results.
Auth and API-discovery queries also verified still correct. Full test
suite: 83/87 pass (4 pre-existing unrelated failures, confirmed via
`git stash` in an earlier audit pass).

---

### P0.2 — Per-channel `similarity_threshold` is applied pre-fusion, on three incomparable scales

**Evidence:** `backend/rag/retrieval/metadata_filter.py:67-74`
(`filter_similarity`) applies the same numeric `settings.similarity_threshold`
(default 0.30) to: raw cosine similarity (vector channel), a
batch-max-normalized BM25 score (`0 < score <= 1`, relative to that
specific query's batch — not calibrated across queries), and a hand-coded
dependency-hop score (`1.0` / `0.8` / `0.6`, `dependency_retriever.py:190-200`).
The code itself flags this as heuristic (`metadata_filter.py:173` comment).
This is *why* P0.1's threshold experiment showed such a sharp cliff — one
global number is being asked to mean three different things at once.

**Fix:** Once P0.1's reranker lands, this pre-fusion threshold no longer
needs to be precise — it only needs to keep the candidate pool from
exploding, so widen it to something safe and low (e.g. 0.05, or remove
entirely and rely on `top_k`-per-channel + the reranker to do the real
filtering). Do **not** attempt to "properly calibrate" three different score
scales against one shared cutoff — that's solving the wrong problem; let
the reranker (P0.1) be the actual relevance judge.

**Effort:** Small (one settings default + a few lines in `metadata_filter.py`
or `merge()`). **Risk:** Low, but must ship together with P0.1 — widening
this alone without a reranker just trades the "returns nothing" failure for
the "returns garbage" failure demonstrated live above.

**Status: DONE (2026-08-24).** Lowered `similarity_threshold` default to
0.05 in both `backend/rag/config/settings.py` and `backend/.env`
(`RAG_SIMILARITY_THRESHOLD` — the `.env` value overrides the Python
default via pydantic-settings, so both had to change).

**Found and fixed a second, independent bug while verifying this**:
`backend/app/api/rag.py`'s `RetrieveRequest.similarity_threshold` had its
own hardcoded `default=0.30`, completely disconnected from
`rag.config.settings` — meaning the standalone `POST /api/rag/retrieve`
HTTP endpoint would have kept using the old miscalibrated threshold even
after this fix, silently diverging from the internal
`RAGService.retrieve()` path that `understanding_agent.py` actually uses.
Changed the field to `float | None = None`; the handler now only passes
`similarity_threshold` through to `SemanticQuery` when the caller
explicitly set it, otherwise `SemanticQuery`'s own
`default_factory=lambda: settings.similarity_threshold` applies — so the
HTTP endpoint and the internal path can no longer drift apart.

**Also found and fixed** (unrelated to this specific setting, discovered
while debugging why the fix "wasn't taking effect"): the backend's worker
processes had been running continuously since long before this session's
edits — FastAPI lifespan events were firing on every file-watcher trigger,
but Python never re-executes an already-imported module's top-level code,
so `RAGSettings()` had genuinely only run once, at original startup.
`uvicorn --reload`'s "Application started" log lines were misleading — no
actual process restart was happening. Did a clean kill + restart to get a
true fresh process; worth knowing if a future settings change ever again
seems to "not take effect" despite correct file edits.

---

### P0.3 — `SemanticQueryRefiner` is dead in the actual deployment

**Evidence:** `backend/rag/preprocessing/semantic_refiner.py:51` hardcoded
`if settings.llm_provider.lower() != "ollama": return {}` — LLM-based query
term expansion only ran on a local Ollama model. The shipped `.env` sets
`RAG_LLM_PROVIDER=gemini` (`backend/.env:86`), so despite
`enable_semantic_query_refinement=True` being the default, this step was
silently skipped on every commit-driven retrieval in production.

**Decision (confirmed with user, 2026-08-24):** Not deliberate cost
control worth keeping — user does not want a locally-running model at all
(confirmed no Ollama process, no `ollama` CLI installed, and
`RAG_OLLAMA_BASE_URL` commented out in `.env`). Decision: enable
refinement for Gemini specifically, not a blanket "any configured
provider" — Groq/Grok were not opted into the extra per-retrieval API
call.

**Status: DONE (2026-08-24).** Added `_SUPPORTED_PROVIDERS = {"ollama",
"gemini"}` in `semantic_refiner.py`; the gate now checks membership in
that set instead of a single hardcoded string. `ollama` stays supported
for anyone who does run it locally later — no reason to remove a free
option. `GeminiClient` already implements `generate(prompt, system_prompt)`
and `health_check()`, matching the `BaseLLM` interface this module already
calls generically, so no other code changes were needed. Fixed a stale
`.env` comment that claimed this feature was "now active -- uses
GROQ_API_KEY" (it was never true — the gate only ever allowed Ollama).

Verified end-to-end against real Gemini (this code path had never
actually been exercised before — passing the gate isn't the same as the
call working): fed a realistic evidence packet, got back well-formed,
correctly-parsed JSON with genuinely useful refined terms (e.g.
`"high_level_purpose": "Validates credentials and submits authentication
requests."`, sensible `keywords`/`technical_concepts`/`processing_workflow`
lists) — not just "no exception," actually useful output.

**Cost impact accepted:** one extra Gemini call per commit-driven
retrieval (not per ad-hoc topic query — this only runs in the
`QueryBuilder`/webhook path, not `understanding_agent.py`'s topic
retrieval).

---

### P0.4 — `chunk_overlap` setting exists but is never applied (dead config)

**Evidence:** `backend/rag/config/settings.py:261-265` defines
`chunk_overlap = 100`, but grep confirms neither `code_chunker.py`'s
`_split_large_content` (lines 264-343) nor `doc_chunker.py`'s
`_split_large_section` (lines 381-443) reference it — both do a naive
greedy line/paragraph split with zero overlap between resulting pieces.
The codebase's own `RAG_DOCUMENTATION.md:1647` already admitted this at
the time (that file has since been superseded by `rag/RAG_WALKTHROUGH.md`).
Any
oversized function or doc section that gets split has a hard content
boundary with nothing shared across the cut — context right at the split
point can become unretrievable from either resulting chunk.

**Fix:** Either wire `chunk_overlap` into both split functions (carry the
last N estimated-tokens of the previous piece into the start of the next),
or remove the dead setting so the config stops claiming behavior that
doesn't exist. Wiring it in is the more valuable option and is a contained,
mechanical change to two functions.

**Effort:** Small. **Risk:** Low — isolated to the oversized-content split
path, doesn't touch normal (non-split) chunking.

**Status: DONE (2026-08-24).** Added `overlap_suffix()` to
`rag/utils/tokenizer.py` — a small shared helper that returns a trailing
suffix of units (lines or paragraphs) whose combined estimated token count
fits within a token budget, used by both chunkers so the logic isn't
duplicated. Wired into:
- `code_chunker.py::_split_large_content` — seeds the next line-based
  piece with trailing lines from the piece just closed.
- `doc_chunker.py::_split_large_section` — same, at paragraph granularity.

Both classes now accept `chunk_overlap` in `__init__` (defaulting to
`settings.chunk_overlap`), matching the existing `max_chunk_tokens` pattern.

Verified with real functional tests (not just syntax/type checks): built
an oversized function and an oversized doc section, forced a split with
tight token budgets, and confirmed adjacent pieces genuinely share trailing
content at the boundary — then re-verified the same behavior holds at the
actual production defaults (`max_chunk_tokens=1024`, `chunk_overlap=100`).
One test iteration caught a real test-data mistake (overlap_tokens smaller
than a single paragraph, which correctly produces zero overlap by design —
not a bug) before landing on realistic parameters. Full test suite: 83/87
pass (same 4 pre-existing unrelated failures). Backend reloads cleanly.

---

## P1 — Real gaps, moderate effort

### P1.1 — Pinecone incremental updates have no rollback

**Evidence:** `backend/rag/indexing/incremental.py`'s `refresh_indexes`
(lines 402-493) has explicit `.bak`-file backup/restore transaction handling
for the FAISS path, but none for Pinecone — vectors are already durably
upserted to the cloud by the time the local sidecar/BM25/graph `save()`
runs; if that local save fails, the exception propagates but nothing rolls
back the already-committed Pinecone writes. The local JSON sidecar (chunk
content + metadata) can end up out of sync with what's actually indexed.

**Fix:** Add a reconciliation path — either (a) on local-save failure,
delete the just-upserted Pinecone vectors for the affected chunk IDs to
restore consistency, or (b) rely on the existing `IncrementalIndexer.sync()`
method (lines 365-401, currently a manually-callable repair tool, not
invoked automatically) — wire it to run automatically after any
incremental update failure, or on a schedule.

**Effort:** Moderate — needs a clear decision on rollback vs.
reconcile-later strategy. **Risk:** Low to implement, but skipping this
means silent data drift can accumulate unnoticed over time.

**Status: DONE (2026-08-24).** Implemented true rollback, not
reconcile-later — chose option (a). `update()` now passes
`rollback_chunk_ids=[c.metadata.chunk_id for c in embedded_chunks]` into
`refresh_indexes()`.

**Design note — reading the code changed the plan.** The original two
options treated "the Pinecone-path save fails" as one failure mode. It
isn't: `refresh_indexes()`'s try block covers *four* saves (sidecar, BM25,
graph, model-info), and only the **sidecar** failing actually creates a
Pinecone-vs-local mismatch — it's the only local record of which vectors
are real chunks (Pinecone's own metadata is deliberately lightweight, full
content lives only in the sidecar). A naive "roll back on any exception in
this block" would have deleted perfectly good, correctly-persisted Pinecone
vectors just because an *unrelated* BM25 pickle write failed afterward —
actively worse than doing nothing. Split the try block in two: sidecar
save failure → hard-delete (`vector_store.delete(chunk_id, soft=False)`)
each chunk ID upserted this run, restoring the pre-update state (mirrors
what the FAISS `.bak` restore achieves); BM25/graph/model-info failure
*after* a successful sidecar save → no rollback, since Pinecone and the
sidecar are already mutually consistent at that point and BM25 is
independently repairable via the existing `sync()` method.

Verified with isolated mock-based tests (deliberately not run against real
Pinecone): (1) sidecar-save failure correctly triggers `delete(chunk_id,
soft=False)` for exactly the newly-upserted IDs, and still raises so the
caller knows the update failed; (2) a BM25-only failure, with the sidecar
save having succeeded, correctly does **not** touch Pinecone at all; (3)
the FAISS path is unaffected by the new optional parameter (defaults to
`None`, existing behavior unchanged). Full test suite: 83/87 pass (same 4
pre-existing unrelated failures). Backend reloads cleanly.

### P1.2 — API response embeds the full raw embedding vector for every chunk

**Evidence:** Live-tested `POST /api/rag/retrieve` — every result in the
response includes `chunk.embedding`, a 384-float array (~7-8KB of JSON per
chunk once serialized), even though no current consumer
(`understanding_agent.py`, `documentation_agent.py` via `context_slicer.py`)
reads that field — they only use `.content` and `.metadata`.

**Fix:** Strip `embedding` from the serialized `RetrievalResult`/`Chunk`
response by default (keep it available internally, just don't serialize it
over the API), or make it opt-in via a query param for callers that
actually need raw vectors (e.g. a future debugging/visualization tool).

**Effort:** Trivial (schema/serialization change). **Risk:** Low — verify no
current caller actually depends on the field before removing.

**Status: DONE (2026-08-24).** Confirmed `POST /api/rag/retrieve` is the
only place `ContextPackage` gets serialized to JSON (grepped for other
`model_dump` call sites — none). Added a nested `exclude` to that one
`model_dump(mode="json", ...)` call, targeting
`retrieval_results.results[].chunk.embedding` specifically — the `Chunk`
schema itself is untouched, so every internal Python consumer (which
never went through JSON serialization anyway) is unaffected.

Verified live against the running server, not just unit-tested: called the
real endpoint, confirmed the response no longer contains an `embedding`
key on any chunk while `content` and `metadata` are still present.

### P1.3 — Ad-hoc topic-retrieval queries are generic keyword-bags

**Evidence:** `understanding_agent.py:288-291,303-306,329-332,345-348` sends
fixed, broad, hardcoded strings like `"project purpose architecture main
core system application overview README feature functionality"` straight
into `RAGService.retrieve()` with zero query expansion/rewriting — this is
the exact query type shown above to produce a 0-vs-garbage threshold
cliff. Distinct from (and much simpler than) the commit-diff path's
`QueryBuilder`, which assembles structured, evidence-grounded queries.

**Fix:** Once P0.1 (reranker) lands, this becomes lower-risk to leave as-is
since the reranker will filter noise regardless of query looseness. If
tackled independently first, tighten these into several more targeted
queries per topic (e.g. split "project purpose" and "architecture" into
separate, more distinctive queries) rather than one long keyword salad.

**Effort:** Small, but best sequenced *after* P0.1 so its effect can
actually be measured against a working relevance judge.

**Status: DONE (2026-08-24).** Measured actual need first, as planned,
rather than assuming: re-ran all 4 production query strings live against
the reranker. 2 of 4 (`project_understanding`, `api_discovery`) already
retrieved genuinely relevant content — left untouched, no reason to risk
regressing something that works. The other 2
(`folder_responsibilities`, `dependency_graph`) still returned mostly
unrelated UI-component/skeleton files even with reranking — confirming
the plan's premise that abstract meta-words ("organization",
"responsibilities", "relationship", "layer") rarely appear verbatim in
real content, so no amount of reranking a bad candidate pool fixes a query
that never retrieved the right candidates in the first place.

Tested several concrete-phrasing rewrites live for both weak queries
before picking a winner (not guessed): the original
`folder_responsibilities` query surfaced icon/skeleton-loader files;
rewritten to `"top level directories frontend backend src app components
pages api routes and what each folder contains"`, it now surfaces
`README.md`, `app-shell.tsx`, `layout.tsx`. Original `dependency_graph`
surfaced `dropdown-menu.tsx`/`radio.tsx`/chart components; rewritten to
`"backend API client database connection service calls between modules"`,
it now surfaces `main_integrated.py`, `agentic/main.py`, `middleware.ts`.
Both changes are in `agents/understanding/understanding_agent.py`, with
comments explaining why (so a future reader isn't left wondering why the
query text looks oddly specific).

Full test suite: 83/87 pass (same 4 pre-existing unrelated failures).
Backend reloads cleanly.

---

## P2 — Larger decisions, needs explicit sign-off before starting

### P2.1 — Embedding model is general-purpose, not code-aware, and undersized

**Evidence:** Deployed model is `all-MiniLM-L6-v2` (`.env:80`) — 384-dim,
general sentence-similarity model, ~256 token actual sequence limit — used
symmetrically on code chunks sized up to 1024 *estimated* tokens (the
model silently truncates anything beyond its real limit, on top of the
RAG layer's own coarser truncation). Not pretrained on code.

**Why P2, not P0/P1:** Changing the embedding model changes vector
dimension, which Pinecone fixes at index creation — this requires
**rebuilding the entire index from scratch, re-embedding every already-
indexed repository** (currently `canonyx`, `Navayatra`, `TEST-REPO-
MINDSTRIDE`, `Mindstride-test-repo-v1`, `Doc_generation_test` — ~1788
vectors total as of this review). It also may mean trading a free local
model for a paid API-based one (better code embedding models are mostly
API-based) — a real cost decision.

**Fix (once approved):** Evaluate a code-aware embedding model (e.g. a
code-pretrained sentence-transformers variant, or a paid API option) sized
to comfortably cover 1024-token chunks, migrate via a full re-bootstrap of
each indexed repo.

**Effort:** Large (model evaluation + full reindex of every repo + cost
tradeoff decision). **Risk:** Medium — reversible (old index can be
rebuilt back) but a real one-time cost/time hit, and downtime for KB
search during migration.

**Status: EVALUATED, NOT PROCEEDING (2026-08-24).** Config was never
touched — every test below used throwaway standalone scripts against
`.env`'s existing `all-MiniLM-L6-v2` config, confirmed unchanged.

Tested five code-specific candidates directly in this environment before
any decision:
- `jinaai/jina-embeddings-v2-base-code` — fails to load: custom model
  code imports `find_pruneable_heads_and_indices`, removed from the
  installed `transformers 5.15.1`.
- `jinaai/jina-embeddings-v3` — fails differently, but same root cause
  class (`'XLMRobertaLoRA' object has no attribute
  'all_tied_weights_keys'`).
- `codesage/codesage-large-v2` and `codesage/codesage-small-v2` — both
  fail identically (`Conv1D` removed from `transformers.modeling_utils`);
  confirmed the whole CodeSage family shares this custom code, not a
  per-model issue.
- `microsoft/unixcoder-base`, `microsoft/codebert-base`,
  `microsoft/graphcodebert-base` — all three **load successfully** (no
  custom remote code, standard `transformers` architecture). GraphCodeBERT
  has missing/randomly-initialized pooler weights (flagged, not
  necessarily fatal since sentence-transformers mean-pools rather than
  using that head). UniXcoder's 1026-token max sequence length was the
  best fit for this system's 1024-token chunk budget.
- `nomic-ai/nomic-embed-text-v1.5` (not code-specific, but the other
  candidate discussed) — loads successfully once `einops` is installed;
  768-dim, 8192 token context.

**The decisive test, and the honest result:** rather than assume a
code-specific model would help, ran a direct empirical comparison —
`unixcoder-base` (the strongest working code-specific candidate) against
the current `all-MiniLM-L6-v2` — using both a short clean-text example and
a realistic long-query/long-chunk example matching the actual production
scenario (the same query style that P0.1/P0.2 fixed). **In both tests,
the current model showed *better* relevant-vs-irrelevant separation than
the code-specific alternative** (0.446 vs 0.180 on the short test; 0.457
vs 0.271 on the realistic long-content test) — the opposite of the
assumption this P2 item was written on.

This doesn't prove MiniLM is definitively the better model in general —
two handcrafted examples aren't a rigorous benchmark (no precision@k over
labeled query-document pairs). But it does mean the original case for
swapping isn't supported by the evidence gathered, and the actual root
cause of the production defect this investigation started from (P0.1/P0.2)
was already fixed independently of the embedding model. **Decision: keep
`all-MiniLM-L6-v2`, no config changes made.** Revisit only if a proper
benchmark is done first, or if a future need specifically calls for it.

### P2.2 — BM25 has no true incremental update

**Evidence:** `backend/rag/retrieval/keyword_store.py`'s `_rebuild_bm25`
does a full `BM25Okapi` rebuild from the entire in-memory corpus on every
incremental indexing run (`rank_bm25` has no incremental API).

**Why P2:** Not causing a problem at current repo sizes; only worth fixing
once corpus size makes full-rebuild latency noticeable. Track, don't act
yet.

### P2.3 — Token counting is `len(text) // 4` everywhere, not a real tokenizer

**Evidence:** `backend/rag/utils/tokenizer.py:20-40` — used for chunk
sizing, embedding pre-truncation, and prompt-length estimates throughout
`rag/`. A real tokenizer aligned to the configured embedding model (or
`tiktoken` for LLM-side estimates) would be more accurate, especially for
code (dense punctuation/identifiers diverge more from the char/4 heuristic
than prose does).

**Why P2:** Broad-touching (many call sites), not currently causing a
correctness failure — the effect is chunks being somewhat mis-sized
relative to the *stated* budget, not returning wrong results the way
P0.1-P0.4 do. Worth doing but not urgent.

### P2.4 — Context assembly has no MMR/diversity-aware selection

**Evidence:** `backend/agents/documentation/context_slicer.py` is pure
greedy top-rank truncation against a character budget
(`MAX_FILE_CONTEXT_CHARS=3000`, `MAX_GLOBAL_CONTEXT_CHARS=4000`,
lines 22-23) — no MMR, no dedup beyond chunk-id-level.

**Why P2, and why sequence it last:** MMR-based diversity only pays off
once the ranked list feeding it is actually trustworthy — right now,
without a reranker (P0.1), the top-ranked candidates can already be
low-relevance, so adding diversity logic on top of an unreliable ranking
would be optimizing the wrong layer. Revisit after P0.1 ships.

**Status: DONE (2026-08-24).** User selected this as the one P2 item to
do now (P2.1/P2.2/P2.3 deferred). Implemented real MMR — not a text-
overlap heuristic — using each chunk's own embedding vector, which
turned out to already be present all the way through retrieval (verified
live before assuming: `chunk.embedding` is populated on every result from
`RetrievalPipeline.retrieve()`, survives `CrossEncoderReranker.rerank()`'s
`model_copy()`, and is only stripped at the very end by P1.2's API-layer
exclusion — internal consumers like this one never lose it).

Added `ContextSlicer._mmr_reorder()` (greedy MMR: relevance from incoming
rank order, diversity via cosine similarity between chunk embeddings,
`MMR_LAMBDA=0.7` keeps relevance dominant) and `_cosine_similarity()`.
Wired into all three public methods (`get_chunks_for_file`,
`get_chunks_for_module`, `get_global_context`) right before the existing
`_format()` budget-truncation step — reordering only, no filtering, so
`_format`'s character-budget logic is untouched. Falls back to the
original rank order unchanged if any chunk is missing an embedding.

Verified with a functional test (not just type-checking): built two
near-duplicate embeddings ranked 1st/2nd and one very different embedding
ranked 3rd — confirmed MMR keeps the top-ranked item first but promotes
the diverse 3rd-ranked item above the near-duplicate 2nd-ranked one.
Also verified the missing-embedding fallback, empty/single-item edges,
and cosine similarity correctness, then ran `get_global_context` against
the real indexed `canonyx` repo end-to-end (not mocked) to confirm no
regressions in the real path. Full test suite: 83/87 pass (same 4
pre-existing unrelated failures). Backend reloads cleanly.

---

## Recommended sequencing

1. ~~**P0.1 + P0.2 together**~~ **DONE 2026-08-24.**
2. ~~**P0.4** (chunk overlap)~~ **DONE 2026-08-24.**
3. ~~**P0.3** (semantic refiner gate)~~ **DONE 2026-08-24** — enabled for Gemini.
4. ~~**P1.1** (Pinecone rollback)~~ **DONE 2026-08-24.**
5. ~~**P1.2** (embedding payload bloat)~~ **DONE 2026-08-24.**
6. ~~**P1.3** (keyword-bag queries)~~ **DONE 2026-08-24.**
7. ~~**P2.4** (MMR context diversity)~~ **DONE 2026-08-24** — user's pick
   from the P2 set.
8. ~~**P2.1** (embedding model swap)~~ **EVALUATED, NOT PROCEEDING
   2026-08-24** — tested 5 candidate models directly; the working
   code-specific one underperformed the current model in direct
   comparison. Keeping `all-MiniLM-L6-v2`.
9. **P2.2, P2.3** — deferred by user choice (2026-08-24), not declined;
   each still needs its own explicit go-ahead whenever revisited.
   All of P0, P1, and P2.4 are complete; P2.1 is closed as evaluated.
