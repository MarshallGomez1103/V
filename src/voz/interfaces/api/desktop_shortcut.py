"""``/api/desktop-shortcut``: check, (re)create or remove the desktop icon that opens V.

Changing files outside V's own folders needs a custom header (a page on
another origin cannot send it without a CORS preflight, which VOZ never allows).
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from voz.application.ports.desktop_shortcut import DesktopShortcut, DesktopShortcutError
from voz.interfaces.api.errors import api_error

ACTION_HEADER = "X-VOZ-Action"
ACTION_VALUE = "desktop-shortcut"
REMOVE_ACTION_VALUE = "remove-desktop-shortcut"


def create_desktop_shortcut_router(shortcut: DesktopShortcut) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["server"])

    def view() -> dict[str, object]:
        return {
            "supported": shortcut.supported(),
            "exists": shortcut.exists(),
            "broken": shortcut.broken(),
            "path": shortcut.location(),
        }

    def require(action: str | None, expected: str) -> None:
        if action != expected:
            raise api_error(
                403,
                "desktop_shortcut_forbidden",
                f"Send the header {ACTION_HEADER}: {expected}.",
            )

    def get_shortcut() -> dict[str, object]:
        return view()

    def post_shortcut(
        action: str | None = Header(default=None, alias=ACTION_HEADER),
    ) -> dict[str, object]:
        require(action, ACTION_VALUE)
        if not shortcut.supported():
            raise api_error(
                409,
                "desktop_shortcut_unsupported",
                "V must run from its folder (with the Start-V launchers) or be "
                "installed with the v command to create a shortcut.",
            )
        try:
            shortcut.create()
        except DesktopShortcutError:
            raise api_error(
                500,
                "desktop_shortcut_failed",
                "The shortcut could not be created.",
            ) from None
        return view()

    def delete_shortcut(
        action: str | None = Header(default=None, alias=ACTION_HEADER),
    ) -> dict[str, object]:
        require(action, REMOVE_ACTION_VALUE)
        try:
            shortcut.remove()
        except DesktopShortcutError:
            raise api_error(
                500,
                "desktop_shortcut_remove_failed",
                "The shortcut could not be removed.",
            ) from None
        return view()

    router.add_api_route("/desktop-shortcut", get_shortcut, methods=["GET"])
    router.add_api_route("/desktop-shortcut", delete_shortcut, methods=["DELETE"])
    router.add_api_route(
        "/desktop-shortcut", post_shortcut, methods=["POST"], status_code=201
    )
    return router


__all__ = [
    "ACTION_HEADER",
    "ACTION_VALUE",
    "REMOVE_ACTION_VALUE",
    "create_desktop_shortcut_router",
]
