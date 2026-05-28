"""Optional evidence retrieval client loader."""
from __future__ import annotations

try:
    from services._kb_backend import (  # noqa: F401
        Client as EvidenceClient,
        Config as EvidenceConfig,
        Error as EvidenceError,
    )
except ImportError:
    EvidenceClient = None
    EvidenceConfig = None

    class EvidenceError(Exception):
        pass
