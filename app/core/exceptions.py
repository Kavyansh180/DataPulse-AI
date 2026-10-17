"""DataPulse AI — Core Exceptions.

Provides database-independent, lightweight application exceptions.
"""

from typing import Any, Optional


class APIError(Exception):
    """Custom application exception with structured error code and message."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: str = "BAD_REQUEST",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details
