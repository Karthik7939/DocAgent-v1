"""
app/api/rag.py
---------------
RAG (Retrieval Augmented Generation) API endpoints.

Exposes four HTTP endpoints:

POST /api/rag/bootstrap
    Trigger a full initial index build for a repository.
    Must be called once after a repository is cloned/synced before any
    incremental pipeline or retrieve calls will return useful results.

POST /api/rag/retrieve
    Synchronous retrieval from pre-built indexes.
    Accepts a SemanticQuery JSON body and returns a ContextPackage JSON body.
    Can be called by external agents or services that need code context
    without triggering a full webhook flow.

GET /api/rag/status/{repository_name}
    Returns real-time indexing status for a specific repository.

GET /api/rag/knowledge-base
    Returns all repositories that have embeddings stored in the vector store.

No business logic. No filesystem access. Delegates entirely to RAGService
and the underlying rag/ pipelines.
"""

import json
import logging
import os
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dependencies import get_github_service
from rag.config.settings import RAGSettings
from rag.indexing.index_stats import read_index_stats
from rag.pipeline.retrieval_pipeline import RetrievalPipeline
from rag.schemas.query import SemanticQuery
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter()

# One shared RAGService instance for all API calls.
# Construction is cheap (no I/O at init time).
_rag_service = RAGService()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    """Request body for POST /api/rag/bootstrap."""

    repository_name: str = Field(
        ...,
        description="Full repository name, e.g. 'owner/repo'.",
    )
    repository_path: str = Field(
        ...,
        description=(
            "Local filesystem path to the cloned repository. "
            "Must already exist on disk."
        ),
    )
    commit_sha: str = Field(
        default="HEAD",
        description="Commit SHA to tag the index with.",
    )


class BootstrapResponse(BaseModel):
    """Response body for POST /api/rag/bootstrap."""

    status: str
    message: str
    repository_name: str


class RetrieveRequest(BaseModel):
    """
    Request body for POST /api/rag/retrieve.

    Minimum required fields are ``repository``, ``commit_sha``, and
    ``query_text``. All other fields improve retrieval quality but are
    optional for external callers.
    """

    repository: str = Field(
        ...,
        description="Repository name, e.g. 'owner/repo'.",
    )
    commit_sha: str = Field(
        ...,
        description="Commit SHA context for retrieval.",
    )
    query_text: str = Field(
        ...,
        min_length=1,
        description="Natural language retrieval query.",
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="Files modified in the commit (improves filtering).",
    )
    modified_symbols: list[str] = Field(
        default_factory=list,
        description="Function/class/method names modified in the commit.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for BM25 keyword retrieval.",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of chunks to return.",
    )
    similarity_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity score. Defaults to rag.config.settings."
            "similarity_threshold when omitted, instead of a hardcoded "
            "value here, so this HTTP endpoint and the internal "
            "RAGService.retrieve() path (used by understanding_agent.py) "
            "stay in sync — see rag_fix_plan.md P0.2."
        ),
    )


class GenerateDocsRequest(BaseModel):
    """Request body for POST /api/rag/generate-docs."""

    repository_name: str = Field(
        ...,
        description="Full repository name, e.g. 'owner/repo'.",
    )
    repository_path: str = Field(
        ...,
        description=(
            "Local filesystem path to the cloned repository. "
            "Must already be bootstrapped via POST /api/rag/bootstrap."
        ),
    )
    commit_sha: str = Field(
        default="HEAD",
        description="HEAD commit SHA.",
    )
    branch: str = Field(
        default="main",
        description="Repository branch name.",
    )


class GenerateDocsResponse(BaseModel):
    """Response body for POST /api/rag/generate-docs."""

    status: str
    message: str
    workflow_id: str
    repository_name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate-docs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Full Documentation from Bootstrap Index",
    description=(
        "Triggers a complete documentation generation run for a repository that "
        "has already been bootstrapped via POST /api/rag/bootstrap. "
        "Scans all source files, retrieves a full-repo RAG context package from "
        "the existing index, and runs the full agent pipeline asynchronously. "
        "Returns immediately with a workflow_id — poll /api/workflows/{id} for status."
    ),
    tags=["RAG"],
    response_model=GenerateDocsResponse,
)
async def generate_docs(
    request: GenerateDocsRequest,
    github_service=Depends(get_github_service),
) -> GenerateDocsResponse:
    """
    Trigger a full documentation generation run using the existing bootstrap index.

    Args:
        request: GenerateDocsRequest with repository_name, repository_path, and commit_sha.
        github_service: Fully wired GitHubService injected by FastAPI.

    Returns:
        GenerateDocsResponse: Immediate response with workflow_id.

    Raises:
        HTTPException 400: If repository_path does not exist on disk.
    """
    import os as _os

    if not _os.path.isdir(request.repository_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"repository_path '{request.repository_path}' does not exist. "
                "Clone or sync the repository before calling generate-docs."
            ),
        )

    workflow_id = str(uuid.uuid4())
    logger.info(
        "generate-docs requested: repo=%s  path=%s  workflow=%s",
        request.repository_name,
        request.repository_path,
        workflow_id,
    )

    def _run_in_background() -> None:
        try:
            github_service.generate_initial_docs(
                repository_name=request.repository_name,
                repository_path=request.repository_path,
                commit_sha=request.commit_sha,
                workflow_id=workflow_id,
                branch=request.branch,
            )
            logger.info("generate-docs background task finished: workflow=%s", workflow_id)
        except Exception as exc:
            logger.error(
                "generate-docs background task failed: workflow=%s  error=%s",
                workflow_id, exc,
            )

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    return GenerateDocsResponse(
        status="accepted",
        message=(
            f"Documentation generation started for '{request.repository_name}'. "
            f"Poll /api/workflows/{workflow_id} for progress."
        ),
        workflow_id=workflow_id,
        repository_name=request.repository_name,
    )


@router.post(
    "/bootstrap",
    status_code=status.HTTP_200_OK,
    summary="Bootstrap RAG Indexes",
    description=(
        "Builds the full initial FAISS, BM25, and dependency-graph indexes "
        "for a repository from scratch. Run this once after cloning or syncing "
        "a repository. Subsequent GitHub push webhooks will perform incremental "
        "updates automatically."
    ),
    tags=["RAG"],
    response_model=BootstrapResponse,
)
async def bootstrap_repository(request: BootstrapRequest) -> BootstrapResponse:
    """
    Trigger a full index bootstrap for a repository.

    Args:
        request: Bootstrap request with repository_name, repository_path,
                 and optional commit_sha.

    Returns:
        BootstrapResponse: Confirmation with status and repository name.

    Raises:
        HTTPException 500: If the bootstrap pipeline fails fatally.
    """
    logger.info(
        "RAG bootstrap requested: repo=%s  path=%s  sha=%s",
        request.repository_name,
        request.repository_path,
        request.commit_sha,
    )

    try:
        rag = RAGService(repository_name=request.repository_name)
        rag.index_repository(
            repo_path=request.repository_path,
            commit_sha=request.commit_sha,
        )
    except Exception as exc:
        logger.error("RAG bootstrap failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bootstrap failed: {exc}",
        ) from exc

    logger.info("RAG bootstrap completed: repo=%s", request.repository_name)
    return BootstrapResponse(
        status="ok",
        message=(
            f"Bootstrap completed for '{request.repository_name}'. "
            "FAISS, BM25, and dependency-graph indexes are ready."
        ),
        repository_name=request.repository_name,
    )


@router.post(
    "/retrieve",
    status_code=status.HTTP_200_OK,
    summary="Retrieve RAG Context",
    description=(
        "Performs synchronous hybrid retrieval (FAISS + BM25 + dependency graph) "
        "for the given semantic query and returns a ranked ContextPackage. "
        "The repository must have been bootstrapped first. "
        "Can be called by external agents that need code context without "
        "triggering a full GitHub webhook flow."
    ),
    tags=["RAG"],
)
async def retrieve_context(request: RetrieveRequest) -> JSONResponse:
    """
    Perform synchronous hybrid retrieval for a semantic query.

    Args:
        request: RetrieveRequest with repository, commit_sha, and query_text.

    Returns:
        JSONResponse: Serialised ContextPackage with ranked retrieval results.

    Raises:
        HTTPException 500: If retrieval fails fatally.
        HTTPException 404: If no context is found (empty result set).
    """
    logger.info(
        "RAG retrieve requested: repo=%s  sha=%s  query='%s'",
        request.repository,
        request.commit_sha,
        request.query_text[:80],
    )

    try:
        query_kwargs: dict[str, Any] = dict(
            repository=request.repository,
            commit_sha=request.commit_sha,
            query_text=request.query_text,
            changed_files=request.changed_files,
            modified_symbols=request.modified_symbols,
            keywords=request.keywords,
            top_k=request.top_k,
        )
        # Only pass similarity_threshold when the caller explicitly set it;
        # omitting it lets SemanticQuery's own default_factory apply
        # rag.config.settings.similarity_threshold instead.
        if request.similarity_threshold is not None:
            query_kwargs["similarity_threshold"] = request.similarity_threshold

        semantic_query = SemanticQuery(**query_kwargs)

        pipeline = RetrievalPipeline(repository=request.repository)
        context_package = pipeline.retrieve(semantic_query)

    except Exception as exc:
        logger.error("RAG retrieve failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    logger.info(
        "RAG retrieve completed: repo=%s  chunks=%d",
        request.repository,
        context_package.metadata.total_retrieved_chunks,
    )

    # Serialise the Pydantic model to JSON-compatible dict. `embedding` is
    # excluded: it's a 384-float array per chunk (~7-8KB of JSON each) that
    # no current consumer (understanding_agent.py, context_slicer.py) reads
    # — they only use .content and .metadata. Still available internally;
    # just not serialized over this HTTP response.
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=context_package.model_dump(
            mode="json",
            exclude={
                "retrieval_results": {
                    "results": {"__all__": {"chunk": {"embedding"}}},
                },
            },
        ),
    )


@router.get(
    "/status/{repository_name:path}",
    status_code=status.HTTP_200_OK,
    summary="Get RAG Index Status for a Repository",
    description=(
        "Returns real-time indexing status for a specific repository: "
        "whether it has been bootstrapped, how many vectors are stored, "
        "and which vector store backend (pinecone or faiss) is active."
    ),
    tags=["RAG"],
)
async def get_rag_status(repository_name: str) -> JSONResponse:
    """
    Return real-time RAG status for a given repository.

    Args:
        repository_name: Full repo name, e.g. 'owner/repo'.

    Returns:
        JSONResponse with indexing status details.
    """
    logger.info("RAG status requested: repo=%s", repository_name)

    rag_settings = RAGSettings()
    backend = rag_settings.vector_store_backend
    vector_count = 0
    indexed = False
    details: dict = {}

    try:
        if backend == "pinecone":
            from pinecone import Pinecone  # type: ignore[import-untyped]

            api_key = rag_settings.pinecone_api_key
            index_name = rag_settings.pinecone_index_name
            if api_key and index_name:
                pc = Pinecone(api_key=api_key)
                index = pc.Index(index_name)
                stats = index.describe_index_stats()
                ns_stats = stats.namespaces or {}
                if repository_name in ns_stats:
                    vector_count = ns_stats[repository_name].vector_count or 0
                    indexed = vector_count > 0
                details = {
                    "pinecone_index": index_name,
                    "namespace": repository_name,
                    "total_index_vectors": stats.total_vector_count,
                }
        else:
            # FAISS — check if storage files exist on disk
            slug = repository_name.replace("/", "_")
            faiss_path = rag_settings.storage_root / "faiss" / slug / "index.faiss"
            indexed = faiss_path.exists()
            vector_count = -1  # FAISS doesn't expose count easily without loading
            details = {"faiss_path": str(faiss_path)}

    except Exception as exc:
        logger.warning("RAG status check failed for repo=%s: %s", repository_name, exc)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "repository": repository_name,
                "indexed": False,
                "vector_count": 0,
                "backend": backend,
                "error": str(exc),
                "index_stats": read_index_stats(repository_name),
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "repository": repository_name,
            "indexed": indexed,
            "vector_count": vector_count,
            "backend": backend,
            "index_stats": read_index_stats(repository_name),
            **details,
        },
    )


# ---------------------------------------------------------------------------
# Index a repository (clone if needed + bootstrap)
# ---------------------------------------------------------------------------

class IndexRepoRequest(BaseModel):
    """Request body for POST /api/rag/index-repo."""
    repository_name: str = Field(
        ...,
        description="Full repository name, e.g. 'owner/repo'.",
    )
    clone_url: str = Field(
        default="",
        description=(
            "Git clone URL. If omitted, defaults to "
            "'https://github.com/{repository_name}.git'."
        ),
    )


@router.post(
    "/index-repo",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Clone & Index a Repository into the Knowledge Base",
    description=(
        "Clones the repository locally if not already present, then runs a full "
        "bootstrap index (chunking, embeddings, Pinecone/FAISS upsert). "
        "This lets you add any connected repo to the knowledge base without "
        "waiting for a GitHub push webhook to fire. Returns immediately; "
        "indexing runs in the background."
    ),
    tags=["RAG"],
)
async def index_repo(request: IndexRepoRequest) -> JSONResponse:
    """
    Clone (if necessary) + bootstrap a repository into the RAG knowledge base.

    Spawns ``scripts/run_index_repo.py`` as a fully detached subprocess so
    that uvicorn --reload cannot kill the job when new .py files appear in
    repositories/ during the git clone.

    Args:
        request: IndexRepoRequest with repository_name and optional clone_url.

    Returns:
        202 Accepted immediately; detached subprocess performs clone + index.
    """
    import subprocess
    import sys
    from pathlib import Path
    from app.core.config import settings as app_settings

    repo_name = request.repository_name.strip()
    clone_url = request.clone_url.strip() or f"https://github.com/{repo_name}.git"

    slug = repo_name.replace("/", "_")
    repo_root = Path(app_settings.repository_root)
    local_path = str((repo_root / slug).resolve())

    # Ensure repo root dir exists before spawning the subprocess
    repo_root.mkdir(parents=True, exist_ok=True)

    logger.info(
        "index-repo: spawning detached subprocess  repo=%s  clone=%s  dest=%s",
        repo_name, clone_url, local_path,
    )

    # Path to the standalone indexing script (lives next to this package)
    _backend_root = Path(__file__).resolve().parent.parent.parent  # backend/
    script_path = str(_backend_root / "scripts" / "run_index_repo.py")

    # On Windows, prefer pythonw.exe (the windowless GUI-subsystem build that
    # ships alongside python.exe in every venv/install) over sys.executable.
    # DETACHED_PROCESS is supposed to suppress the console, but on Windows 11
    # the OS's "default terminal application" setting can still surface a
    # console-subsystem child (python.exe) in a visible window regardless of
    # creation flags. pythonw.exe never allocates a console in the first
    # place, so it isn't subject to that behavior at all.
    python_exe = sys.executable
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            python_exe = str(pythonw)

    cmd = [python_exe, script_path, repo_name, clone_url, local_path]

    try:
        if sys.platform == "win32":
            # DETACHED_PROCESS (0x00000008) + CREATE_NEW_PROCESS_GROUP (0x00000200)
            # detach from this process's console/signals. CREATE_BREAKAWAY_FROM_JOB
            # (0x01000000) is also required: when uvicorn is launched from a terminal
            # (VS Code, Windows Terminal, etc.), Windows assigns it to a Job Object
            # with "kill on job close" semantics, and child processes are added to
            # that same job by default even when DETACHED_PROCESS is set. Without
            # breakaway, the "detached" subprocess is still silently killed if the
            # parent job is torn down. If the job doesn't permit breakaway, Popen
            # raises OSError — retry without the flag rather than failing the request.
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            # The child inherits its own duplicated copy of this fd on
            # Popen(); the parent's handle must be closed afterward or it
            # leaks for the lifetime of this long-running uvicorn worker
            # (one leaked fd per "Add to KB" click).
            log_file = open(str(_backend_root / "logs" / f"index_repo_{slug}.log"), "w")
            try:
                try:
                    subprocess.Popen(
                        cmd,
                        creationflags=(
                            DETACHED_PROCESS
                            | CREATE_NEW_PROCESS_GROUP
                            | CREATE_BREAKAWAY_FROM_JOB
                        ),
                        close_fds=True,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
                except OSError:
                    logger.warning(
                        "index-repo: CREATE_BREAKAWAY_FROM_JOB rejected by parent job "
                        "for '%s' — retrying without breakaway (subprocess may not "
                        "survive a parent reload).",
                        repo_name,
                    )
                    subprocess.Popen(
                        cmd,
                        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                        close_fds=True,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
            finally:
                log_file.close()
        else:
            # On Unix: start a new session so the process is fully detached
            log_file = open(str(_backend_root / "logs" / f"index_repo_{slug}.log"), "w")
            try:
                subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    close_fds=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
            finally:
                log_file.close()
        logger.info("index-repo: detached subprocess launched for '%s'", repo_name)
    except Exception as exc:
        logger.error("index-repo: failed to spawn subprocess for '%s': %s", repo_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start indexing subprocess: {exc}",
        ) from exc

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "message": (
                f"Cloning and indexing '{repo_name}' in the background. "
                "This may take 1-3 minutes. Refresh the Knowledge Base list to see it appear."
            ),
            "repository": repo_name,
            "log_file": f"logs/index_repo_{slug}.log",
        },
    )



# Module-level cache for knowledge base listing to prevent Pinecone network hangs
_kb_cache_data: dict = {}
_kb_cache_timestamp: float = 0.0
_KB_CACHE_TTL: float = 30.0



@router.get(
    "/repos",
    status_code=status.HTTP_200_OK,
    summary="List All Repositories with RAG Status",
    description=(
        "Returns all locally cloned repositories (from the repositories/ directory) "
        "along with their RAG indexing status in the vector store. "
        "Use this to populate the Knowledge Base page with repos that can be added."
    ),
    tags=["RAG"],
)
async def list_repos_with_rag_status() -> JSONResponse:
    """
    Return all local repositories and whether they are indexed in the knowledge base.

    Scans the repositories/ directory for cloned repos, then cross-references
    each repo against the Pinecone namespace stats to determine indexed status.
    """
    from pathlib import Path
    from app.core.config import settings as app_settings

    rag_settings = RAGSettings()
    backend = rag_settings.vector_store_backend

    # Build a map of namespace → vector_count from Pinecone
    indexed_namespaces: dict[str, int] = {}
    try:
        if backend == "pinecone":
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            from pinecone import Pinecone  # type: ignore[import-untyped]

            api_key = rag_settings.pinecone_api_key
            index_name = rag_settings.pinecone_index_name
            if api_key and index_name:
                def _fetch():
                    pc = Pinecone(api_key=api_key)
                    idx = pc.Index(index_name)
                    return idx.describe_index_stats()

                loop = asyncio.get_running_loop()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    stats = await asyncio.wait_for(
                        loop.run_in_executor(pool, _fetch),
                        timeout=12.0,
                    )
                for ns, ns_info in (stats.namespaces or {}).items():
                    indexed_namespaces[ns] = ns_info.vector_count or 0
    except Exception as exc:
        logger.warning("list_repos_with_rag_status: Pinecone stats fetch failed: %s", exc)

    # Scan local repositories/ directory
    repo_root = Path(app_settings.repository_root)
    repos = []
    if repo_root.exists():
        for entry in sorted(repo_root.iterdir()):
            if not entry.is_dir():
                continue
            # Convert "owner_repo-name" → "owner/repo-name" (first underscore only)
            repo_name = entry.name.replace("_", "/", 1)
            vector_count = indexed_namespaces.get(repo_name, 0)
            repos.append({
                "repository": repo_name,
                "local_path": str(entry.resolve()),
                "indexed": vector_count > 0,
                "vector_count": vector_count,
                "backend": backend,
            })

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"repos": repos, "backend": backend},
    )


@router.get(
    "/knowledge-base",
    status_code=status.HTTP_200_OK,
    summary="List Knowledge Base Repositories",
    description="Returns all repositories that have embeddings stored in the vector store.",
    tags=["RAG"],
)
async def list_knowledge_base() -> JSONResponse:

    """
    Return all repositories that have embeddings stored.

    For Pinecone: reads namespace stats from the cloud index with caching & timeout.
    For FAISS: scans the local storage directory for index files.
    """
    global _kb_cache_data, _kb_cache_timestamp
    import time
    import asyncio

    now = time.time()
    if _kb_cache_data and (now - _kb_cache_timestamp < _KB_CACHE_TTL):
        return JSONResponse(status_code=status.HTTP_200_OK, content=_kb_cache_data)

    logger.info("Knowledge base list requested")

    rag_settings = RAGSettings()
    backend = rag_settings.vector_store_backend
    repos: list[dict] = []

    try:
        if backend == "pinecone":
            from pinecone import Pinecone  # type: ignore[import-untyped]
            from concurrent.futures import ThreadPoolExecutor

            api_key = rag_settings.pinecone_api_key
            index_name = rag_settings.pinecone_index_name

            if not api_key or not index_name:
                res = {"backend": backend, "repos": [], "error": "Pinecone not configured"}
                _kb_cache_data = res
                _kb_cache_timestamp = now
                return JSONResponse(status_code=status.HTTP_200_OK, content=res)

            def _fetch_pinecone_stats():
                pc = Pinecone(api_key=api_key)
                index = pc.Index(index_name)
                return index.describe_index_stats()

            # Execute Pinecone call with 12.0s timeout to allow HTTPS API response
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                stats = await asyncio.wait_for(
                    loop.run_in_executor(pool, _fetch_pinecone_stats),
                    timeout=12.0,
                )


            namespaces = stats.namespaces or {}

            # Sidecar directory holds full chunk content alongside Pinecone vectors
            sidecar_root = rag_settings.storage_root / "pinecone"

            for namespace, ns_info in namespaces.items():
                vector_count = ns_info.vector_count or 0
                file_count = 0
                chunk_count_sidecar = 0

                # Try to read sidecar for file-level metadata
                slug = namespace.replace("/", "_")
                sidecar_path = sidecar_root / slug / "chunks.json"
                if sidecar_path.exists():
                    try:
                        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
                        chunks: dict = payload.get("chunks", {})
                        chunk_count_sidecar = len(chunks)
                        file_count = len(
                            {
                                c.get("metadata", {}).get("file_path", "")
                                for c in chunks.values()
                                if c.get("metadata", {}).get("active", True)
                            }
                        )
                    except Exception:
                        pass  # sidecar unreadable — fall back to vector counts

                repos.append(
                    {
                        "repository": namespace,
                        "vector_count": vector_count,
                        "file_count": file_count,
                        "chunk_count": chunk_count_sidecar or vector_count,
                        "indexed": vector_count > 0,
                        "backend": backend,
                        "pinecone_index": index_name,
                    }
                )

        else:
            # FAISS backend — scan local storage dirs
            faiss_root = rag_settings.storage_root / "faiss"
            if faiss_root.exists():
                for slug_dir in faiss_root.iterdir():
                    if not slug_dir.is_dir():
                        continue
                    if not (slug_dir / "index.faiss").exists():
                        continue
                    # Convert slug back to repo name (best-effort: first _ → /)
                    repo_name = slug_dir.name.replace("_", "/", 1)
                    repos.append(
                        {
                            "repository": repo_name,
                            "vector_count": -1,
                            "file_count": -1,
                            "chunk_count": -1,
                            "indexed": True,
                            "backend": backend,
                        }
                    )

    except Exception as exc:
        logger.warning("Knowledge base list timeout or error: %s", exc)
        if _kb_cache_data:
            return JSONResponse(status_code=status.HTTP_200_OK, content=_kb_cache_data)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"backend": backend, "repos": []},
        )


    res = {"backend": backend, "repos": repos}
    _kb_cache_data = res
    _kb_cache_timestamp = now
    logger.info("Knowledge base: found %d embedded repo(s)", len(repos))
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=res,
    )


@router.delete(
    "/knowledge-base/{repository_name:path}",
    status_code=status.HTTP_200_OK,
    summary="Delete a Repository from the Knowledge Base",
    description="Erases all vectors and local sidecar caches for the given repository.",
    tags=["RAG"],
)
async def delete_knowledge_base_repo(repository_name: str) -> JSONResponse:
    """
    Delete a repository from the RAG knowledge base.
    """
    global _kb_cache_data, _kb_cache_timestamp

    success = _rag_service.delete_repository(repository_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete repository '{repository_name}' from knowledge base.",
        )

    # Invalidate the KB list cache so the UI reflects the deletion immediately
    # (without this, the deleted repo would still appear for up to _KB_CACHE_TTL seconds,
    # causing users to retry the delete which then fails with Pinecone 404 → 500).
    _kb_cache_data = {}
    _kb_cache_timestamp = 0.0
    logger.info("Knowledge base cache invalidated after deleting '%s'", repository_name)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "deleted", "repository": repository_name},
    )
