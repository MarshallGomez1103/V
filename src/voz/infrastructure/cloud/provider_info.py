"""Visible name and privacy policy link of every cloud provider VOZ ships."""

from __future__ import annotations

from typing import Final

from voz.application.ports.cloud_providers import CloudProviderInfo

# ponytail: the order here is the order the UI lists providers in.
CLOUD_PROVIDER_INFO: Final = (
    CloudProviderInfo("openai", "OpenAI", "https://openai.com/policies/privacy-policy"),
    CloudProviderInfo("elevenlabs", "ElevenLabs", "https://elevenlabs.io/privacy"),
)
CLOUD_PROVIDER_LABELS: Final = {info.id: info.label for info in CLOUD_PROVIDER_INFO}
