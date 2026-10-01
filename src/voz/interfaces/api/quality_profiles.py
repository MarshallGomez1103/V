"""Read-only catalog of quality profiles plus the measured recommendation."""

from __future__ import annotations

from fastapi import APIRouter

from voz.application.quality_profiles import (
    DEFAULT_PROFILE_NAME,
    PROFILES,
    recommend_profile,
)


def create_quality_profiles_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["quality-profiles"])

    def list_profiles(language: str | None = None) -> dict[str, object]:
        recommendation = recommend_profile(language)
        return {
            "default": DEFAULT_PROFILE_NAME,
            "profiles": [
                {
                    "name": entry.profile.name,
                    "label": entry.label,
                    "description": entry.description,
                    "parameters": entry.profile.to_dict(),
                }
                for entry in PROFILES
            ],
            "recommendation": {
                "language": recommendation.language,
                "profile": recommendation.profile,
                "measured": recommendation.measured,
                "evidence": recommendation.evidence,
                "synthetic": recommendation.synthetic,
                "unmeasured_profiles": list(recommendation.unmeasured_profiles),
            },
        }

    router.add_api_route("/quality-profiles", list_profiles, methods=["GET"])
    return router


__all__ = ["create_quality_profiles_router"]
