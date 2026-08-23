# Fix Plan

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
