"""Exceptions for the SPA Booking integration."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError


class SpaBookingError(HomeAssistantError):
    """Base error for the SPA Booking integration."""


class NotFoundError(SpaBookingError):
    """Raised when a referenced record does not exist."""


class ValidationError(SpaBookingError):
    """Raised when the supplied data is inconsistent."""


class OverlapError(SpaBookingError):
    """Raised when an appointment overlaps an existing one."""

    def __init__(self, message: str, conflicts: list[dict[str, Any]] | None = None) -> None:
        """Initialize the error and keep the conflicting appointments."""
        super().__init__(message)
        self.conflicts: list[dict[str, Any]] = conflicts or []