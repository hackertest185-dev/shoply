"""Per-request context used to correlate audit records without logging secrets."""
from contextvars import ContextVar

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
