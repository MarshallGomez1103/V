"""Visible data about a cloud provider; the backend is the UI's source of truth."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CloudProviderInfo:
    id: str
    label: str
    privacy_url: str | None = None
