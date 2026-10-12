"""A voice offered by a speech synthesis model (ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from voz.domain.entities._validation import require_non_blank


@dataclass(frozen=True, slots=True)
class Voice:
    """A selectable voice: stable id, visible name and spoken languages.

    ``id`` is whatever the engine uses to pick the voice inside a model (for
    sherpa-onnx, the speaker id as text); it is stable for one model revision.
    ``languages`` may be empty when the model does not declare them.
    """

    id: str
    name: str
    languages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, field="voice id"))
        object.__setattr__(
            self, "name", require_non_blank(self.name, field="voice name")
        )
        languages = cast(object, self.languages)
        if not isinstance(languages, tuple):
            raise TypeError("voice languages must be a tuple")
        normalized = tuple(
            require_non_blank(language, field="voice language")
            for language in cast(tuple[object, ...], languages)
        )
        if len(set(normalized)) != len(normalized):
            raise ValueError("voice languages must not repeat")
        object.__setattr__(self, "languages", normalized)
