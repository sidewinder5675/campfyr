"""Compatibility import for code that used the original module name."""

from campfyr.recreation import RecreationClient, RecreationError


__all__ = ["RecreationClient", "RecreationError"]
