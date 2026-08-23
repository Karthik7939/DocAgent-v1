"""
utils/helpers.py
----------------
General-purpose utility helpers.

Responsibilities:
- UUID generation
- ISO-8601 timestamp generation
- Consistent JSON response formatting
"""

import uuid
from datetime import datetime, timezone


def generate_uuid() -> str:
    """Generate a random UUID4 string.

    Returns:
        str: A UUID4 string, e.g. '3fa85f64-5717-4562-b3fc-2c963f66afa6'.
    """
    return str(uuid.uuid4())


def generate_timestamp() -> str:
    """Generate a current UTC timestamp in ISO-8601 format.

    Returns:
        str: Timestamp string, e.g. '2026-06-30T10:20:00Z'.
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_success_response(data: dict) -> dict:
    """Wrap a data payload in a standard success envelope.

    Args:
        data: Arbitrary key/value pairs to include in the response.

    Returns:
        dict: Response dict with 'status' set to 'success' and all data fields merged in.
    """
    return {"status": "success", **data}


def build_error_response(message: str) -> dict:
    """Wrap an error message in a standard error envelope.

    Args:
        message: Human-readable description of what went wrong.

    Returns:
        dict: Response dict with 'status' set to 'error' and the message.
    """
    return {"status": "error", "message": message}
