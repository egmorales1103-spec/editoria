"""User-facing errors of the ingest/analysis/versioning modules (messages in Spanish)."""

from __future__ import annotations


class IngestError(Exception):
    """A problem the user can fix; the message is shown as is (Spanish)."""
