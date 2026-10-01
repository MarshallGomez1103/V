"""The backend names providers; options carry the label of cloud providers."""

from voz.application.ports.transcription_options import InstallationStatus
from voz.infrastructure.cloud.catalog import CloudTranscriptionCatalog
from voz.infrastructure.cloud.openai_limits import openai_descriptors
from voz.infrastructure.cloud.provider_info import (
    CLOUD_PROVIDER_INFO,
    CLOUD_PROVIDER_LABELS,
)


def test_every_shipped_provider_has_label_and_https_privacy_link() -> None:
    assert [info.id for info in CLOUD_PROVIDER_INFO] == ["openai", "elevenlabs"]
    for info in CLOUD_PROVIDER_INFO:
        assert info.label
        assert info.privacy_url is not None
        assert info.privacy_url.startswith("https://")


def test_catalog_attaches_the_provider_label_to_cloud_registrations() -> None:
    catalog = CloudTranscriptionCatalog(openai_descriptors(), CLOUD_PROVIDER_LABELS)
    registrations = catalog.list_models()
    assert registrations
    assert {r.provider_label for r in registrations} == {"OpenAI"}
    assert all(
        r.installation_status is InstallationStatus.REGISTERED for r in registrations
    )


def test_catalog_without_labels_leaves_the_label_empty() -> None:
    registrations = CloudTranscriptionCatalog(openai_descriptors()).list_models()
    assert {r.provider_label for r in registrations} == {None}
