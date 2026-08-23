"""
app/api/health.py
------------------
Health check endpoint.

Responsibilities:
- Respond to GET /health with the application status
- No business logic
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    summary="Health Check",
    description="Returns the current health status of the application.",
    tags=["Health"],
)
async def health_check() -> JSONResponse:
    """Return a simple health-check response.

    Returns:
        JSONResponse: ``{"status": "healthy"}`` with HTTP 200.
    """
    logger.debug("Health check requested")
    return JSONResponse(content={"status": "healthy"}, status_code=200)
