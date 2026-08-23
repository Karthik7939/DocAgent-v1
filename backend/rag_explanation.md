# RAG Integration — Complete Explanation

This document explains the RAG (Retrieval-Augmented Generation) subsystem in simple words: what it is, how it works, how it integrates with the AI agents, and how the underlying pipelines function.

---

## 1. What is RAG in this Project?

RAG stands for **Retrieval-Augmented Generation**. 

In this system, when a developer pushes code, the AI agents need to document it. However, the changes in a single push might depend on code located in other files that weren't modified in the commit. 

For example, if a developer edits a function call, the AI needs to know:
*   How that function is defined in other files.
*   What classes or helper utilities are imported.
*   Where else in the repository this function is called.

**Without RAG**, the AI agents are blind to the rest of the repository and can only read the changed files and basic metadata (file names).
**With RAG**, the system searches the entire repository for semantic context, gathers related code snippets, and injects them into the AI's prompts, enabling precise, context-aware documentation.

---

## 2. RAG Directory Structure

The RAG logic is divided into two parts:
1.  **The Engine (`rag/`)**: Pure library code doing chunking, embedding, indexing, parsing, and query refinement.
2.  **The Adapter (`services/rag_service.py`)**: Connects the RAG engine to the FastAPI endpoints and the AI agent pipeline.

```
backend/
├── rag/
│   ├── pipeline/
│   │   ├── bootstrap_pipeline.py    ← Builds initial indexes from scratch (FAISS + BM25)
│   │   ├── incremental_pipeline.py  ← Updates indexes on push event (only parses changed files)
│   │   └── retrieval_pipeline.py    ← Queries the vector + keyword indexes for context
│   ├── rag/
│   │   ├── chunkers/                ← Splits code files into semantic chunks
│   │   ├── embeddings/              ← Converts text chunks into mathematical vectors
│   │   ├── indexers/                ← Manages FAISS vector store & BM25 keyword index
│   │   └── parsers/                 ← AST code parser (tree-sitter) to find classes/methods
│   ├── llm/
│   │   ├── groq_client.py           ← Groq API client (for semantic query refinement)
│   │   ├── multi_key_client.py      ← Round-robin load balancer for dual Groq API keys
│   │   └── factory.py               ← Decides single-key vs. dual-key load balancer
│   ├── config/
│   │   └── settings.py              ← Reads RAG_* environment variables
│   └── storage/                     ← [Runtime] Stored indexes per repository (.index, .json)
│
├── services/
│   └── rag_service.py               ← The bridge wrapper. Handles errors & degrades gracefully
│
└── app/
    └── api/
        └── rag.py                   ← FastAPI router (/api/rag/bootstrap, /api/rag/retrieve)
```

---

## 3. Core Technical Components

To deliver accurate code retrieval, the RAG engine uses a **hybrid retrieval** strategy:

```
                  ┌───────── Code Chunk ─────────┐
                  │                              │
                  ▼                              ▼
      ┌───────────────────────┐      ┌───────────────────────┐
      │  Semantic Embeddings  │      │   Keyword Indexing    │
      │ (sentence-transformers)│      │       (BM25)          │
      └───────────┬───────────┘      └───────────┬───────────┘
                  │                              │
                  ▼                              ▼
             FAISS Vector                   Lexical Text
                Match                           Match
                  │                              │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   Dependency Graph    │  ← Structural Context
                     │ (Import relationships)│
                     └───────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  Final Context Chunks │
                     └───────────────────────┘
```

### A. Code Parsing & Chunking (`tree-sitter`)
*   Files are parsed into an **Abstract Syntax Tree (AST)** using `tree-sitter` (supporting Python, JavaScript, TypeScript, and Java).
*   Instead of splitting text by character count (which breaks code logic), it splits by class, function, or method definitions. This preserves the structural context of the code.

### B. Semantic Embeddings (`sentence-transformers`)
*   Converts text chunks into numerical vectors using a local `all-MiniLM-L6-v2` model.
*   Runs locally inside the Python process (no external API calls or servers like Ollama are needed).
*   Enables **semantic search** (finding "user auth" when the query is "verify token").

### C. Keyword Indexing (`rank-bm25`)
*   Indexes exact words and symbol names using BM25.
*   Enables **exact match search** (finding the exact line containing `def validate_jwt_token`).

### D. Dependency Graph
*   Scans imports inside files to build a structural graph of how modules relate to one another.
*   If `file_a.py` imports `file_b.py`, the system fetches additional context from `file_b.py` when retrieving information about `file_a.py`.

### E. LLM Client (`groq` with dual-key failover)
*   Refines incoming natural language search queries before querying the indexes.
*   **Dual-Key Load Balancer**: Uses your `GROQ_API_KEY` (primary) and an optional `RAG_GROQ_API_KEY_2` (secondary). It distributes requests 50/50 and automatically switches keys if one hits a `429 Rate Limit` from Groq, providing high scalability.

---

## 4. The RAG Life Cycle (Dual Path)

The RAG subsystem handles data in two distinct ways:

### Path A: Repository Bootstrapping (Full Index)
Executed once when a repository is added or synced.
1.  A POST request hits `/api/rag/bootstrap`.
2.  `RAGService.index_repository()` triggers the `BootstrapPipeline`.
3.  The engine parses every file, computes embeddings, and builds the FAISS, BM25, and dependency-graph databases.
4.  The databases are saved to the `rag/storage/` folder on disk.

### Path B: Webhook Push (Incremental Update)
Executed automatically every time a developer pushes code to GitHub.
1.  FastAPI receives the GitHub webhook and calls `GitHubService.process_push_event()`.
2.  The Git service pulls the latest changes.
3.  **Incremental Sync**: `RAGService.run_incremental(old_sha, new_sha)` is triggered.
4.  The `IncrementalPipeline` scans only the files that changed between the two commits:
    *   Removes deleted chunks from the indexes.
    *   Adds/recomputes embeddings only for new or modified code.
5.  **Retrieval**: The system queries the updated index for the exact context of the push and builds a `ContextPackage` containing the relevant source code.
6.  The `ContextPackage` is forwarded to the AI Agent Coordinator.

---

## 5. How RAG Integrates with the AI Agents

```
           GitHub Service (Push Event)
                     │
                     ▼
             RAG Incremental Run
                     │
                     ▼
              ContextPackage
                     │
                     ▼
            Coordinator.start_workflow(context_package)
                     │
                     ▼
         [SharedMemory.rag_context_package] (Whiteboard)
                     │
                     ├──────────────────────────┐
                     ▼                          ▼
            PreprocessingAgent         UnderstandingAgent
                                       (Reads from SharedMemory first)
                                       (Falls back to direct retrieve if empty)
```

1.  **Shared Memory**: The Coordinator stores the `ContextPackage` generated by the RAG pipeline directly inside the `SharedMemory` object under the `rag_context_package` field.
2.  **Priority-Based Retrieval**: When `UnderstandingAgent` runs to analyze what changed in the repository, it follows a 3-step retrieval priority:
    *   **Priority 1 (Pre-computed Context)**: It checks if `SharedMemory.rag_context_package` exists. If so, it immediately uses this context. This is highly efficient because it avoids making redundant database queries during agent runs.
    *   **Priority 2 (On-demand Retrieval)**: If no pre-computed package is in memory, it queries the `RAGService` directly for the changed files.
    *   **Priority 3 (Graceful Degradation)**: If the RAG service fails (e.g. if files are missing or index is corrupted), it falls back to a metadata-only stub (`_NoRagResult`). The agent logs a warning but **never crashes** — documentation generation will still complete using the code changes alone.

---

## 6. Settings & Configuration

The RAG subsystem is configured in your `.env` file:

```env
# --- Embeddings (Local, runs in-process) ---
RAG_EMBEDDING_PROVIDER=sentence-transformers
RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_ENABLE_EMBEDDING_CACHE=true

# --- LLM Settings (Refines queries via Groq API) ---
RAG_LLM_PROVIDER=groq
RAG_LLM_MODEL=llama-3.3-70b-versatile
RAG_GROQ_MODEL=llama-3.3-70b-versatile
RAG_ENABLE_SEMANTIC_QUERY_REFINEMENT=true

# --- Dual-Key load balancing ---
# Uses GROQ_API_KEY (from the main app) as the primary key.
# Add your second key here to double your rate limit and enable failover:

# --- Storage ---
RAG_STORAGE_ROOT=rag/storage
```

---

## 7. How to run and test RAG

### Step 1: Start the server
Use the startup script `start.ps1` to prevent Uvicorn from reloading when RAG writes index files or syncs repositories:
```powershell
.\start.ps1
```

### Step 2: Bootstrap your repository
Make a POST request to index your repository (use your actual values):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/rag/bootstrap" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"repository_name": "username/repo", "repository_path": "repositories/repo", "commit_sha": "HEAD"}'
```
*(You can also run this directly in the browser via `http://localhost:8000/docs`)*

### Step 3: Trigger a push webhook
Once bootstrapped, push changes to your GitHub repo. The server will catch the webhook, run the incremental indexer, pass context to the `UnderstandingAgent`, and output your documentation into `generated_docs/`.
