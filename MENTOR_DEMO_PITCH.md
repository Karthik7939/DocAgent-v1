# DocuBear — Mentor Demo Script

A page-by-page walkthrough for presenting the frontend to a mentor —
what to click, and what to say. Grounded in the actual pages that exist
in `frontend/app/` (not generic filler).

---

## Opening line (before touching the screen)

> "This is DocuBear — it watches a GitHub repo, and every time someone
> pushes code, it automatically generates and keeps README, Architecture,
> Changelog, and Security docs up to date, using a RAG pipeline so the AI
> is grounded in real code instead of guessing. Nothing gets published
> without a human approving it first."

That's the whole pitch in one breath. Everything else is proof.

---

## Suggested demo order

`Dashboard → Repos → Knowledge Base → Review → GitBook`

### 1. Dashboard (`/`)

**Show:** the landing page — KPI cards (Connected Projects, Tracked Docs,
Pending Updates, Reviewed Docs) and the Recent Documentation feed.

**Say:** "This is the command center — at a glance, how many repos are
connected, how many docs exist, and how many need review right now.
Nothing here is fake data — these numbers come straight from the actual
document store." Point at "Pending Updates" specifically: "This tells you
exactly which docs changed because of the *latest* commit, not just
which ones exist."

### 2. Repos (`/repos`)

**Show:** the connect-a-repo form, and the list of already-connected repos.

**Say:** "This is where you hook up a GitHub repository. Once connected,
every push triggers the pipeline automatically via webhook — no manual
trigger needed." If asked how: "It's an HMAC-signed webhook, so we verify
the push actually came from GitHub before doing anything."

### 3. Knowledge Base (`/knowledge-base`)

**This is the strongest technical page — spend the most time here.**

**Show:** the list of indexed repos with real vector counts, and the
"Add to KB" flow for one that isn't indexed yet.

**Say:** "Before the AI can write anything, it needs to actually
understand the codebase — that's what this page shows. Each repo gets
chunked at the function/class level, embedded, and stored in a vector
database (Pinecone). When you click 'Add to KB,' it clones the repo and
indexes it live — I can show that running." (Click "Add to KB" on a real
repo if there's time — it's a genuine live operation, not a mock.)

**If asked "how does it search / stay accurate":** "It's hybrid — vector
search *plus* keyword search *plus* a dependency graph, merged together,
then a second AI model reranks the results for actual relevance. That
reranking step was something I found broken and fixed myself — the
original setup was silently returning zero results for the most
important queries, and I caught it by testing live against real data,
not just trusting the code." *(Honest, credibility-building line — shows
debugging rigor, not just "I built a feature.")*

### 4. Review (`/review` → click into a document)

**Show:** pick a real generated doc, open it, show the diff view (old vs.
new content) and the tabbed preview/raw-markdown view.

**Say:** "This is the human-in-the-loop step — nothing publishes
automatically. When a doc changes, you see exactly what changed, side by
side, and you can approve it, request changes with a comment, or edit it
directly before approving. This exists specifically so the AI never gets
the final word."

### 5. GitBook (`/gitbook`)

**Show:** the connection settings (space ID, API token) and the publish
action.

**Say:** "Once a doc is approved, this is the last mile — it publishes
into GitBook so the docs live somewhere the team already reads, not
buried in the repo." (Skip the live demo if not currently connected to a
real GitBook space — describe it rather than risk a live error.)

---

## If asked "what's under the hood" (the credibility layer)

Have this ready — don't lead with it:

- **7-stage AI pipeline** (LangGraph): Preprocessing → Understanding →
  Planning → Documentation → Validation → Revision → Sync. Each
  generated doc is automatically **scored 0–100** on
  completeness/accuracy/consistency by a Validation agent before a human
  even sees it.
- **RAG grounding**: the AI doesn't hallucinate architecture — it
  retrieves real code chunks via hybrid search before writing anything.
- **Incremental, not wasteful**: editing one file in a 500-chunk repo
  only re-processes that file's chunks — not a full re-index every push.

## If asked for metrics / numbers

- Documentation quality score: automatically computed per doc, 0–100, by
  the Validation agent — not a made-up number, the system grades its own
  output.
- Real before/after: found and fixed a retrieval bug where the system's
  most important query returned 0 results — verified live, fixed, then
  re-verified live.
- Test suite: 83/87 passing (the 4 failures are pre-existing and
  unrelated, confirmed via isolation testing before this work started).

---

## One note before presenting

Don't over-promise on GitBook or the debug page unless confident they're
in a demo-ready state right now — better to describe them briefly than
hit a live error in front of a mentor. Test the actual demo flow once,
end to end, before presenting it live.
