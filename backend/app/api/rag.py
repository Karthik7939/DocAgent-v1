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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.dependencies import get_github_service
from rag.config.settings import RAGSettings
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
    similarity_threshold: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score.",
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
        semantic_query = SemanticQuery(
            repository=request.repository,
            commit_sha=request.commit_sha,
            query_text=request.query_text,
            changed_files=request.changed_files,
            modified_symbols=request.modified_symbols,
            keywords=request.keywords,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

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

    # Serialise the Pydantic model to JSON-compatible dict
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=context_package.model_dump(mode="json"),
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
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "repository": repository_name,
            "indexed": indexed,
            "vector_count": vector_count,
            "backend": backend,
            **details,
        },
    )


# Module-level cache for knowledge base listing to prevent Pinecone network hangs
_kb_cache_data: dict = {}
_kb_cache_timestamp: float = 0.0
_KB_CACHE_TTL: float = 30.0


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
    success = _rag_service.delete_repository(repository_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete repository '{repository_name}' from knowledge base.",
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "deleted", "repository": repository_name},
    )
