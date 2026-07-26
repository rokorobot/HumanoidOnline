"""R1 — application-level admin authentication (B1 **stage 1**).

Gap B1: `/admin` shipped completely unauthenticated — SQLAdmin with no
authentication backend, 21 model views with full CRUD, on the same ASGI app as
the public API, exposing buyer `contact_email` / `organization`. The only
mitigation was a code comment saying "network-gate in deployment".

This module closes the *application* half. It deliberately does **not** pretend
the network boundary exists:

  stage 1  R1  (WS8.1, here)  application authentication/authorization
  stage 2  R27 (WS8.7)        admin on a separate protected host/listener (DEP P4)
  stage 3  R29 (WS8.8)        external probe proving the boundary cannot be bypassed

Both layers are mandatory under §11 D1 — neither substitutes for the other.

Fail-closed (WS8-L5): if credentials or the session secret are absent, the admin
surface is **not mounted at all** rather than mounted unprotected.
"""
from __future__ import annotations

import secrets

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

SESSION_KEY = "admin_user"


def _constant_time_equals(supplied: str, expected: str) -> bool:
    """Compare without leaking length/prefix through timing."""
    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


class AdminAuth(AuthenticationBackend):
    """Session-cookie authentication for the internal admin.

    Single operator credential: the admin is an internal tool, and WS8 must not
    introduce user accounts or public authentication (WS8-L1, §12 OUT-list).
    """

    def __init__(self, secret_key: str, username: str, password: str) -> None:
        super().__init__(secret_key=secret_key)
        self._username = username
        self._password = password

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        # Evaluate both comparisons regardless of the first result so a wrong
        # username is not distinguishable from a wrong password by timing.
        username_ok = _constant_time_equals(username, self._username)
        password_ok = _constant_time_equals(password, self._password)
        if username_ok and password_ok:
            request.session.update({SESSION_KEY: self._username})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool | RedirectResponse:
        return bool(request.session.get(SESSION_KEY))
