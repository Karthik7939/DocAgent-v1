# Fix Plan

## Agent pipeline audit (2026-08-24) — backend/agents/

Full read-through of coordinator, preprocessing, understanding, documentation
(+ planner/context_slicer/file_extractor/markdown_formatter), validation,
revision, sync, and shared_memory. 5 real bugs found and fixed:

1. **`sync_agent.py` `_file_doc_path`** — doc keys without a `.md` suffix
   produced a doubled, self-nesting output path instead of the documented
   mirrored structure. Dormant today (all current doc keys end in `.md`) but
   part of the class's public contract. Fixed; updated 4 stale test
   assertions in `test_sync.py` that had encoded the bug as expected.
2. **`validation_agent.py` `_validate_structure`** — `total_expected` was
   hardcoded to 3 regardless of doc type, so a top-level doc (e.g. README.md)
   missing its only required section scored ~66.7 instead of 0. Fixed to use
   the actual `expected` list length.
3. **`validation_agent.py` `_compute_overall_score`** — `WEIGHT_COVERAGE`
   (0.10) was declared but never applied; weights summed to 0.90, capping
   every quality score at 90/100 regardless of actual quality. Fixed by
   normalizing against the weights actually applied.
4. **`revision_agent.py` `_group_issues`** — assumed every issue string is
   `"DocType: message"`, but LLM-produced errors/hallucinations have no such
   prefix, and the colon-free fallback used a stale doc-name list that no
   longer matches real keys (`README.md` vs `README`). Net effect: LLM-driven
   correction of validation-flagged errors almost never ran; only rule-based
   formatting fixes did. Fixed to match against real document keys the same
   way `formatting_issues` already did correctly.
5. **`coordinator.py` / `workflow_state.py`** — `_planner_node` was tagged
   with `AgentName.DOCUMENTATION`, the same enum value as the real
   `DocumentationAgent` node, so the planner's timing/log entries were
   silently overwritten when the doc node ran. Added a distinct
   `AgentName.PLANNER` value.

Also flagged (not fixed — would be a feature, not a bug fix): `planner_agent.py`'s
output (`shared_memory.plan`) and `file_extractor.py`'s `FileContentExtractor`
class are both fully dead — written/defined but never read/used anywhere else
in `agents/`.

Verified: syntax-checked all edited files, ran the affected pytest suites
(35 passed; `test_documentation.py`'s 4 pre-existing failures confirmed
unrelated via `git stash`), and confirmed the backend reloads cleanly
(`GET /health` OK before and after).


## Fix 1: CRITICAL – RAG crashes when Gemini is used (no Gemini in RAG LLM factory)

**Root cause:** `rag/llm/factory.py` only knows `groq`, `ollama`, `grok`. 
When `GEMINI_API_KEY` is set but `GROQ_API_KEY` is absent, the RAG semantic query 
refinement crashes with ValueError("Unsupported LLM provider: groq").

**Two-part fix:**
a) Create `rag/llm/gemini_client.py` implementing `BaseLLM` using google-generativeai
b) Add `gemini` case to `rag/llm/factory.py`
c) Add `gemini_api_key` field to `rag/config/settings.py` with alias GEMINI_API_KEY
d) Set `RAG_LLM_PROVIDER=gemini` in `.env`

## Fix 2: MAJOR – Frontend `lib/db.ts` loses all repos on restart (in-memory only)

**Root cause:** `let repos: Repo[] = []` is a module-level variable; every server 
restart wipes connected repositories.

**Fix:** Replace with a file-backed JSON store using Node.js `fs` module.
The store reads from `data/repos.json` on first access and writes on every mutation.
This is the simplest no-dependency fix.

## Fix 3: Frontend Connection UI shows fake "Webhook active" badge

**Root cause:** The badge is hardcoded to `true` in `app/api/repos/route.ts`.

**Fix:** 
a) Add a backend status endpoint `GET /api/rag/status/{repo_name}` that returns 
   real Pinecone vector count, last indexed commit, and webhook reception status.
b) Update `RepoCard` to fetch and display real status after bootstrap completes.

**Status: DONE.** `GET /api/rag/status/{repository_name}` (backend/app/api/rag.py)
returns real Pinecone vector count + indexed flag, proxied via
`frontend/app/api/rag/status/route.ts`. Webhook reception is now tracked
separately and honestly: `POST /api/repos` creates repos with
`webhookActive: false`; `frontend/app/api/webhook/route.ts` calls the new
`db.markWebhookReceived()` (frontend/lib/db.ts) to flip it to `true` with a
`lastWebhookAt` timestamp only once a real GitHub push event is processed.
`RepoCard.tsx` badge now reads `repo.webhookActive`/`lastWebhookAt` instead of
an always-true value.

---

## Issues found during full project audit (2026-08-24)

### Issue A — CRITICAL: `next build` fails to type-check (`lib/db.ts`)
`db.listRepos()`'s auto-discovery branch built a `Repo` literal with a `url`/
`status`/`createdAt` shape that doesn't match the `Repo` interface
(`owner`, `name`, `connectedAt`, `webhookActive` required). `npx tsc --noEmit`
failed with `TS2353: 'url' does not exist in type 'Repo'`, i.e. `next build`
was broken. **Fixed:** the object now derives `owner`/`name` from the repo's
full name and sets `connectedAt`/`webhookActive: false` per the real interface.

### Issue B — RepoCard `IndexBadge` component defined inside render (eslint error)
`function IndexBadge() {...}` was declared inside the `RepoCard` component body
and instantiated as `<IndexBadge />` on every render — React treats this as a
new component type each render (remounts, `react-hooks/static-components`
lint error). **Fixed:** converted to a plain JSX expression (`indexBadge`)
computed inline instead of a nested component.

### Issue C — Fix 3 was only half-applied (see above): webhook badge was real
for indexing but still hardcoded `true` for webhook reception. **Fixed** as
described in Fix 3 status above.

### Issue D — Knowledge Base panel showed already-indexed repos as "not indexed"
`toSlashForm()` in `KnowledgeBasePanel.tsx` blindly replaced the *first*
underscore in a Pinecone namespace name with `/`, assuming every namespace is
stored as `owner_repo`. Namespaces indexed via the manual "Add to KB" /
`index-repo` path are stored using the raw name the user typed, which can
already be in `owner/repo` slash form with underscores inside the repo name
itself (e.g. `Blrm123/Doc_generation_test`). Normalizing that name corrupted
it into `Blrm123/Doc/generation_test`, which no longer matched the connected
repo's `fullName`, so the UI showed the repo simultaneously as "not indexed"
(top section) and "indexed" (bottom section) — reported by the user with a
screenshot. **Fixed:** `toSlashForm()` now only rewrites the underscore form;
if the name already contains a `/`, it's left untouched.

### Known, not fixed — lint-only, no functional impact
`npx eslint .` still reports pre-existing issues out of scope for this pass:
- `react-hooks/set-state-in-effect` in `RepoCard.tsx`, `KnowledgeBasePanel.tsx`,
  and `app/gitbook/page.tsx` — standard "fetch on mount" pattern; functionally
  correct, just flagged by the stricter React Compiler ESLint rule.
- Several `@typescript-eslint/no-explicit-any` in `ApprovalActions.tsx`,
  `DocPreview.tsx`, `DocReviewClient.tsx`, `app/gitbook/page.tsx`.
- `require()` import in `tailwind.config.ts`.
- Unused imports (`Link`, `DocVersion`, `Repo`) in a few pages.
These are stylistic and pre-date this pass; recommend a separate cleanup task
if desired.
