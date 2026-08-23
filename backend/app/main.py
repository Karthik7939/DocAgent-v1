"""
app/main.py
------------
FastAPI application entry point.

Responsibilities:
- Create the FastAPI application instance
- Register the API router
- Configure CORS middleware
- Initialise logging on startup
- Define startup / shutdown lifecycle events
- No business logic
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logger import setup_logging
from utils.file_utils import ensure_directory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        FastAPI: A fully configured application instance.
    """
    app = FastAPI(
        title="GitHub Repository Workflow Backend",
        description=(
            "Webhook processing service for GitHub repositories. "
            "Receives push events, synchronises local repositories, "
            "parses commit data, and persists workflow state."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    app.include_router(api_router)

    # --- Lifecycle events ---
    @app.on_event("startup")
    async def on_startup() -> None:
        """Run when the application starts.

        - Initialises structured logging (console + rotating file).
        - Ensures required runtime directories exist.
        - Eagerly initializes the embedding model.
        """
        setup_logging(log_level=settings.log_level, log_file=settings.log_file)
        ensure_directory(settings.repository_root)
        ensure_directory(settings.workflow_path)
        logger.info("Application started")
        logger.info("Repository root : %s", settings.repository_root)
        logger.info("Workflow path   : %s", settings.workflow_path)
        logger.info("Log level       : %s", settings.log_level)
        
        # Eagerly initialize the embedding model to prevent 'atexit after shutdown'
        # errors that occur when it is lazily loaded inside a background thread.
        from rag.embeddings.embedder import Embedder
        logger.info("Eagerly loading embedding model...")
        Embedder().model
        logger.info("Embedding model loaded.")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        """Run when the application shuts down."""
        logger.info("Application shutting down")

    return app


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app: FastAPI = create_application()
