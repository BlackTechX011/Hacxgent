from __future__ import annotations

from hacxgent.core.llm.backend.universal import UniversalBackend

BACKEND_FACTORY = {
    "hacxgent": UniversalBackend,
    "generic": UniversalBackend
}
