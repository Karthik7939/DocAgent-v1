"""
app/core/config.py
------------------
Environment variable reader.

Responsibilities:
- Load values from the .env file via python-dotenv
- Expose a single, importable `settings` object
- No hardcoded secrets; all sensitive values come from the environment
"""

from functools import lru_cache

from app.core.settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Construct and cache the application Settings object.

    Using lru_cache ensures the .env file is read only once per process
    lifetime, which is efficient and avoids repeated disk I/O.

    Returns:
        Settings: The populated settings instance.
    """
    return Settings()


# Module-level singleton — import this everywhere you need configuration.
settings: Settings = get_settings()
