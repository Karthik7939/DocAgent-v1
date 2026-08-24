"""
scripts/run_index_repo.py
--------------------------
Standalone script invoked by the /api/rag/index-repo endpoint as a detached
subprocess so that uvicorn --reload cannot kill the indexing job.

Usage (internal — called programmatically):
    python scripts/run_index_repo.py <repository_name> <clone_url> <local_path>

All three arguments are required.
"""

import sys
import os
import logging

# ── Bootstrap: make sure the backend root is on sys.path ──────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# Load .env so settings resolve correctly
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_index_repo")


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: run_index_repo.py <repo_name> <clone_url> <local_path>", file=sys.stderr)
        return 1

    repo_name = sys.argv[1]
    clone_url = sys.argv[2]
    local_path = sys.argv[3]

    logger.info("run_index_repo: START  repo=%s  clone=%s  dest=%s", repo_name, clone_url, local_path)

    # ── Step 1: clone or pull ──────────────────────────────────────────────────
    try:
        from app.core.config import settings as app_settings
        from services.git_service import GitService

        os.makedirs(os.path.dirname(local_path) if not local_path.endswith(os.sep) else local_path, exist_ok=True)
        git = GitService(repository_root=app_settings.repository_root)
        git.sync_repository(clone_url=clone_url, local_path=local_path)
        logger.info("run_index_repo: git sync complete")
    except Exception as exc:
        logger.error("run_index_repo: git sync FAILED: %s", exc)
        return 2

    # ── Step 2: RAG bootstrap ──────────────────────────────────────────────────
    try:
        from services.rag_service import RAGService

        rag = RAGService(repository_name=repo_name)
        rag.index_repository(repo_path=local_path, commit_sha="HEAD")
        logger.info("run_index_repo: RAG bootstrap complete")
    except Exception as exc:
        logger.error("run_index_repo: RAG bootstrap FAILED: %s", exc)
        return 3

    logger.info("run_index_repo: DONE  repo=%s", repo_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
