"""Static bearer-token authentication for the HTTP transport.

Our deployment has exactly one trusted caller (the Next.js server), so a single
shared secret is the right weight — no OAuth dance needed. The server is given
the secret via ``MCP_AUTH_TOKEN``; the client sends it as
``Authorization: Bearer <token>``. Requests with a missing/wrong token are
rejected with 401 by FastMCP's auth middleware.

Auth is only attached when ``MCP_AUTH_TOKEN`` is set, so local stdio runs (the
Inspector, the local Next.js client) stay unauthenticated and frictionless.
"""

from __future__ import annotations

import hmac

from fastmcp.server.auth import AccessToken, TokenVerifier


class StaticTokenVerifier(TokenVerifier):
    """Accepts a single pre-shared bearer token (constant-time comparison)."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token, self._token):
            return AccessToken(token=token, client_id="lol-web-client", scopes=[])
        return None
