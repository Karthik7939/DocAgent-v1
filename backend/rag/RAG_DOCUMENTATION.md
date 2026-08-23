# RAG Module Documentation

This document explains the purpose, structure, and behavior of the `backend/rag` package. The package implements a repository-aware Retrieval Augmented Generation system that can index source code, detect commit-level semantic changes, retrieve relevant context, and package that context for downstream automation.

## High-Level Purpose

The RAG module exists to answer one core question:

> Given a repository and a code change, what existing code, documentation, and dependency context should an agent see before generating documentation or analysis?

To do that, it provides:

- Full repository bootstrapping into searchable indexes.
- Incremental updates after commits.
- Semantic chunking of code and documentation.
- Dense embedding generation and caching.
- FAISS vector retrieval.
- BM25 keyword retrieval.
- Dependency graph retrieval.
- Hybrid ranking with Reciprocal Rank Fusion.
- Structured Pydantic schemas for changes, chunks, queries, retrieval results, graphs, and context packages.
- Optional LLM-backed semantic change classification.
- Workflow event hooks for progress reporting and cancellation.

## Running the System

The RAG module runs inside the FastAPI backend; start the backend from the
`backend` directory after configuring its environment.

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
Copy-Item .env.example .env   # Windows PowerShell
# cp .env.example .env        # macOS/Linux

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The service exposes Swagger UI at `http://localhost:8000/docs`. Configure
`.env` before starting it. In particular, set repository/workflow locations
as needed and configure the selected embedding and optional LLM providers.
The `RAG_`-prefixed settings in `.env.example` control retrieval limits,
similarity thresholds, storage, embeddings, and semantic-refinement behavior.

Before retrieval can return useful data, the repository must have indexes. Use
the bootstrap endpoint once after the repository has been cloned or synced:

```http
POST /api/rag/bootstrap
Content-Type: application/json

{
  "repository_name": "owner/repository",
  "commit_sha": "<commit-sha>"
}
```

This queues `BootstrapPipeline`, which produces the FAISS, BM25, dependency
graph, and embedding-cache artifacts. Later GitHub push webhooks automatically
queue `RAGPipeline` for incremental indexing and context retrieval.

## System Flow and Entry Points

```text
Bootstrap request --> BootstrapPipeline --> persistent indexes
GitHub push webhook --> GitHubService --> RAGPipeline
                                           |
                                           +--> IncrementalPipeline
                                           |     +--> GitDiff + ASTDiff
                                           |     +--> SemanticChange
                                           |     +--> QueryBuilder --> SemanticQuery
                                           |     `--> IncrementalIndexer --> refreshed indexes/graph
                                           |
                                           `--> RetrievalPipeline
                                                 +--> HybridRetriever
                                                 `--> ContextBuilder --> ContextPackage

Agent in same process <-- ContextPackage (PipelineResult)
External agent -- POST /api/rag/retrieve --> ContextPackage JSON
```

The main RAG entry points are:

- `BootstrapPipeline` for a full initial index build.
- `RAGPipeline` for a commit-driven incremental update followed by retrieval.
- `RetrievalPipeline` for retrieval from an already-created `SemanticQuery`.
- `POST /api/rag/retrieve` for synchronous, API-based retrieval.

`POST /api/rag/retrieve` is registered in `app/api/rag.py` under the
`/api/rag` prefix. It accepts a `SemanticQuery`, loads the corresponding
repository vector and BM25 stores, and returns a `ContextPackage`.

## How a Semantic Query Is Created

For a GitHub commit, `IncrementalPipeline.process_commit()` constructs the
query before it updates the indexes. It:

1. Uses `GitDiff` to identify added, modified, deleted, and renamed files.
2. Uses `ASTDiff` and `SymbolExtractor` to identify changed symbols, imports,
   calls, structural operations, data flows, and rename mappings.
3. Uses `SemanticChange` to classify the change and gather implementation
   evidence.
4. Calls `QueryBuilder.build()`, which expands dependency context, derives
   technical/domain concepts and workflow steps, optionally applies
   LLM-assisted semantic refinement, derives keywords, and composes natural
   language `query_text`.

The resulting immutable `SemanticQuery` carries the repository and commit,
query text, changed files, modified and renamed symbols, BM25 keywords,
semantic context/sections, clustered evidence, extensions, languages,
dependency files, `top_k`, similarity threshold, and optional metadata
filters. The master pipeline also stores a JSON form of that query in workflow
state when a workflow ID is available.

An API client may also construct and submit this same schema directly. At a
minimum, `repository`, `commit_sha`, and non-empty `query_text` are required;
the optional structured fields improve filtering and dependency retrieval.

## How Context Retrieval Works

`RetrievalPipeline.retrieve(query)` loads the vector and BM25 indexes and
attempts to load the dependency graph. `HybridRetriever.retrieve_for_change()`
then:

1. Embeds `query.query_text` and performs FAISS dense retrieval.
2. Performs BM25 keyword retrieval when query keywords are present.
3. Retrieves dependency-neighbor chunks when dependency context is available.
4. Applies repository, activity, metadata, language, duplicate, and score
   filtering.
5. Merges ranked channels with Reciprocal Rank Fusion (RRF).
6. Passes the ranked results to `ContextBuilder`, which creates the final
   `ContextPackage`.

If the dependency graph cannot be initialized, the pipeline retries lazily; if
that still fails, it returns a valid but empty `ContextPackage` rather than
raising a retrieval failure.

## Context Package Contract and Agent Integration

`ContextPackage`, defined in `schemas/context.py`, is the boundary between
RAG and an agent. It contains:

- `repository` and `commit_sha` identifying the scope.
- `query`, the complete `SemanticQuery` and its change evidence.
- `changed_files`, the commit file paths.
- `retrieval_results.results`, an ordered list of `RetrievalResult` objects.
- `metadata`: generation timestamp, retrieval duration, changed-file count,
  and retrieved-chunk count.

Every `RetrievalResult` provides a `chunk`, similarity score, final rank,
retrieval source (`faiss`, `bm25`, `dependency`, or `hybrid`), and a
human-readable retrieval reason. Each chunk includes its source `content`,
optional `summary` and embedding, plus metadata: chunk ID, repository, file
path, language, code/documentation type, symbol and parent symbol, line range,
index commit SHA, content hash, token count, active state, and creation time.

### Same-process agent

An agent invoked by the webhook flow can receive the package directly from
`RAGPipeline.run()`:

```python
result = rag.run(old_commit_sha, new_commit_sha, workflow_id=workflow_id)
if result.success and result.context_package and result.context_package.has_context:
    package = result.context_package
    for item in package.retrieval_results.results:
        source = item.chunk.metadata.file_path
        text = item.chunk.content
        # Add source, line range, text, and retrieval_reason to the agent prompt.
```

The current `GithubService._run_rag_pipeline_async()` runs this pipeline but
does not yet call an agent or persist the resulting package. The next agent
implementation should consume `result.context_package` at that point, or hand
it to an application-level agent service.

### External agent or separate service

An external agent can call the synchronous endpoint and use the returned JSON:

```http
POST /api/rag/retrieve
Content-Type: application/json

{
  "repository": "owner/repository",
  "commit_sha": "<commit-sha>",
  "query_text": "Retrieve context for the authentication token validation change.",
  "changed_files": ["backend/auth/service.py"],
  "modified_symbols": ["validate_token"],
  "keywords": ["authentication", "token", "validation"]
}
```

Use the returned result list as grounded prompt context. Preserve each chunk's
file path, line range, rank, and retrieval reason so the agent can cite its
sources, prioritize the highest-ranked chunks, and avoid treating retrieved
code as untrusted instructions. There is no workflow-ID endpoint that returns
a previously generated context package today; an agent that must run after the
webhook task completes should either receive it in-process or retrieve it again
through `/api/rag/retrieve` using the saved workflow `semantic_query`.

## End-to-End Flow

### Bootstrap Flow

Bootstrap builds all RAG artifacts from scratch.

1. `BootstrapPipeline` calls `BootstrapIndexer`.
2. `BootstrapIndexer.build_repository()` discovers supported files.
3. `Chunker` routes each file to `CodeChunker` or `DocChunker`.
4. `MetadataBuilder` assigns stable chunk IDs, hashes, token counts, and source metadata.
5. `Embedder` generates embeddings, using `EmbeddingCache` where possible.
6. `VectorStore` rebuilds the FAISS dense vector index.
7. `KeywordStore` rebuilds the BM25 keyword index.
8. `DependencyGraphBuilder` creates a file-level dependency graph.
9. Stores and graph files are persisted with backup/rollback behavior.

### Incremental Commit Flow

Incremental processing updates the RAG indexes after a commit.

1. `RAGPipeline.execute()` starts an `IncrementalPipeline`.
2. `GitDiff` extracts added, modified, deleted, renamed, binary, and changed-line data.
3. `ASTDiff` compares old and new source for symbol-level changes.
4. `SemanticChange` classifies changes as logic, API, configuration, formatting, documentation, comment, rename, or refactoring.
5. `QueryBuilder` builds a `SemanticQuery` from changed files, symbols, keywords, languages, and dependency expansion.
6. `IncrementalIndexer` chunks only changed files.
7. Existing chunk hashes are compared against new chunks.
8. Unchanged chunks are skipped, changed chunks are embedded, obsolete chunks are soft-deleted.
9. FAISS, BM25, and dependency graph artifacts are refreshed transactionally.
10. `RetrievalPipeline` retrieves the final context package for the commit.

### Retrieval Flow

Retrieval combines multiple retrieval strategies.

1. `RetrievalPipeline.retrieve()` receives a `SemanticQuery`.
2. `HybridRetriever` embeds the query text.
3. `VectorStore.search()` returns dense semantic matches.
4. `KeywordStore.search()` returns BM25 lexical matches.
5. `DependencyRetriever` returns chunks from dependency-neighbor files.
6. `MetadataFilter` removes inactive chunks, wrong repositories, wrong languages, duplicate chunks, and low-scoring results.
7. `HybridRetriever.rrf()` merges result lists using Reciprocal Rank Fusion.
8. `ContextBuilder` wraps results into a `ContextPackage`.

## Directory Map

```text
backend/rag/
  chunking/       Turns source and documentation files into semantic chunks.
  config/         Static constants and runtime settings.
  embeddings/     Embedding provider abstraction, batching, normalization, and cache.
  indexing/       Bootstrap and incremental index maintenance.
  llm/            Provider-agnostic LLM clients used for semantic classification.
  parsing/        Language detection, AST parsing, symbol extraction, dependency graphs.
  pipeline/       High-level orchestration and workflow progress events.
  preprocessing/  Git diff, AST diff, semantic change classification, query building.
  retrieval/      FAISS, BM25, dependency retrieval, metadata filtering, hybrid ranking.
  schemas/        Shared immutable data contracts.
  storage/        Persisted runtime indexes and cache artifacts.
  utils/          File loading, hashing, logging, and token estimation helpers.
```

## Package Root

### `__init__.py`

This file is currently empty. The RAG package does not expose a root-level public API from this file; consumers import from subpackages such as `rag.pipeline`, `rag.indexing`, `rag.retrieval`, or `rag.schemas`.

## `chunking`

The `chunking` package converts repository files into `Chunk` objects. Chunking is intentionally split into two phases:

1. Produce content-only `ChunkDraft` objects.
2. Enrich drafts with metadata through `MetadataBuilder`.

### `chunking/__init__.py`

Provides lazy exports for the chunking package:

- `Chunker`
- `CodeChunker`
- `DocChunker`
- `MetadataBuilder`
- `Chunk`

It uses `__getattr__` to avoid importing Tree-sitter-related dependencies until chunking is actually used.

### `chunking/chunker.py`

High-level chunking orchestrator.

Purpose:

- Discover and process repository files.
- Skip unsupported, binary, or unknown-language files.
- Route code files to `CodeChunker`.
- Route documentation files to `DocChunker`.
- Attach metadata using `MetadataBuilder`.
- Validate chunk output before it moves downstream.
- Emit workflow events while parsing and chunking when a `workflow_id` is provided.

Important class:

- `Chunker`

Important methods:

- `chunk_file()` chunks one file from a path and source string.
- `chunk_repository()` discovers all files under a repository path and chunks them.
- `chunk_changed_file()` is a convenience wrapper for incremental processing.
- `should_process()` checks whether a file is supported and non-binary.
- `validate()` checks empty chunks, invalid line ranges, zero token counts, and duplicate chunk IDs.

### `chunking/code_chunker.py`

Semantic chunker for source code.

Purpose:

- Split code around meaningful symbol boundaries such as classes, functions, and methods.
- Use Tree-sitter via `ASTParser` when a parser is available.
- Fall back to symbol extraction or whole-file chunking when AST parsing fails.
- Split oversized symbols by line boundaries.
- Add module-level chunks for uncovered content.
- Deduplicate drafts before metadata is attached.

Important class:

- `CodeChunker`

Supported AST chunk node configuration currently covers:

- Python
- Java
- JavaScript
- TypeScript

Important behavior:

- Python decorators are handled as decorated definitions so decorated functions/classes stay together.
- Parent classes are tracked for method chunks.
- Large chunks are split based on `settings.max_chunk_tokens`.
- The module is deliberately metadata-free; it returns `ChunkDraft`, not final `Chunk`.

### `chunking/doc_chunker.py`

Semantic chunker for documentation files.

Purpose:

- Split Markdown by headings while preserving fenced code blocks.
- Split reStructuredText by section underline patterns.
- Split HTML by heading tags.
- Split plain text by paragraph boundaries.
- Split oversized documentation sections by paragraph boundaries.

Important class:

- `DocChunker`

Important behavior:

- Documentation chunks use `ChunkType.DOCUMENTATION`.
- Section headings become `symbol_name`.
- Documentation sections use `SymbolType.SECTION`.

### `chunking/metadata_builder.py`

Converts `ChunkDraft` objects into final `Chunk` objects.

Purpose:

- Strip and validate chunk content.
- Normalize line ranges.
- Generate content hashes.
- Estimate token counts.
- Generate stable chunk IDs.
- Attach repository, file path, language, symbol, commit, token, and active-state metadata.

Important class:

- `MetadataBuilder`

Important methods:

- `build()` converts one draft into one `Chunk`.
- `build_many()` converts an iterable of drafts.
- `build_chunk_id()` creates a deterministic ID from repository, file path, symbol, line range, and content hash.
- `detect_duplicates()` identifies repeated chunk IDs.

### `chunking/models.py`

Chunking-specific data structures.

Purpose:

- Define `ChunkDraft`, the intermediate model produced by chunkers.
- Define `ChunkStatistics`, immutable aggregate stats for chunking runs.
- Define `ChunkValidationResult`, the result of validating chunk output.
- Re-export shared chunk models from `rag.schemas.chunk`.

Important models:

- `ChunkDraft`
- `ChunkStatistics`
- `ChunkValidationResult`

## `config`

The `config` package centralizes constants and runtime settings.

### `config/__init__.py`

Exports the singleton `settings` object from `settings.py`.

### `config/constants.py`

Static constants used across the RAG module.

Purpose:

- Map file extensions to languages.
- Define documentation extensions.
- Define ignored directories and ignored binary/file extensions.
- Define retrieval defaults such as `DEFAULT_TOP_K` and `DEFAULT_RRF_K`.
- Define persisted artifact filenames.
- Define default storage subdirectories.
- Define the hash algorithm.

Key constants:

- `SUPPORTED_LANGUAGES`
- `DOCUMENTATION_EXTENSIONS`
- `IGNORED_DIRECTORIES`
- `IGNORED_EXTENSIONS`
- `HASH_ALGORITHM`
- `FAISS_INDEX_FILENAME`
- `METADATA_FILENAME`
- `DEPENDENCY_GRAPH_FILENAME`
- `BM25_FILENAME`
- `EMBEDDING_CACHE_FILENAME`

### `config/settings.py`

Runtime configuration loaded through Pydantic settings.

Purpose:

- Provide environment-configurable RAG options with `RAG_` prefix.
- Configure LLM provider, model, and Ollama URL.
- Configure embedding provider, model, batching, retries, normalization, and cache behavior.
- Configure retrieval thresholds and top-k behavior.
- Configure chunk size and overlap.
- Configure storage root and logging.
- Configure dependency graph traversal depth and worker count.

Important object:

- `settings = RAGSettings()`

Environment variables use the `RAG_` prefix. For example:

- `RAG_LLM_PROVIDER`
- `RAG_LLM_MODEL`
- `RAG_EMBEDDING_PROVIDER`
- `RAG_EMBEDDING_MODEL`
- `RAG_TOP_K`
- `RAG_SIMILARITY_THRESHOLD`
- `RAG_STORAGE_ROOT`

## `embeddings`

The `embeddings` package generates dense vectors for chunks and queries.

### `embeddings/__init__.py`

Provides lazy exports for:

- `Embedder`
- `EmbedderStatistics`
- `BaseEmbeddingModel`
- `EmbeddingModelFactory`
- `EmbeddingCache`

### `embeddings/cache.py`

JSON-backed persistent embedding cache.

Purpose:

- Avoid recomputing embeddings for unchanged content.
- Key cache entries by content hash, embedding model name, and model version.
- Protect in-process cache access with a reentrant lock.
- Persist atomically through temporary files and `os.replace`.
- Detect corrupt cache JSON and reset safely.
- Purge stale entries when model metadata changes.

Important classes:

- `CacheStatistics`
- `EmbeddingCache`

Important methods:

- `build_key()` creates a deterministic cache key.
- `exists()` checks for a cached embedding.
- `load()` returns cached vectors and increments hit/miss stats.
- `save()` writes vectors to cache.
- `delete()` removes one entry.
- `clear()` clears all entries.
- `purge_stale()` removes entries for old models or versions.

### `embeddings/embedder.py`

Embedding orchestration layer.

Purpose:

- Lazily create an embedding provider.
- Lazily create an embedding cache.
- Batch embedding requests.
- Reuse cached vectors.
- Skip duplicate content hashes within a batch.
- Retry failed embedding requests.
- Fall back from batch embedding to per-chunk embedding if a batch fails.
- Normalize vectors with L2 normalization when enabled.
- Validate embedding dimensions.
- Emit workflow progress events during embedding.

Important classes:

- `EmbedderStatistics`
- `Embedder`

Important methods:

- `embed_chunk()` embeds one `Chunk`.
- `embed_chunks()` embeds a list of chunks with cache and duplicate handling.
- `embed_text()` embeds raw query text.
- `embed_batch()` embeds raw text batches.
- `validate_embedding_dimension()` enforces model consistency.
- `clear_cache()` clears the cache.

### `embeddings/embedding_models.py`

Embedding provider abstraction and implementations.

Purpose:

- Define the provider interface used by the rest of RAG.
- Implement Ollama embeddings.
- Implement Sentence Transformers embeddings.
- Reserve an OpenAI embedding provider placeholder for future integration.
- Centralize provider creation through `EmbeddingModelFactory`.

Important classes:

- `BaseEmbeddingModel`
- `OllamaEmbedding`
- `SentenceTransformerEmbedding`
- `OpenAIEmbedding`
- `EmbeddingModelFactory`

Provider behavior:

- `OllamaEmbedding` calls Ollama `/api/embed`.
- `SentenceTransformerEmbedding` loads `sentence_transformers.SentenceTransformer`.
- `OpenAIEmbedding` currently raises `NotImplementedError` for actual embedding calls.
- `EmbeddingModelFactory.create()` selects a provider from settings or explicit arguments.

## `indexing`

The `indexing` package builds and maintains persisted retrieval stores.

### `indexing/__init__.py`

Exports:

- `BootstrapIndexer`
- `IncrementalIndexer`
- `IndexInvalidator`

### `indexing/bootstrap.py`

Full repository indexing.

Purpose:

- Chunk the full repository.
- Generate embeddings for all chunks.
- Rebuild FAISS vector index.
- Rebuild BM25 keyword index.
- Rebuild dependency graph.
- Persist all artifacts safely with backup/rollback.
- Emit workflow events when requested.

Important class:

- `BootstrapIndexer`

Important methods:

- `bootstrap()` coordinates the whole rebuild.
- `build_repository()` chunks the repository.
- `build_vector_index()` rebuilds FAISS.
- `build_keyword_index()` rebuilds BM25.
- `build_dependency_graph()` builds graph JSON.
- `persist()` saves stores with transaction-style backups.
- `statistics()` reports index and graph counts.

### `indexing/incremental.py`

Incremental index update engine.

Purpose:

- Load existing indexes.
- Detect embedding model version mismatch and fall back to full bootstrap.
- Re-chunk added, modified, and renamed files.
- Compare chunk hashes against existing chunks.
- Skip unchanged chunks.
- Restore soft-deleted unchanged chunks.
- Embed only new or changed chunks.
- Soft-delete obsolete chunks.
- Update FAISS, BM25, and dependency graph.
- Persist changes with backup/rollback.
- Repair VectorStore and KeywordStore consistency mismatches.

Important class:

- `IncrementalIndexer`

Important methods:

- `update()` applies commit file changes.
- `insert_chunks()` programmatically inserts chunks.
- `update_chunks()` programmatically replaces chunks.
- `remove_chunks()` soft-deletes chunks.
- `sync()` checks FAISS/BM25 active chunk consistency and repairs it.
- `refresh_indexes()` persists stores and embedding model info.
- `statistics()` returns store counts.

### `indexing/invalidation.py`

Soft deletion and cleanup helper.

Purpose:

- Soft-delete chunks from both FAISS and BM25 stores.
- Restore soft-deleted chunks.
- Physically rebuild stores when the deleted ratio exceeds a threshold.

Important class:

- `IndexInvalidator`

Important methods:

- `invalidate()` soft-deletes a chunk in both stores.
- `restore()` marks a chunk active again.
- `cleanup()` physically rebuilds stores from active chunks.
- `needs_rebuild()` checks whether physical cleanup is warranted.

## `llm`

The `llm` package provides optional LLM clients. The RAG module primarily uses this layer in `SemanticChange` for classification refinement.

### `llm/__init__.py`

Exports:

- `BaseLLM`
- `OllamaClient`
- `GrokClient`
- `LLMFactory`

### `llm/base.py`

Abstract interface for LLM providers.

Purpose:

- Define `generate(prompt, system_prompt=None)`.
- Define `health_check()`.
- Store common model configuration such as model name, temperature, and max tokens.

Important class:

- `BaseLLM`

### `llm/factory.py`

LLM provider factory.

Purpose:

- Read `settings.llm_provider`.
- Create `OllamaClient` for `ollama`.
- Create `GrokClient` for `grok`, requiring a configured API key.
- Raise for unsupported providers.

Important class:

- `LLMFactory`

### `llm/grok_client.py`

Grok client implementation.

Purpose:

- Implement `BaseLLM` using xAI/Grok's OpenAI-compatible chat completions API.
- Manage bearer-token headers through a `requests.Session`.
- Provide model endpoint health checking.
- Convert request failures into `RuntimeError`.

Important class:

- `GrokClient`

### `llm/ollama_client.py`

Ollama client implementation.

Purpose:

- Implement `BaseLLM` using Ollama `/api/generate`.
- Support optional system prompts.
- Support temperature and max token options.
- Health check using `/api/tags`.
- Convert timeouts and request failures into `RuntimeError`.

Important class:

- `OllamaClient`

## `parsing`

The `parsing` package performs static analysis used by chunking, diffing, and dependency graph retrieval.

### `parsing/__init__.py`

Exports:

- `LanguageDetector`
- `ASTParser`
- `ExtractedSymbol`
- `ExtractionResult`
- `SymbolExtractor`
- `DependencyGraphBuilder`
- `DependencyGraphQuery`
- `DependencyGraphUpdater`
- `GraphPersistence`

### `parsing/language_detector.py`

File extension based language detection.

Purpose:

- Convert repository file paths into language labels.
- Identify source code files.
- Identify documentation files.
- List supported languages and extensions.

Important class:

- `LanguageDetector`

### `parsing/ast_parser.py`

Tree-sitter parser wrapper.

Purpose:

- Initialize parsers for Python, Java, JavaScript, TypeScript, and TSX.
- Parse source strings and files into syntax trees.
- Traverse syntax trees.
- Find nodes by type.
- Extract node text and line ranges.
- Check syntax errors.
- Provide tree statistics and debug printing.

Important class:

- `ASTParser`

### `parsing/symbol_extractor.py`

Symbol extraction on top of Tree-sitter.

Purpose:

- Extract classes, functions, methods, imports, parent class names, signatures, and line ranges.
- Return `ExtractionResult` objects used by AST diffing and dependency graph building.

Important classes:

- `ExtractedSymbol`
- `ExtractionResult`
- `SymbolExtractor`

Current implemented extraction:

- Python class/function/method extraction.
- Python import extraction.

Maintenance note:

- The file also contains several module-level helper functions with `self` parameters after the `SymbolExtractor` class. They appear to mirror methods that may have been intended to live inside the class. The active pipeline mainly uses the class methods above them.

### `parsing/dependency_graph.py`

Dependency graph construction, querying, updating, and persistence.

Purpose:

- Build a file-level dependency graph from extracted imports.
- Resolve Python import strings to repository-relative file paths.
- Query dependencies, dependents, neighbors, one-hop/two-hop expansion, BFS, DFS, affected files, and path existence.
- Update the graph incrementally for added, modified, deleted, and renamed files.
- Persist the graph to JSON and create backups.

Important classes:

- `DependencyGraphBuilder`
- `DependencyGraphQuery`
- `DependencyGraphUpdater`
- `GraphPersistence`

Important behavior:

- Graph nodes represent files.
- Graph edges currently represent import relationships.
- Dependency retrieval uses this graph to expand context around changed files.

## `pipeline`

The `pipeline` package contains high-level orchestration.

### `pipeline/__init__.py`

Exports:

- `BootstrapPipeline`
- `IncrementalPipeline`
- `RetrievalPipeline`
- `RAGPipeline`

### `pipeline/bootstrap_pipeline.py`

Thin wrapper around `BootstrapIndexer`.

Purpose:

- Provide a pipeline-level entry point for full repository initialization.
- Keep bootstrap invocation consistent with the broader pipeline API.

Important class:

- `BootstrapPipeline`

### `pipeline/events.py`

Dataclass event definitions for pipeline lifecycle tracking.

Purpose:

- Decouple RAG processing from workflow status updates.
- Represent stages like started, parsing, chunking, embedding, indexing, retrieval, completed, and failed.

Important events:

- `PipelineStarted`
- `ParsingStarted`
- `ChunkCreated`
- `EmbeddingGenerated`
- `IndexingStarted`
- `RetrievalStarted`
- `RetrievalFinished`
- `PipelineCompleted`
- `PipelineFailed`

### `pipeline/manager.py`

Workflow state and logging bridge.

Purpose:

- Load and save workflow state through `WorkflowManager`.
- Append progress logs to `logs/{workflow_id}.log`.
- Detect cancellation and raise `PipelineCancelled`.
- Handle RAG pipeline events and update workflow progress percentages.

Important functions:

- `get_workflow_manager()`
- `append_log()`
- `read_logs()`
- `check_cancelled()`
- `handle_event()`

External dependencies:

- `app.core.config.settings`
- `workflow.workflow_manager.WorkflowManager`
- `workflow.workflow_state.WorkflowState`

### `pipeline/incremental_pipeline.py`

Commit-level preprocessing and indexing orchestrator.

Purpose:

- Extract Git diff information.
- Compare symbols with AST diffing.
- Classify semantic changes.
- Build the `SemanticQuery`.
- Update indexes through `IncrementalIndexer`.

Important class:

- `IncrementalPipeline`

Important methods:

- `process_commit()` runs the full commit preprocessing and indexing flow.
- `update_repository()` invokes `IncrementalIndexer.update()` and `sync()`.

Maintenance note:

- The current construction of `SemanticChange` passes all changed symbols as `added_symbols` and leaves `modified_symbols`/`removed_symbols` empty inside the classification loop. That may reduce classification precision for modified or removed symbols.

### `pipeline/retrieval_pipeline.py`

Retrieval and context package construction.

Purpose:

- Load vector and keyword stores.
- Load dependency graph when available.
- Build a `HybridRetriever`.
- Execute retrieval for a `SemanticQuery`.
- Return a `ContextPackage`.

Important classes:

- `ContextBuilder`
- `RetrievalPipeline`

Important behavior:

- If dependency graph initialization fails, retrieval can return an empty `ContextPackage` rather than crashing.
- Workflow retrieval events are emitted when `workflow_id` is provided.

### `pipeline/rag_pipeline.py`

Master RAG orchestrator.

Purpose:

- Combine incremental indexing and retrieval into one top-level operation.
- Persist the generated `SemanticQuery` into workflow state when available.
- Return a `PipelineResult` with success/failure, context package, and timing.
- Provide status information about last run and index store counts.

Important class:

- `RAGPipeline`

## `preprocessing`

The `preprocessing` package transforms raw Git changes into a structured semantic query.

### `preprocessing/__init__.py`

Exports:

- `GitDiff`
- `ASTDiff`
- `SemanticChange`
- `QueryBuilder`

### `preprocessing/git_diff.py`

Git diff extraction.

Purpose:

- Use GitPython to compare two commits.
- Detect added, modified, deleted, and renamed files.
- Detect binary files.
- Parse unified diff hunks into changed line ranges in the new file.
- Capture commit metadata.

Important function:

- `parse_hunks()`

Important class:

- `GitDiff`

### `preprocessing/ast_diff.py`

Symbol-level AST diffing.

Purpose:

- Compare old and new source versions.
- Extract added, deleted, modified, and unchanged symbols.
- Compare imports added and removed.
- Normalize source to ignore formatting, comments, whitespace, and Python docstrings.
- Subtract method bodies from class-level comparisons so class changes are not falsely triggered by method body changes.

Important functions:

- `normalize_python_source()`
- `normalize_generic_source()`
- `get_symbol_source()`

Important class:

- `ASTDiff`

### `preprocessing/semantic_change.py`

Semantic change classification.

Purpose:

- Classify a file change using heuristics and optional LLM refinement.
- Detect documentation, configuration, rename, formatting, comment, logging-only, API, and logic changes.
- Estimate severity.
- Decide whether documentation should be updated.

Important class:

- `SemanticChange`

Important methods:

- `classify()`
- `is_semantic()`
- `change_type()`
- `severity()`
- `needs_documentation()`

LLM behavior:

- If a change is considered semantic by heuristics, the classifier attempts to call `LLMFactory.create()`.
- The LLM must return raw JSON.
- If LLM classification fails, heuristic results are retained.

### `preprocessing/query_builder.py`

Semantic query construction.

Purpose:

- Convert changed files, symbols, change type, and dependency graph expansion into a `SemanticQuery`.
- Expand symbols into useful lexical pieces using dot, camelCase, and snake_case splitting.
- Add file stems and dependency file stems to query terms.
- Remove common code stop words.
- Generate BM25 keywords.
- Derive file extensions and languages.

Important class:

- `QueryBuilder`

Important methods:

- `build()`
- `expand_symbols()`
- `expand_dependencies()`
- `optimize()`
- `keywords()`

## `retrieval`

The `retrieval` package stores and retrieves chunks.

### `retrieval/__init__.py`

Provides lazy exports for:

- `HybridRetriever`
- `VectorStore`
- `KeywordStore`
- `DependencyRetriever`
- `MetadataFilter`

### `retrieval/vector_store.py`

FAISS-backed dense vector store.

Purpose:

- Create, load, save, search, add, update, delete, and rebuild a FAISS index.
- Persist chunk metadata alongside FAISS vectors.
- Track mappings between FAISS IDs and chunk IDs.
- Support soft deletion through `_deleted_chunk_ids`.
- Return only active chunks during search.

Important classes:

- `VectorStoreStatistics`
- `VectorSearchHit`
- `VectorStore`

Important methods:

- `create()`
- `load()`
- `save()`
- `search()`
- `add_batch()`
- `delete()`
- `rebuild()`
- `get_chunk()`
- `get_chunks_by_file()`
- `get_all_active_chunks()`
- `statistics()`

Similarity behavior:

- Uses `faiss.IndexFlatIP`, so normalized vectors behave like cosine similarity through inner product.

### `retrieval/keyword_store.py`

BM25-backed sparse keyword store.

Purpose:

- Tokenize chunk content.
- Build a BM25 corpus with `rank_bm25.BM25Okapi`.
- Search exact-ish lexical matches for identifiers, filenames, function names, and class names.
- Persist BM25 pickle and chunk metadata JSON.
- Support update and soft deletion.

Important classes:

- `KeywordStoreStatistics`
- `KeywordSearchHit`
- `KeywordStore`

Important methods:

- `index()`
- `search()`
- `update()`
- `delete()`
- `save()`
- `load()`
- `get_chunks_by_file()`
- `get_all_active_chunks()`
- `statistics()`

### `retrieval/dependency_retriever.py`

Dependency graph based retrieval.

Purpose:

- Convert graph-neighbor files into chunk hits.
- Retrieve one-hop or two-hop context.
- Retrieve affected chunks for changed files.
- Score changed files higher than dependency neighbors.

Important classes:

- `DependencyRetrieverStatistics`
- `DependencySearchHit`
- `DependencyRetriever`

Important methods:

- `retrieve()`
- `retrieve_one_hop()`
- `retrieve_two_hop()`
- `affected_chunks()`
- `expand_context()`
- `set_chunks_by_file()`

### `retrieval/metadata_filter.py`

Filtering utilities for retrieval results.

Purpose:

- Remove inactive or empty chunks.
- Deduplicate by chunk ID, keeping the highest scoring result.
- Filter by repository.
- Filter by language.
- Filter by similarity threshold.
- Filter by chunk type.
- Filter by file paths.
- Apply arbitrary metadata filters from `SemanticQuery.metadata_filters`.

Important classes:

- `MetadataFilterStatistics`
- `MetadataFilter`

### `retrieval/hybrid_retriever.py`

Hybrid retrieval and ranking.

Purpose:

- Run vector retrieval, BM25 retrieval, and dependency retrieval.
- Normalize BM25 scores relative to the max result score.
- Use metadata filters on channel results.
- Merge channels with Reciprocal Rank Fusion.
- Return final `RetrievalResults`.
- Track channel-level statistics and failures.

Important classes:

- `HybridRetrieverStatistics`
- `HybridRetriever`

Important methods:

- `retrieve()`
- `retrieve_for_change()`
- `rrf()`
- `merge()`
- `rank()`
- `statistics()`

Retrieval channels:

- `RetrievalSource.FAISS`
- `RetrievalSource.BM25`
- `RetrievalSource.DEPENDENCY`
- Final merged results are marked `RetrievalSource.HYBRID`.

## `schemas`

The `schemas` package defines immutable contracts exchanged between RAG components.

### `schemas/__init__.py`

Re-exports the public schema models and enums from all schema files.

### `schemas/change.py`

Change detection schemas.

Purpose:

- Represent file-level and symbol-level semantic changes.
- Provide convenience properties for change type checks.

Important models:

- `ChangeType`
- `SymbolType`
- `SymbolChange`
- `CodeChange`

### `schemas/chunk.py`

Chunk schemas.

Purpose:

- Represent semantic chunks and their metadata.
- Store optional embeddings and summaries.
- Track chunk active/inactive state.
- Provide aggregate chunk collection helpers.

Important models:

- `ChunkType`
- `SymbolType`
- `ChunkMetadata`
- `Chunk`
- `ChunkCollection`

### `schemas/context.py`

Final context package schemas.

Purpose:

- Represent the final output of the RAG pipeline.
- Attach query, retrieval results, changed files, commit SHA, repository name, and metadata.
- Represent pipeline success/failure through `PipelineResult`.

Important models:

- `ContextMetadata`
- `ContextPackage`
- `PipelineResult`

### `schemas/graph.py`

Dependency graph schemas.

Purpose:

- Represent repository files as graph nodes.
- Represent directed dependencies as graph edges.
- Represent a complete repository dependency graph.

Important models:

- `DependencyType`
- `DependencyEdge`
- `DependencyNode`
- `DependencyGraph`

### `schemas/query.py`

Semantic retrieval query schema.

Purpose:

- Represent the structured query generated from commit changes.
- Carry query text, changed files, modified symbols, keywords, languages, dependency files, top-k, threshold, and metadata filters.

Important model:

- `SemanticQuery`

### `schemas/retrieval.py`

Retrieval result schemas.

Purpose:

- Represent individual retrieved chunks.
- Represent ranked retrieval result collections.
- Track which retrieval strategy produced each result.

Important models:

- `RetrievalSource`
- `RetrievalResult`
- `RetrievalResults`

## `utils`

The `utils` package contains shared low-level helpers.

### `utils/__init__.py`

Re-exports file loading, hashing, logging, and tokenization helpers.

### `utils/file_loader.py`

Repository file discovery and loading.

Purpose:

- Determine whether files are supported.
- Detect binary files by checking for null bytes.
- Recursively discover supported files while ignoring configured directories.
- Load files as UTF-8 text with replacement for invalid bytes.
- Load an entire repository into a file-content mapping.
- Filter file lists by extension.

Important functions:

- `is_supported_file()`
- `is_binary_file()`
- `discover_files()`
- `load_text_file()`
- `load_repository()`
- `filter_files_by_extension()`

### `utils/hashing.py`

Deterministic hashing helpers.

Purpose:

- Generate content hashes.
- Generate file hashes.
- Hash multiple chunks.
- Combine multiple hashes into a single hash.
- Compare old and new hashes.

Important functions:

- `generate_hash()`
- `hash_file()`
- `hash_chunks()`
- `combine_hashes()`
- `has_content_changed()`

### `utils/logger.py`

RAG logger helpers.

Purpose:

- Return namespaced loggers under the `rag` logger name.
- Change RAG log level dynamically.
- Check whether debug logging is enabled.

Important functions:

- `get_logger()`
- `set_log_level()`
- `is_debug_enabled()`

### `utils/tokenizer.py`

Lightweight token estimation helpers.

Purpose:

- Estimate token counts in a model-agnostic way.
- Estimate remaining context window space.
- Check whether text fits a context window.
- Normalize whitespace.
- Truncate text to an estimated token budget.

Important functions:

- `estimate_tokens()`
- `estimate_available_tokens()`
- `fits_context_window()`
- `normalize_whitespace()`
- `truncate_to_token_limit()`

Implementation note:

- Token estimation uses approximately 4 characters per token.

## `storage`

The `storage` folder contains generated runtime artifacts. These are not source modules, but they are important to understand because they are the persisted state of the RAG system.

### `storage/bm25/.gitkeep`

Keeps the BM25 storage directory present in Git even when no index has been generated.

### `storage/faiss/.gitkeep`

Keeps the FAISS storage directory present in Git even when no index has been generated.

### `storage/dependency_graph/.gitkeep`

Keeps the dependency graph storage directory present in Git even when no graph has been generated.

### `storage/storage/bm25/bm25.pkl`

Generated BM25 index pickle. This is written by `KeywordStore.save()` and read by `KeywordStore.load()`.

### `storage/storage/bm25/bm25_metadata.json`

Generated BM25 metadata. It stores chunk payloads, chunk IDs, repository metadata, and deleted chunk IDs needed to reconstruct the keyword store.

### `storage/storage/faiss/faiss.index`

Generated FAISS binary index. This is written by `VectorStore.save()` and read by `VectorStore.load()`.

### `storage/storage/faiss/metadata.json`

Generated FAISS metadata. It stores vector dimension, repository name, FAISS ID mappings, deleted chunk IDs, and serialized chunks.

### `storage/storage/dependency_graph/dependency_graph.json`

Generated dependency graph JSON. This is written and read by `GraphPersistence`.

### `storage/storage/embeddings/embedding_cache.json`

Generated embedding cache. It stores embeddings by content hash, embedding model, and model version.

### `storage/storage/embeddings/embedding_cache.tmp`

Temporary embedding cache artifact. Cache writes normally use uniquely named temporary files and atomic replacement. A `.tmp` file can indicate an interrupted or leftover cache write.

## Generated Python Cache Files

The repository currently contains `__pycache__` folders under several RAG subpackages. These are Python bytecode caches generated by the interpreter and are not part of the RAG source design. They do not need functional documentation and can usually be ignored when reasoning about the system.

## Core Data Contracts

### `Chunk`

Represents one retrievable unit of content. It contains:

- `metadata`: `ChunkMetadata`
- `content`: source or documentation text
- `embedding`: optional dense vector
- `summary`: optional generated summary

### `ChunkMetadata`

Captures:

- Stable `chunk_id`
- Repository and file path
- Language
- Chunk type
- Symbol name/type/parent
- Start and end lines
- Commit SHA
- Content hash
- Token count
- Active/inactive state
- Creation timestamp

### `SemanticQuery`

Captures the retrieval request generated from a commit:

- Natural language query text
- Changed files
- Modified symbols
- Keywords
- File extensions
- Languages
- Dependency files
- `top_k`
- Similarity threshold
- Metadata filters

### `RetrievalResult`

Wraps a retrieved chunk with:

- Similarity score
- Rank
- Retrieval source
- Human-readable retrieval reason

### `ContextPackage`

The final output passed downstream. It contains:

- Repository name
- Commit SHA
- Semantic query
- Retrieval results
- Changed files
- Context metadata

## Configuration Summary

Important runtime settings from `RAGSettings`:

| Setting | Purpose | Default |
| --- | --- | --- |
| `llm_provider` | LLM provider for classification | `ollama` |
| `llm_model` | LLM model name | `deepseek-r1:1.5b` |
| `ollama_base_url` | Ollama server URL | `http://localhost:11434` |
| `embedding_provider` | Embedding provider | `ollama` |
| `embedding_model` | Embedding model name | `nomic-embed-text` |
| `embedding_batch_size` | Embedding batch size | `32` |
| `embedding_model_version` | Cache invalidation version | `1` |
| `embedding_normalize` | L2 normalize vectors | `True` |
| `top_k` | Retrieval result limit | `10` |
| `similarity_threshold` | Minimum retrieval score | `0.30` |
| `rrf_k` | Reciprocal Rank Fusion constant | `60` |
| `max_chunk_tokens` | Maximum chunk size estimate | `1024` |
| `chunk_overlap` | Intended overlap setting | `100` |
| `storage_root` | Root for persisted artifacts | `rag/storage` |
| `enable_embedding_cache` | Reuse embeddings | `True` |
| `enable_soft_delete` | Soft delete old chunks | `True` |
| `max_dependency_depth` | Dependency traversal depth | `2` |
| `max_workers` | Worker count setting | `4` |

## Supported Files

Source language support is defined in `config/constants.py`.

Supported source extensions include:

- `.py`
- `.js`
- `.ts`
- `.tsx`
- `.jsx`
- `.java`
- `.cpp`
- `.cc`
- `.c`
- `.cs`
- `.go`
- `.rs`
- `.rb`
- `.php`
- `.swift`
- `.kt`
- `.scala`

Documentation extensions include:

- `.md`
- `.txt`
- `.rst`

Important distinction:

- `LanguageDetector` recognizes many extensions as code.
- `ASTParser` currently initializes parsers for Python, Java, JavaScript, TypeScript, and TSX.
- `SymbolExtractor` currently implements detailed extraction for Python.
- Other languages may still be chunked through parser support, fallback symbol behavior, or whole-file fallback depending on the path.

## Index Consistency Model

The RAG indexes are maintained as coordinated stores:

- FAISS stores dense vectors and chunk metadata.
- BM25 stores tokenized chunk content and chunk metadata.
- Dependency graph stores file-to-file relationships.
- Embedding cache stores reusable vectors by content hash and model metadata.

Incremental updates rely heavily on stable chunk IDs and content hashes:

- Same content and location means embedding can often be reused.
- Changed content creates a new chunk or invalidates old state.
- Deleted/obsolete chunks are usually soft-deleted first.
- Physical cleanup happens after the deleted ratio exceeds a configured threshold.

## Error Handling and Resilience

The module uses several defensive patterns:

- Chunking validation logs warnings for suspicious chunks.
- Embedding generation retries failed batches.
- Embedding cache corruption starts a fresh cache.
- Bootstrap and incremental persistence create backups before overwriting stores.
- Failed persistence rolls back from backups.
- Retrieval channel failures are logged and isolated where possible.
- Missing dependency graph can result in empty retrieval context instead of crashing the entire retrieval pipeline.
- Workflow cancellation is checked during long-running chunking and embedding operations.

## Maintenance Notes

These notes are based on the current code structure.

- `chunk_overlap` exists in settings but is not consistently used by current chunkers.
- `SymbolExtractor` has module-level helper functions after the class that look like they may have been intended as class methods.
- `IncrementalPipeline` currently aggregates changed symbols in a way that may blur added/modified/deleted symbol distinctions during semantic classification.
- `OpenAIEmbedding` is a placeholder and is not usable until implemented.
- The default `storage_root` is `rag/storage`, while this repository also contains nested generated artifacts under `backend/rag/storage/storage/...`; verify runtime working directory assumptions when deploying.
- Several modules import workflow/application objects outside `rag`, especially `pipeline/manager.py`; RAG workflow progress tracking depends on those external application modules.

## Typical Entry Points

Use these classes depending on the task:

- Full initial indexing: `rag.pipeline.BootstrapPipeline`
- Commit processing plus retrieval: `rag.pipeline.RAGPipeline`
- Incremental index update only: `rag.pipeline.IncrementalPipeline` or `rag.indexing.IncrementalIndexer`
- Retrieval only from an existing query: `rag.pipeline.RetrievalPipeline`
- Manual chunking: `rag.chunking.Chunker`
- Manual embedding: `rag.embeddings.Embedder`
- Direct FAISS access: `rag.retrieval.VectorStore`
- Direct BM25 access: `rag.retrieval.KeywordStore`
- Dependency graph operations: `rag.parsing.DependencyGraphBuilder`, `DependencyGraphQuery`, `DependencyGraphUpdater`, `GraphPersistence`
