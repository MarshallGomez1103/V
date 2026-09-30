"""Export use case: load a transcript, render it and name the download (S10.14)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from voz.application.export.filenames import safe_export_filename
from voz.application.export.json_canonical import JsonExporter
from voz.application.export.markdown import MarkdownExporter
from voz.application.export.port import TranscriptExporter
from voz.application.export.srt import SrtExporter
from voz.application.export.text import TxtExporter
from voz.application.export.vtt import VttExporter
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    SegmentRepository,
    SpeakerRepository,
    TranscriptRepository,
)

EXPORT_FORMATS = ("txt", "markdown", "srt", "vtt", "json")
# ponytail: only the plain-text and Markdown renderers take these options.
_OPTION_FORMATS = frozenset({"txt", "markdown"})


class ExportError(Exception):
    """Typed failure with a stable ``code``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ExportedDocument:
    """Rendered text plus its safe download name (never a host path)."""

    format_id: str
    content: str
    filename: str
    # ASCII-only twin of ``filename`` for the legacy ``filename=`` parameter.
    ascii_filename: str


def _exporter(
    format_id: str, timestamps: bool, group_by_speaker: bool
) -> TranscriptExporter:
    if format_id not in EXPORT_FORMATS:
        raise ExportError("export_format_unknown", "The export format is unknown.")
    if (timestamps or group_by_speaker) and format_id not in _OPTION_FORMATS:
        raise ExportError(
            "export_option_unsupported",
            "This format does not support timestamps or speaker grouping.",
        )
    if format_id == "txt":
        return TxtExporter(
            include_timestamps=timestamps, group_by_speaker=group_by_speaker
        )
    if format_id == "markdown":
        return MarkdownExporter(
            include_timestamps=timestamps, group_by_speaker=group_by_speaker
        )
    if format_id == "srt":
        return SrtExporter()
    if format_id == "vtt":
        return VttExporter()
    return JsonExporter()


class ExportTranscript:
    def __init__(
        self,
        transcripts: TranscriptRepository,
        segments: SegmentRepository,
        speakers: SpeakerRepository,
        projects: ProjectRepository,
        media_assets: MediaAssetRepository,
    ) -> None:
        self._transcripts = transcripts
        self._segments = segments
        self._speakers = speakers
        self._projects = projects
        self._media_assets = media_assets

    def execute(
        self,
        transcript_id: UUID,
        format_id: str,
        *,
        timestamps: bool = False,
        group_by_speaker: bool = False,
    ) -> ExportedDocument:
        exporter = _exporter(format_id, timestamps, group_by_speaker)
        transcript = self._transcripts.get(transcript_id)
        if transcript is None:
            raise ExportError("transcript_not_found", "The transcript does not exist.")
        content = exporter.render(
            transcript,
            self._segments.list_by_transcript(transcript_id),
            self._speakers.list_by_project(transcript.project_id),
        )
        stem = self._stem(transcript.project_id, transcript.media_asset_id)
        extension = exporter.file_extension
        ascii_stem = (
            unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
        )
        return ExportedDocument(
            format_id,
            content,
            safe_export_filename(stem, extension),
            safe_export_filename(ascii_stem, extension),
        )

    def _stem(self, project_id: UUID, media_asset_id: UUID) -> str:
        project = self._projects.get(project_id)
        if project is not None:
            return project.name
        asset = self._media_assets.get(media_asset_id)
        # ponytail: display_name is already a basename; keep only its stem.
        return "" if asset is None else PurePosixPath(asset.display_name).stem


__all__ = ["EXPORT_FORMATS", "ExportError", "ExportTranscript", "ExportedDocument"]
