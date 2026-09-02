"""Application composition root.

Framework and infrastructure wiring belongs here so that the domain remains
independent of transport concerns.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from voz import __version__
from voz.interfaces.api.health import router as health_router

STATIC_DIRECTORY = Path(__file__).with_name("static")


def create_app() -> FastAPI:
    """Build the local VOZ HTTP application."""
    application = FastAPI(
        title="VOZ",
        description="Local-first transcription workspace API.",
        version=__version__,
    )
    application.include_router(health_router)
    if STATIC_DIRECTORY.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=STATIC_DIRECTORY, html=True),
            name="web",
        )
    return application


app = create_app()
