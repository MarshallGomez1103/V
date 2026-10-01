"""Read and replace a project's glossary of hot terms (S13.01).

The glossary only biases the engine (Faster Whisper ``hotwords``, a cloud
provider's ``keyterms``). It never rewrites the literal transcript.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from voz.application.ports.project_glossary import ProjectGlossaryRepository
from voz.application.ports.repositories import ProjectRepository

MAX_GLOSSARY_TERMS = 50
MAX_TERM_LENGTH = 50
"""Both limits fit inside the strictest provider (100 keyterms of 50 characters)."""


class InvalidGlossary(ValueError):
    """The submitted terms cannot be stored; the message is user-safe."""


class ProjectNotFound(LookupError):
    """The project does not exist."""


def normalize_glossary(terms: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Trim, drop blanks, dedupe (order kept) and enforce the limits."""
    clean: dict[str, None] = {}
    for term in terms:
        stripped = term.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_TERM_LENGTH:
            raise InvalidGlossary(
                f"Each term must have at most {MAX_TERM_LENGTH} characters."
            )
        if not stripped.isprintable():
            raise InvalidGlossary("Terms must not contain control characters.")
        clean.setdefault(stripped)
    if len(clean) > MAX_GLOSSARY_TERMS:
        raise InvalidGlossary(f"At most {MAX_GLOSSARY_TERMS} terms are allowed.")
    return tuple(clean)


@dataclass(frozen=True, slots=True)
class ProjectGlossary:
    projects: ProjectRepository
    glossaries: ProjectGlossaryRepository
    providers: tuple[str, ...] = ("faster-whisper",)
    """Provider ids that use the glossary (wired by the composition root); every
    other engine ignores it and the UI says so."""

    def get(self, project_id: UUID) -> tuple[str, ...]:
        if self.projects.get(project_id) is None:
            raise ProjectNotFound
        return self.glossaries.get(project_id)

    def replace(self, project_id: UUID, terms: list[str]) -> tuple[str, ...]:
        if self.projects.get(project_id) is None:
            raise ProjectNotFound
        clean = normalize_glossary(terms)
        self.glossaries.put(project_id, clean)
        return clean


__all__ = [
    "MAX_GLOSSARY_TERMS",
    "MAX_TERM_LENGTH",
    "InvalidGlossary",
    "ProjectGlossary",
    "ProjectNotFound",
    "normalize_glossary",
]
