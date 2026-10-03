"""``/api/desktop-shortcut``: check or (re)create the desktop icon that opens VOZ.

Creating files outside VOZ's own folders needs the custom header (a page on
another origin cannot send it without a CORS preflight, which VOZ never allows).
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from voz.application.ports.desktop_shortcut import DesktopShortcut, DesktopShortcutError

ACTION_HEADER = "X-VOZ-Action"
ACTION_VALUE = "desktop-shortcut"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def create_desktop_shortcut_router(shortcut: DesktopShortcut) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["server"])

    def view() -> dict[str, object]:
        supported = shortcut.supported()
        return {
            "supported": supported,
            "exists": supported and shortcut.exists(),
            "path": shortcut.location() if supported else None,
        }

    def get_shortcut() -> dict[str, object]:
        return view()

    def post_shortcut(
        action: str | None = Header(default=None, alias=ACTION_HEADER),
    ) -> dict[str, object]:
        if action != ACTION_VALUE:
            raise _error(
                403,
                "desktop_shortcut_forbidden",
                f"Send the header {ACTION_HEADER}: {ACTION_VALUE}.",
            )
        if not shortcut.supported():
            raise _error(
                409,
                "desktop_shortcut_unsupported",
                "VOZ must run from its folder (with the Iniciar launchers) to "
                "create a shortcut.",
            )
        try:
            shortcut.create()
        except DesktopShortcutError:
            raise _error(
                500,
                "desktop_shortcut_failed",
                "The shortcut could not be created.",
            ) from None
        return view()

    router.add_api_route("/desktop-shortcut", get_shortcut, methods=["GET"])
    router.add_api_route(
        "/desktop-shortcut", post_shortcut, methods=["POST"], status_code=201
    )
    return router


__all__ = ["ACTION_HEADER", "ACTION_VALUE", "create_desktop_shortcut_router"]
