"""Built-in profiles and the measured-only recommendation (S13.02/S13.11)."""

from __future__ import annotations

from voz.application.quality_profiles import (
    ACADEMIC_PROFILE,
    DEFAULT_PROFILE,
    MEASUREMENTS,
    PROFILES,
    ProfileMeasurement,
    get_profile,
    recommend_profile,
)


def test_catalog_has_unique_named_profiles() -> None:
    names = [entry.profile.name for entry in PROFILES]

    assert names == ["default", "academic"]
    assert get_profile("academic") is ACADEMIC_PROFILE
    assert get_profile("nope") is None


def test_default_profile_is_the_engine_default_without_vad() -> None:
    assert DEFAULT_PROFILE.vad is None
    assert DEFAULT_PROFILE.beam_size == 5
    assert DEFAULT_PROFILE.condition_on_previous_text is True
    assert DEFAULT_PROFILE.temperature == (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def test_academic_profile_differs_where_documented() -> None:
    assert ACADEMIC_PROFILE.condition_on_previous_text is False
    assert ACADEMIC_PROFILE.vad is not None
    assert len(ACADEMIC_PROFILE.temperature) < len(DEFAULT_PROFILE.temperature)


def test_spanish_is_measured_and_regional_tags_map_to_it() -> None:
    for tag in ("es", "ES", "es-CO", "es_MX"):
        recommendation = recommend_profile(tag)

        assert recommendation.measured is True
        assert recommendation.language == "es"
        assert recommendation.profile == "default"
        assert recommendation.synthetic is True
        assert "docs/benchmarks.md" in recommendation.evidence
        assert recommendation.unmeasured_profiles == ("academic",)


def test_no_measurement_means_no_recommendation() -> None:
    for language in ("fr", "en", None, "", "  "):
        recommendation = recommend_profile(language)

        assert recommendation.measured is False
        assert recommendation.profile is None
        assert "sin medición" in recommendation.evidence
        assert recommendation.unmeasured_profiles == ("default", "academic")


def test_lowest_measured_wer_wins() -> None:
    rows = (
        ProfileMeasurement("en", "default", 5.0, 2.0, "a", False),
        ProfileMeasurement("en", "academic", 3.0, 1.0, "b", False),
        ProfileMeasurement("es", "default", 1.0, 1.0, "c", True),
    )

    best = recommend_profile("en", rows)

    assert (best.profile, best.evidence, best.synthetic) == ("academic", "b", False)
    assert best.unmeasured_profiles == ()


def test_shipped_measurements_only_name_known_profiles() -> None:
    assert MEASUREMENTS
    assert {m.profile for m in MEASUREMENTS} <= {e.profile.name for e in PROFILES}
