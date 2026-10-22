"""Stable, user-safe failures of the synthesis use cases."""

from __future__ import annotations

from enum import StrEnum


class SynthesisJobFailureCode(StrEnum):
    """Codes translated one-to-one by the HTTP adapter; never rename one."""

    PROVIDER_NOT_FOUND = "synthesis_provider_not_found"
    MODEL_UNKNOWN = "synthesis_model_unknown"
    MODEL_NOT_INSTALLED = "synthesis_model_not_installed"
    RUNTIME_UNAVAILABLE = "synthesis_runtime_unavailable"
    VOICE_NOT_FOUND = "synthesis_voice_not_found"
    REQUEST_INVALID = "synthesis_request_invalid"
    JOB_NOT_FOUND = "synthesis_job_not_found"
    JOB_TERMINAL = "synthesis_job_terminal"
    JOB_ACTIVE = "synthesis_job_active"
    CLOUD_CONSENT_REQUIRED = "cloud_consent_required"


class SynthesisJobError(RuntimeError):
    """Typed use-case failure with a message safe to show in the browser."""

    def __init__(self, code: SynthesisJobFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


__all__ = ["SynthesisJobError", "SynthesisJobFailureCode"]
