"""The exception name is part of docs/interface.md; D catches it verbatim."""


class OcrExtractionError(Exception):
    """Unreadable document or missing/ambiguous fields; messages contain no PII."""
