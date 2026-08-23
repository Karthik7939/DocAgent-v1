# RAG & AI Agent Integration — Complete End-to-End Workflow

This document provides an exhaustive, step-by-step architectural breakdown of how **Retrieval-Augmented Generation (RAG)** and **Multi-Agent AI Systems** are connected, configured, and executed within the backend.

---

## 1. Executive Summary & Core Architectural Goal

In automated repository documentation systems, standard LLM (Large Language Model) context windows face two fundamental limitations:
1. **Context Blindness**: A single Git commit push only contains the diff (modified lines). The LLM does not know how imported helper functions, base classes, or surrounding architectural components in other files work.
2. **Context Overload & Hallucination**: Passing an entire multi-thousand-line codebase directly into an LLM prompt exceeds token limits, increases API cost, and causes signal degradation (hallucination).

### The Solution: RAG + Multi-Agent Synergy
This system bridges **RAG (Deterministic Code Context Retrieval)** with **Multi-Agent Orchestration (LangGraph & LangChain Reasoning)**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   GITHUB PUSH EVENT                                     │
└──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         RAG ENGINE (Deterministic Context)                              │
│   Git Diff ──► AST Chunking ──► Hybrid Vector/Keyword Search ──► ContextPackage         │
└──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │ (Injects ContextPackage)
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        SHARED MEMORY (Agent State Whiteboard)                           │
│                      [ shared_memory.rag_context_package ]                             │
└──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH MULTI-AGENT PIPELINE (Reasoning)                          │
│ Preprocessing ──► Code Understanding ──► Doc Planner ──► Doc Writer ──► Validation ──► Sync │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

* **RAG** acts as the **Information Retrieval Engine**: It scans the repository AST, computes semantic vector embeddings and lexical BM25 indices, traces dependency graphs, and produces grounded source code snippets (`ContextPackage`).
* **Agents** act as the **Cognitive Reasoning Engine**: Guided by LangGraph, specialized agents read the `ContextPackage` from `SharedMemory`, analyze architectural intent, generate structured documentation, validate quality rules, auto-revise flaws, and write markdown outputs to disk.

---

## 2. Deep-Dive: Overview of Components

### A. RAG Engine Architecture (`backend/rag/`)

The RAG engine converts source code into searchable mathematical representation and exact structural chunks:

| Subsystem | File Location | Responsibility & Implementation |
|---|---|---|
| **Code Parser** | `rag/chunkers/` | Uses `tree-sitter` (supporting Python, JS, TS, Java) to parse source code into an Abstract Syntax Tree (AST). Code is split along class, method, and function boundaries rather than raw line counts. |
| **Embeddings** | `rag/embeddings/` | Uses `sentence-transformers` with local model `all-MiniLM-L6-v2`. Computes dense 384-dimensional vector embeddings in-process without external API latency. |
| **Keyword Index** | `rag/indexers/` | Uses `rank-bm25` for exact symbol and identifier matching (e.g., specific function or variable names like `validate_jwt_token`). |
| **Vector Store** | `rag/indexers/` | Manages local `FAISS` indices on disk for similarity search. |
| **Dependency Graph** | `rag/indexing/` | Scans `import` statements to link dependent files (e.g., if `service.py` imports `utils.py`, `utils.py` chunks are linked as structural context). |
| **Query Refinement** | `rag/llm/` | Refines search queries via `Groq` LLM with a dual-key round-robin load balancer (`groq_client.py` & `multi_key_client.py`) for automatic rate-limit failover. |

---

### B. Multi-Agent Pipeline Architecture (`backend/agents/`)

The agent pipeline is orchestrated by a **LangGraph Compiled StateGraph** (`coordinator.py`), where each agent is an isolated node operating on a central `SharedMemory` object.

```
       [Start]
          │
          ▼
   PreprocessingAgent       (Scans repo structure, file sizes, extensions — No AI)
          │
          ▼
   UnderstandingAgent       (Consumes RAG ContextPackage + LLM prompt reasoning)
          │
          ▼
   DocumentationPlannerAgent (Computes dynamic document tree plan)
          │
          ▼
   DocumentationWriterAgent  (Generates Repo, Module, File, & Report docs in Markdown)
          │
          ▼
     ValidationAgent        (Evaluates quality score, broken links, coverage, syntax)
          │
          ├───► Validation PASSED/WARNING ──► SyncAgent ──► [Save to disk /generated_docs]
          │                                      ▲
          └───► Validation FAILED ───────────────┤
                     │                           │
                     ▼                           │
              RevisionAgent ─────────────────────┘
              (Auto-fixes flaws; retries up to max limit)
```

1. **Preprocessing Agent** (`agents/preprocessing/`): Scans raw file directory structure, counts lines/files, detects binary files, and initializes repository metadata without making LLM calls.
2. **Understanding Agent** (`agents/understanding/`): The core semantic analyzer. Reads the code context from RAG, calls LangChain LLM prompts, and populates `SharedMemory.understanding` (project purpose, architecture type, service inventory, API endpoints, dependency graphs).
3. **Documentation Planner Agent** (`agents/documentation/planner_agent.py`): Formulates a tailored execution plan determining which documents (Level 1 Repo, Level 2 Module, Level 3 File, and Technical Reports) to generate based on changed files.
4. **Documentation Writer Agent** (`agents/documentation/documentation_agent.py`): Transforms the architectural understanding into structured Markdown files (`README.md`, `ARCHITECTURE.md`, module guides, file details, technical reports).
5. **Validation Agent** (`agents/validation/`): Runs rule-based checks (Markdown formatting, headers, broken links, section completeness) and LLM quality scoring (0–100 rating).
6. **Revision Agent** (`agents/revision/`): Triggered conditionally if validation fails. Analyzes validation feedback and rewrites defective document sections before re-triggering validation.
7. **Sync Agent** (`agents/sync/`): Non-AI file writer that flushes validated Markdown documents to `generated_docs/<repo_name>/`.

---

## 3. The Connection Layer: How RAG and Agents Are Connected

The bridge connecting RAG and the Agents consists of three core software components:

```
 ┌──────────────────────┐        ┌──────────────────────┐        ┌──────────────────────┐
 │     RAG SERVICE      │        ┌  CONTEXT PACKAGE     │        │    SHARED MEMORY     │
 │ (services/rag_service)────────►│   (Data Contract)    ├───────►│ (agents/memory/...)  │
 └──────────────────────┘        └──────────────────────┘        └──────────┬───────────┘
                                                                            │
                                                                            ▼
                                                                 ┌──────────────────────┐
                                                                 │ UNDERSTANDING AGENT  │
                                                                 │  (_PrecomputedRag)   │
                                                                 └──────────────────────┘
```

### 1. `services/rag_service.py` (The Service Adapter)
Acts as the wrapper interface. When a push event is processed by `GitHubService`, it invokes:
```python
rag_result = self._rag_service.run_incremental(
    repo_path=local_path,
    repo_name=payload.repository.full_name,
    old_sha=payload.before,
    new_sha=payload.after,
    workflow_id=state.workflow_id,
)
```
The RAG Service runs the incremental pipeline and returns a `RAGExecutionResult` containing a `ContextPackage`.

### 2. `ContextPackage` (The Data Contract)
The data transfer object emitted by RAG and consumed by agents:
* **`retrieval_results`**: Array of ranked code chunks containing `content`, `file_path`, `start_line`, `end_line`, `retrieval_source` (FAISS vs BM25 vs Dependency Graph), and relevance scores.
* **`changed_files`**: List of added/modified/deleted files in the push.
* **`metadata`**: Performance metrics (retrieval time, total retrieved chunks).

### 3. `SharedMemory.rag_context_package` (The Whiteboard Attachment)
When `Coordinator.start_workflow(...)` is called, the `context_package` is stored directly inside `SharedMemory`:
```python
if context_package is not None:
    shared_memory.rag_context_package = context_package
```

### 4. 3-Tier Priority Retrieval inside `UnderstandingAgent`
When `UnderstandingAgent` executes, it checks context through a prioritized fallback mechanism (`_retrieve()`):

```python
# Priority 1: Use pre-computed ContextPackage attached to SharedMemory
if shared_memory.rag_context_package is not None:
    return _PrecomputedRagResult(shared_memory.rag_context_package)

# Priority 2: Direct on-demand RAG query (if RAG service is active but package missing)
if self._rag_service is not None:
    return self._rag_service.retrieve(query)

# Priority 3: Graceful degradation (no RAG available)
return _NoRagResult(query)
```

`_PrecomputedRagResult` formats the `ContextPackage` into LLM-ready markdown code blocks annotated with file paths, line numbers, and retrieval reasons, inserting exact source context directly into `UnderstandingAgent`'s system prompts.

---

## 4. End-to-End Execution Workflow (Step-by-Step)

Here is the exact step-by-step lifecycle from a developer pushing code to GitHub until the generated documentation is stored:

```
[ Developer Git Push ]
        │
        ▼ 1. HTTP POST Payload
[ FastAPI Webhook Endpoint: /api/webhook/github ]
        │
        ▼ 2. Validate HMAC-SHA256 Signature
[ GitHubService.process_push_event() ]
        │
        ▼ 3. Clone / Pull Repository to disk
[ GitService.sync_repository() ]
        │
        ▼ 4. Execute RAG Incremental Pipeline
[ RAGService.run_incremental() ]
        ├── Parse git diff (old_sha → new_sha)
        ├── Tree-sitter AST split modified files
        ├── Update FAISS vector index & BM25 keyword index
        └── Retrieve related code chunks ──► Returns ContextPackage
        │
        ▼ 5. Initialize SharedMemory & LangGraph Agent Pipeline
[ Coordinator.start_workflow(context_package=...) ]
        │  (Attaches context_package to shared_memory.rag_context_package)
        │
        ▼ 6. PreprocessingAgent Node
        │  (Scans directory metadata, populates file listing)
        │
        ▼ 7. UnderstandingAgent Node
        │  (Reads rag_context_package, queries LLM with prompt templates,
        │   populates project purpose, service inventory, API endpoints)
        │
        ▼ 8. DocumentationPlannerAgent Node
        │  (Analyzes understanding data + changed files, plans docs)
        │
        ▼ 9. DocumentationWriterAgent Node
        │  (Generates README.md, ARCHITECTURE.md, Module & File docs)
        │
        ▼ 10. ValidationAgent Node
        │  (Verifies links, code blocks, completeness score)
        │  ├─ FAILED ──► RevisionAgent (Rewrites flaws, loops back)
        │  └─ PASSED ──► Continue to SyncAgent
        │
        ▼ 11. SyncAgent Node
        │  (Writes generated markdown files to generated_docs/<repo>/)
        │
        ▼ 12. Workflow State Saved
[ Workflow COMPLETED ]
```

---

## 5. Failure Modes, Graceful Degradation & Resilience

The connection between RAG and Agents is engineered to be **resilient to system failures**:

| Failure Scenario | How the Connection Handles It | System Behavior |
|---|---|---|
| **RAG Indexing Error or Missing Dependencies** | `GitHubService` catches exceptions from `RAGService.run_incremental()` and sets `context_package = None`. | Agents log a warning and fallback to metadata-only reasoning (`_NoRagResult`). Documentation is still generated. |
| **Empty RAG Retrieval Results** | `_PrecomputedRagResult` formats an empty message banner. | `UnderstandingAgent` relies on Preprocessing file listings and commit metadata. |
| **Groq API Rate Limit (429)** | `multi_key_client.py` detects 429 status code. | Automatically switches to secondary Groq API key in round-robin fashion without failing the pipeline. |
| **LLM Output Parsing Failure** | Agents catch parsing errors, apply fallback default dataclass structures. | Prevents pipeline crash; logs warning in `AgentResult`. |
| **Validation Failure** | LangGraph conditional edge routes to `RevisionAgent`. | Auto-corrects documentation up to `MAX_REVISION_CYCLES` (default 3) before finalizing. |

---

## 6. Code Reference Map

| Component | File Path | Connection Functionality |
|---|---|---|
| **Webhook Entrypoint** | [webhook.py](file:///e:/PROJECTS/nokia/backend/app/api/webhook.py) | Receives GitHub push payload and delegates to `GitHubService`. |
| **Pipeline Orchestrator** | [github_service.py](file:///e:/PROJECTS/nokia/backend/services/github_service.py) | Calls Git sync, triggers RAG incremental run, passes `ContextPackage` to `Coordinator`. |
| **RAG Service Adapter** | [rag_service.py](file:///e:/PROJECTS/nokia/backend/services/rag_service.py) | Bridge wrapper between `rag/` module and the app layer. |
| **RAG Incremental Pipeline** | [incremental_pipeline.py](file:///e:/PROJECTS/nokia/backend/rag/pipeline/incremental_pipeline.py) | Parses commit diffs, updates vector stores, returns retrieved code context package. |
| **RAG Retrieval Engine** | [retrieval_pipeline.py](file:///e:/PROJECTS/nokia/backend/rag/pipeline/retrieval_pipeline.py) | Hybrid search executing FAISS + BM25 + Graph queries. |
| **Agent Orchestrator** | [coordinator.py](file:///e:/PROJECTS/nokia/backend/agents/coordinator/coordinator.py) | LangGraph graph manager. Injects `ContextPackage` into `SharedMemory`. |
| **Shared Whiteboard** | [shared_memory.py](file:///e:/PROJECTS/nokia/backend/agents/memory/shared_memory.py) | Stores `rag_context_package`, `understanding`, `plan`, `documentation`, and `validation`. |
| **Semantic Reasoning Agent** | [understanding_agent.py](file:///e:/PROJECTS/nokia/backend/agents/understanding/understanding_agent.py) | Consumes `_PrecomputedRagResult` context and builds structured domain knowledge. |
| **Documentation Writer** | [documentation_agent.py](file:///e:/PROJECTS/nokia/backend/agents/documentation/documentation_agent.py) | Converts understanding data into output markdown files. |
| **Disk Writer** | [sync_agent.py](file:///e:/PROJECTS/nokia/backend/agents/sync/sync_agent.py) | Persists generated documentation to disk. |

---

## 7. Summary

The integration between RAG and AI Agents in this project creates a closed-loop documentation generation system:
1. **RAG** grounds the AI in precise, real-world code context from the repository.
2. **SharedMemory** acts as the decoupled state bus where retrieved context is stored.
3. **LangGraph Agents** process the context step-by-step through semantic understanding, planning, documentation writing, quality validation, revision, and disk synchronization.
4. **Graceful Fallbacks** ensure that even if RAG or LLM sub-components fail, the system remains operational.
