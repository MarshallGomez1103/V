"""Built-in quality profiles and the measured per-language recommendation.

Profiles are plain immutable data. Changing a parameter means a new ``version``;
jobs keep the full profile they were created with (see ``JobSelection``).
"""

from __future__ import annotations

from dataclasses import dataclass

from voz.domain.entities.quality_profile import QualityProfile, VadSettings

DEFAULT_PROFILE_NAME = "default"

# Faster Whisper's own defaults, so a job on this profile behaves exactly like
# one created before profiles existed (and like `voz bench`).
DEFAULT_PROFILE = QualityProfile(
    name=DEFAULT_PROFILE_NAME,
    version=1,
    beam_size=5,
    temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    condition_on_previous_text=True,
    no_speech_threshold=0.6,
    vad=None,
)

# Long lectures: no conditioning on previous text (stops a hallucinated or looped
# sentence from feeding the next window), fewer random-temperature fallbacks, and
# VAD to skip silence/noise. Chosen from the library's documented behaviour, NOT
# from a VOZ measurement: see docs/quality-profiles.md.
ACADEMIC_PROFILE = QualityProfile(
    name="academic",
    version=1,
    beam_size=5,
    temperature=(0.0, 0.2, 0.4),
    condition_on_previous_text=False,
    no_speech_threshold=0.6,
    vad=VadSettings(
        threshold=0.5,
        min_speech_duration_ms=250,
        min_silence_duration_ms=1000,
        speech_pad_ms=400,
    ),
)


@dataclass(frozen=True, slots=True)
class ProfileEntry:
    profile: QualityProfile
    label: str
    description: str


PROFILES: tuple[ProfileEntry, ...] = (
    ProfileEntry(
        DEFAULT_PROFILE,
        "Estándar",
        "Valores por defecto del motor. Es lo que se usaba antes de existir perfiles.",
    ),
    ProfileEntry(
        ACADEMIC_PROFILE,
        "Académico",
        "Clases y charlas largas: no arrastra el texto previo, menos reintentos "
        "aleatorios y filtra silencios con VAD. Sin medición propia todavía.",
    ),
)


def get_profile(name: str) -> QualityProfile | None:
    """Built-in profile by name, or ``None`` when unknown."""
    return next((e.profile for e in PROFILES if e.profile.name == name), None)


@dataclass(frozen=True, slots=True)
class ProfileMeasurement:
    """One measured WER for a (language, profile) pair, with its provenance."""

    language: str
    profile: str
    wer_percent: float
    cer_percent: float
    evidence: str
    synthetic: bool


# Only numbers that exist in docs/benchmarks.md ("Resultados medidos", 2026-09-30,
# clips cortos, faster-whisper turbo CUDA float16, decodificación por defecto =
# perfil `default`). The audio was synthetic (espeak-ng), so WER is optimistic.
# Add rows only after running `voz bench`; never estimate.
MEASUREMENTS: tuple[ProfileMeasurement, ...] = (
    ProfileMeasurement(
        language="es",
        profile=DEFAULT_PROFILE_NAME,
        wer_percent=1.66,
        cer_percent=0.81,
        evidence=(
            "docs/benchmarks.md (2026-09-30): faster-whisper turbo, CUDA float16, "
            "6 clips de ~36 s en español, WER 1,66 %. Audio sintético: optimista."
        ),
        synthetic=True,
    ),
)


@dataclass(frozen=True, slots=True)
class ProfileRecommendation:
    language: str | None
    profile: str | None
    """Best *measured* profile, or ``None`` when nothing was measured."""
    measured: bool
    evidence: str
    synthetic: bool
    unmeasured_profiles: tuple[str, ...]


def _primary_language(language: str | None) -> str | None:
    if language is None or not language.strip():
        return None
    return language.strip().split("-")[0].split("_")[0].lower()


def recommend_profile(
    language: str | None,
    measurements: tuple[ProfileMeasurement, ...] = MEASUREMENTS,
) -> ProfileRecommendation:
    """Pick the lowest measured WER for ``language``; never extrapolate.

    Without a measurement for the language (or without a language at all) the
    answer is explicitly "sin medición" and no profile is recommended.
    """
    primary = _primary_language(language)
    rows = [m for m in measurements if m.language == primary]
    if not rows:
        reason = (
            "sin medición: elige un idioma"
            if primary is None
            else f"sin medición para el idioma «{primary}»"
        )
        return ProfileRecommendation(
            primary,
            None,
            False,
            reason,
            False,
            tuple(e.profile.name for e in PROFILES),
        )
    best = min(rows, key=lambda m: m.wer_percent)
    measured = {m.profile for m in rows}
    return ProfileRecommendation(
        primary,
        best.profile,
        True,
        best.evidence,
        best.synthetic,
        tuple(e.profile.name for e in PROFILES if e.profile.name not in measured),
    )


__all__ = [
    "ACADEMIC_PROFILE",
    "DEFAULT_PROFILE",
    "DEFAULT_PROFILE_NAME",
    "MEASUREMENTS",
    "PROFILES",
    "ProfileEntry",
    "ProfileMeasurement",
    "ProfileRecommendation",
    "get_profile",
    "recommend_profile",
]
