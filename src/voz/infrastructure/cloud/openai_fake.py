"""Offline stand-in for the OpenAI transport: no network, nothing billable (S11.10).

Default replies are deterministic. ``script`` items (responses or
``TransportError``) are consumed first, one per call, to rehearse failures.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from voz.infrastructure.cloud.openai_transport import (
    HttpRequest,
    HttpResponse,
    TransportError,
)

_MODEL_FIELD = re.compile(rb'name="model"\r\n\r\n([^\r]+)\r\n')
_FORMAT_FIELD = re.compile(rb'name="response_format"\r\n\r\n([^\r]+)\r\n')


class FakeOpenAITransport:
    def __init__(self, script: Iterable[HttpResponse | TransportError] = ()) -> None:
        self._script = list(script)
        self.requests: list[HttpRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self._script:
            item = self._script.pop(0)
            if isinstance(item, TransportError):
                raise item
            return item
        return self._default(request)

    @staticmethod
    def _default(request: HttpRequest) -> HttpResponse:
        match = _FORMAT_FIELD.search(request.body)
        diarized = match is not None and match.group(1) == b"diarized_json"
        segments: list[dict[str, object]] = [
            {"start": 0.0, "end": 0.1, "text": "hola"},
            {"start": 0.1, "end": 0.25, "text": " mundo"},
        ]
        if diarized:
            for index, segment in enumerate(segments):
                segment["speaker"] = "AB"[index]
        return HttpResponse(
            200,
            json.dumps({"language": "spanish", "segments": segments}).encode(),
        )


__all__ = ["FakeOpenAITransport"]
