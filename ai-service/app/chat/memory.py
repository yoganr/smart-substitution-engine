"""In-process per-session conversation memory.

Deliberately simple: a dict keyed by ``session_id`` holding a bounded message
history plus a small ``WorkingContext`` (resolved product, company, pending
slot). Single-process only — swap for Redis/Mongo if the service is scaled out.
"""

from __future__ import annotations

from app.chat.state import WorkingContext


class SessionStore:
    def __init__(self, max_history: int = 20) -> None:
        self._sessions: dict[str, dict] = {}
        self._max_history = max_history

    def _session(self, session_id: str) -> dict:
        return self._sessions.setdefault(session_id, {"history": [], "context": {}})

    def get_history(self, session_id: str) -> list[dict]:
        return list(self._session(session_id)["history"])

    def get_context(self, session_id: str) -> WorkingContext:
        return dict(self._session(session_id)["context"])

    def set_context(self, session_id: str, context: WorkingContext) -> None:
        self._session(session_id)["context"] = dict(context or {})

    def append(self, session_id: str, role: str, content: str) -> None:
        history = self._session(session_id)["history"]
        history.append({"role": role, "content": content})
        # Keep only the most recent turns to bound memory.
        if len(history) > self._max_history:
            del history[: len(history) - self._max_history]

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
