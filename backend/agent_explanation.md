# Agent System — Plain English Explanation

This document explains every agent in the backend pipeline in simple words:
what it does, what frameworks it uses, and exactly how documentation ends up
in the `generated_docs/` folder.

---

## How the Whole System Works (Big Picture)

When a developer pushes code to GitHub:

```
GitHub Push Event
       ↓
  Webhook (FastAPI)        ← receives the push, replies 202 immediately
       ↓
  Background Thread        ← runs the full pipeline so GitHub doesn't time out
       ↓
  GitHubService            ← clones/pulls the repo, parses the commit
       ↓
  Coordinator (LangGraph)  ← runs each agent as a graph node, in order
       ↓
  ┌──────────────────────────────────────────┐
  │ 1. Preprocessing Agent  — no AI          │
  │ 2. Understanding Agent  — LangChain LLM  │
  │ 3. Documentation Agent  — LangChain LLM  │
  │ 4. Validation Agent     — rules + LLM    │
  │ 5. Revision Agent       — LangChain LLM  │
  │ 6. Sync Agent           — no AI, writes  │
  └──────────────────────────────────────────┘
       ↓
  generated_docs/<repo>/<file>.md   ← the final output
```

All agents share a single object called **SharedMemory**.
No agent talks to another agent directly — they just read and write to
this shared object. The **Coordinator** is the only one that runs agents.

---

## Frameworks Used

| Framework | What it does in this project |
|---|---|
| **LangChain** | Powers all LLM calls. Replaces raw HTTP requests to Groq/Gemini/OpenAI with a clean `ChatGroq` model and `StrOutputParser` chain. |
| **LangGraph** | Manages the Coordinator. The 6-agent pipeline is a compiled directed graph. Each agent is a "node". Edges control what runs next. |
| **FastAPI** | Receives GitHub webhooks, runs the HTTP server. |

---

## Shared Memory (`agents/memory/shared_memory.py`)

**What it is:** A Python dataclass that acts like a shared whiteboard for all agents.

**Sections it holds:**

| Section | Written by | Read by |
|---|---|---|
| `repository` | Coordinator (seeded at start) | All agents |
| `metadata` | Preprocessing Agent | Understanding, Documentation agents |
| `understanding` | Understanding Agent | Documentation, Validation agents |
| `documentation.file_docs` | Documentation Agent | Validation, Revision, Sync agents |
| `validation` | Validation Agent | Revision Agent |
| `revision` | Revision Agent | Coordinator |
| `workflow` | Coordinator + Sync Agent | Coordinator |

**Key fields for per-file docs:**
- `repository.added_files` — list of new files in the push
- `repository.modified_files` — list of changed files in the push
- `repository.author` — GitHub username of the developer who pushed
- `repository.push_timestamp` — date/time of the push (ISO-8601 format)
- `documentation.file_docs` — dict of `{file_path: markdown_content}`

---

## 1. Coordinator (`agents/coordinator/coordinator.py`)

**Purpose:** The manager. It builds and runs a **LangGraph directed graph** that
executes each agent as a node in the correct order.

**How it works (using LangGraph):**

The Coordinator builds a `StateGraph` at startup time. Think of it like a
flowchart where each box is an agent:

```
preprocessing → understanding → documentation → validation
                                                     │
                                       ┌─────────────┤
                                       │             │
                                (score PASSED)  (score FAILED,
                                       │         cycles < max)
                                       │             │
                                      sync        revision
                                       │             │
                                      END      (back to validation)
```

- If an agent **passes** → move to the next node
- If an agent **fails but is recoverable** → retry up to 3 times
- If validation **fails** → run revision, then re-validate (up to 2 cycles)
- If validation **still fails** after max cycles → stop with FAILED status

**LangGraph state (`PipelineState` TypedDict):**
Each node receives the full pipeline state and returns only the fields it changed.
LangGraph merges them automatically. The state contains:
- `shared_memory` — the SharedMemory object (agents read/write to this)
- `agent_workflow_state` — tracks timing, retries, logs
- `revision_cycles` — counts how many revision loops have run
- `error` — set when something goes wrong; nodes skip themselves if this is set

**The public API is unchanged:**
```python
summary = coordinator.start_workflow(
    repository_name="owner/repo",
    repository_path="repositories/owner_repo",
    branch="main",
    commit_sha="abc123",
    added_files=[...],
    modified_files=[...],
)
```

**Frameworks used:**
- `langgraph` — `StateGraph`, `END`, conditional edges
- `dataclasses` — for `AgentResult` and `WorkflowSummary`

> The Coordinator does NOT call any LLM. It only routes agents.

---

## 2. Preprocessing Agent (`agents/preprocessing/preprocessing_agent.py`)

**Purpose:** The scanner. It walks through the entire repository and collects
facts about it — without using any AI.

**What it does step by step:**
1. Walks every folder recursively using `os.walk`.
2. Skips ignored folders (`.git`, `node_modules`, `venv`, `__pycache__`, etc.)
   and ignored file types (`.pyc`, `.exe`, `.jpg`, etc.).
3. Detects **programming languages** — counts `.py`, `.js`, `.java`, etc. files
   and calculates their percentages.
4. Detects **frameworks** — opens `requirements.txt` or `package.json` and checks
   for keywords like `fastapi`, `django`, `react`, `next` in the first 4 KB.
5. Lists dependency files (`requirements.txt`, `package.json`, etc.) and extracts
   package names from them.
6. Lists config files (`.env`, `Dockerfile`, `docker-compose.yml`, etc.).
7. Identifies entry-point files (`main.py`, `app.py`, `index.js`, etc.).
8. Generates a text-based directory tree (like what you see in a terminal).
9. Counts files, directories, and total sizes.

**All results are stored in `shared_memory.metadata`.**

**Python packages used:**
- `os` — for `os.walk` to traverse directories
- `pathlib.Path` — for easy file path handling
- `json` — for reading `package.json`
- `logging` — for writing logs

> No AI / LLM is used here. It is purely rule-based.

---

## 3. Understanding Agent (`agents/understanding/understanding_agent.py`)

**Purpose:** The reader. It uses the LLM to understand what the code *means* —
the architecture, modules, APIs, and data flow.

**Note on RAG:** This agent supports an optional RAG (Retrieval-Augmented
Generation) service. When `rag_service=None` (current setting), it reasons
purely from the metadata collected by the Preprocessing Agent. When RAG is
provided in the future, it will also search the actual source code for context.

**What it does step by step:**
1. (Optional) If a RAG service is configured: indexes the repository into a
   vector store and retrieves relevant code chunks per query.
2. If no RAG: uses placeholder context with a note that RAG is not configured.
3. **Sends prompts to the LLM** (via `LLMService.generate()`) and asks it to
   explain the project in a structured format.
4. Parses the LLM response into Python objects:
   - `project_summary` — one-paragraph description
   - `architecture_type` — e.g. "Layered / MVC / Microservices"
   - `modules` — list of named modules with their responsibilities
   - `services` — list of services with inputs/outputs
   - `apis` — list of HTTP endpoints (method, route, purpose)
   - `folder_responsibilities` — what each folder is for
   - `dependency_graph` — which module depends on which
5. Builds a lightweight `knowledge_graph` (nodes = modules/services/APIs,
   edges = dependencies).

**All results are stored in `shared_memory.understanding`.**

**Frameworks used:**
- `langchain` (via `LLMService`) — the LLM is called through a LangChain chain
- `logging`, `time` — standard library
- `prompts/understanding_prompt.py` — prompt templates

---

## 4. Documentation Agent (`agents/documentation/documentation_agent.py`)

**Purpose:** The writer. For every file that was added or changed in the push,
it reads the file content and asks the LLM to describe it — producing one `.md`
file per source file.

**What it does step by step:**
1. Reads `shared_memory.repository.added_files` and `modified_files` — these come
   from the GitHub webhook payload (GitHub tells us exactly which files changed).
2. Merges them into one list, labelling each file as `"Created"` or `"Updated"`.
3. For each file:
   - Reads the raw file content from the local repository clone on disk.
   - If the file is larger than 12,000 characters, trims it so the LLM doesn't
     get overloaded.
   - Skips empty files or files that don't exist.
   - Builds a prompt using `FILE_DOC_PROMPT` — fills in the file path, content,
     change status, developer name, and push timestamp.
   - Sends the prompt to the LLM and gets back a Markdown document.
   - Cleans up the Markdown (removes extra blank lines, balances code fences).
4. Stores all results in `shared_memory.documentation.file_docs` as a dict:
   ```python
   {"app/api/webhook.py": "# `app/api/webhook.py`\n## Overview\n..."}
   ```

**Frameworks used:**
- `langchain` (via `LLMService.generate()`) — sends prompt, gets Markdown back
- `pathlib.Path` — for reading file contents
- `prompts/documentation_prompt.py` — the `FILE_DOC_PROMPT` template
- `agents/documentation/markdown_formatter.py` — cleans up LLM output

**What the generated document looks like:**
```markdown
# `sum.py`

## Overview
This file calculates the average of a list of marks...

## Change Summary
This file was **Created** in the latest push. It introduces...

## Developer
**Blrm123**
**2026-07-21T00:15:26+05:30**

## Key Components
* **marks** — a list to store marks

## Dependencies
Not applicable.

## Notes
The script prompts the user for input...
```

---

## 5. Validation Agent (`agents/validation/validation_agent.py`)

**Purpose:** The quality checker. It reviews each generated `.md` file and
scores its quality — without modifying anything.

**What it does:**
1. Takes every file doc from `shared_memory.documentation.file_docs`.
2. Runs **rule-based checks** on each one (no LLM needed for this):
   - Is the document empty?
   - Are required sections present? (`## Overview`, `## Change Summary`,
     `## Key Components`)
   - Are all code fences balanced (equal number of triple backticks)?
   - Are there any empty headings?
3. Also runs **LLM-based checks** (via `LLMService.generate()`):
   - Is the content accurate compared to what we know about the repo?
   - Are there any hallucinated (made-up) facts?
4. Calculates an overall quality score (0–100) weighted by:
   - Completeness (25%) — are all sections present?
   - Accuracy (30%) — is the content correct?
   - Consistency (20%) — no hallucinations?
   - Formatting (10%) — balanced fences, no empty headings?
   - Readability (5%) — not too many warnings?
5. Sets status to:
   - `PASSED` (score ≥ 85)
   - `PASSED_WITH_WARNINGS` (score ≥ 70)
   - `FAILED` (score < 70) → triggers the Revision Agent

**Result stored in `shared_memory.validation`.**

**Frameworks used:**
- `langchain` (via `LLMService.generate()`) — LLM content validation
- `re` — regex checks for code fences and heading patterns
- `dataclasses`, `logging`, `time` — standard library

---

## 6. Revision Agent (`agents/revision/revision_agent.py`)

**Purpose:** The fixer. If the Validation Agent found issues, this agent
tries to correct them automatically.

**What it does:**
1. Reads the validation report from `shared_memory.validation`.
2. If status is `PASSED` → does nothing (no revision needed).
3. For each file doc that had errors:
   - Sends the document + the list of issues to the LLM with a revision prompt.
   - The LLM rewrites the problematic parts.
   - If the LLM is unavailable, applies rule-based fixes instead:
     balances code fences, removes extra blank lines, removes trailing whitespace.
4. Writes the fixed content back into `shared_memory.documentation.file_docs`.
5. Records revision history in `shared_memory.revision` (what was changed, when).
6. Returns control to the Coordinator, which re-runs Validation.

**Frameworks used:**
- `langchain` (via `LLMService.generate()`) — LLM-powered rewrites
- `re` — regex-based formatting fixes
- `logging`, `time`, `datetime` — standard library

---

## 7. Sync Agent (`agents/sync/sync_agent.py`)

**Purpose:** The writer to disk. This is the **only** agent that saves files
to the filesystem. All other agents only work in memory.

**What it does:**
1. Reads `shared_memory.documentation.file_docs`.
2. For each entry `{file_path: markdown_content}`:
   - Calculates the output path by appending `.md` to the source file path:
     ```
     app/api/webhook.py  →  generated_docs/Blrm123_NOKIA/app/api/webhook.py.md
     ```
   - Creates any missing parent directories.
   - Writes the Markdown content to that file.
   - If the file already exists, **overwrites it** — this is how updates work.
3. Reports how many files were written, skipped, or updated.

**Python packages used:**
- `pathlib.Path` — for all file I/O
- `dataclasses`, `logging`, `time` — standard library

> This agent mirrors the repository's directory structure inside `generated_docs/`.
> No LLM is used here.

---

## LLM Service (`services/llm_service.py`)

**Purpose:** The single place where all LLM communication happens.
All agents call `llm_service.generate(prompt)` — they don't care which
LLM provider is being used.

**How it works:**
1. On startup, it checks which API key is available in `.env`.
2. Builds the appropriate LangChain chat model:
   - **Groq** (if `GROQ_API_KEY` is set) → `ChatGroq` from `langchain-groq`
   - **Gemini** (if `GEMINI_API_KEY` is set) → `ChatGoogleGenerativeAI`
   - **OpenAI** (if `OPENAI_API_KEY` is set) → `ChatOpenAI`
   - **No key** → returns a placeholder message and logs a warning
3. Every `generate(prompt)` call runs this LangChain chain:
   ```
   HumanMessage(prompt) → ChatGroq → StrOutputParser → plain string
   ```

**Frameworks used:**
- `langchain-groq` — `ChatGroq` model
- `langchain-core` — `HumanMessage`, `StrOutputParser`

> LangChain handles retries, connection errors, and output parsing automatically.

---

## RAG Service (`rag/rag.py`)

**Status: Ready but not connected yet.**

The `RAGService` class is fully implemented and ready to use. It will:
1. Read all source files in the repository.
2. Split them into small chunks.
3. Convert each chunk into a vector embedding (a list of numbers representing meaning).
4. Store them in a local vector database.
5. When given a query, retrieve the most relevant chunks.

It is currently not connected to the `UnderstandingAgent` (`rag_service=None`).
When the RAG implementation is provided, simply pass it in:
```python
rag = RAGService(top_k=5)
understanding = UnderstandingAgent(rag_service=rag, llm_client=llm_service)
```

---

## Flow Summary (How One `.md` File Gets Created)

```
1.  Developer pushes code to GitHub
2.  GitHub sends a POST request to /webhook/github
3.  webhook.py validates the request and immediately replies 202 OK
4.  A background thread starts the pipeline
5.  GitHubService clones/pulls the repo, extracts:
      added_files, modified_files, author, push_timestamp
6.  Coordinator seeds SharedMemory with all that info
7.  LangGraph starts the pipeline graph:

    Node 1: PreprocessingAgent scans the repo
            → fills SharedMemory.metadata

    Node 2: UnderstandingAgent calls LLM with metadata context
            → fills SharedMemory.understanding

    Node 3: DocumentationAgent reads each changed file, calls LLM
            → fills SharedMemory.documentation.file_docs

    Node 4: ValidationAgent checks each doc for quality
            → fills SharedMemory.validation (score 0-100)

    (if FAILED and cycles < 2)
    Node 5: RevisionAgent fixes issues using LLM
            → updates SharedMemory.documentation.file_docs
            → returns to Node 4 for re-validation

    (if PASSED or PASSED_WITH_WARNINGS)
    Node 6: SyncAgent writes each file_doc to disk:
            generated_docs/<owner>_<repo>/<file_path>.md

8.  Coordinator returns WorkflowSummary (status, docs written, timing)
```

**That's it.** Every file the developer pushed gets its own `.md` documentation
file, including who wrote it and when.
