"""``POST /api/shutdown``: let the web UI close the local server.

The job in flight stays recoverable (same path as Ctrl+C: the lifespan stops the
worker at a safe point). A custom request header is required, so a page on
another origin cannot trigger it without a CORS preflight, which VOZ never allows.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException

SHUTDOWN_HEADER = "X-VOZ-Action"
SHUTDOWN_VALUE = "shutdown"
SHUTDOWN_DELAY_S = 0.5
"""Time given to the 202 response to reach the browser before the server stops."""


def create_shutdown_router(
    request_shutdown: Callable[[], None] | None,
    *,
    delay_s: float = SHUTDOWN_DELAY_S,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["server"])

    def shutdown(
        action: str | None = Header(default=None, alias=SHUTDOWN_HEADER),
    ) -> dict[str, str]:
        if action != SHUTDOWN_VALUE:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "shutdown_forbidden",
                    "message": f"Send the header {SHUTDOWN_HEADER}: {SHUTDOWN_VALUE}.",
                },
            )
        if request_shutdown is None:
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "shutdown_unavailable",
                    "message": "This server was not started by the voz command.",
                },
            )
        timer = threading.Timer(delay_s, request_shutdown)
        timer.daemon = True
        timer.start()
        return {"status": "stopping"}

    router.add_api_route("/shutdown", shutdown, methods=["POST"], status_code=202)
    return router


__all__ = ["SHUTDOWN_HEADER", "SHUTDOWN_VALUE", "create_shutdown_router"]
