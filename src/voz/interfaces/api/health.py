"""Health endpoint for local readiness checks."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from voz import __version__

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(BaseModel):
    """Public, path-free readiness response."""

    status: Literal["ok"] = "ok"
    version: str


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Report that the local API is ready without leaking host details."""
    return HealthResponse(version=__version__)
