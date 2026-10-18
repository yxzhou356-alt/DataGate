"""Demo sessions. THIS IS NOT PRODUCTION AUTHENTICATION.

Anyone running the local demo can pick a seeded account and get a token. What
matters for the baseline is that every protected route derives identity from
the server-issued token, never from user_id/role fields in a request body.
Tokens live in memory and disappear on backend restart.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Request

from .errors import ApiError


@dataclass(frozen=True)
class Session:
    account_id: str
    expires_at: float


class SessionStore:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def issue(self, account_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = Session(account_id, time.time() + self.ttl)
        return token

    def resolve(self, token: str) -> str | None:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at < time.time():
                del self._sessions[token]
                return None
            return session.account_id


def current_account(request: Request) -> str:
    """FastAPI dependency: account id from the bearer token."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if not header:
        raise ApiError("AUTH_REQUIRED")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError("INVALID_SESSION")
    account_id = request.app.state.sessions.resolve(token.strip())
    if account_id is None:
        raise ApiError("INVALID_SESSION")
    return account_id
