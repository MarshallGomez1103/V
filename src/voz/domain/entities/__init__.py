"""Framework-independent domain entities."""

from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import (
    SynthesisOutputFormat,
    SynthesisRequest,
)
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    InvalidJobTransition,
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.voice import Voice
from voz.domain.entities.word import Word

__all__ = [
    "ComputePrecision",
    "DevicePreference",
    "InvalidJobTransition",
    "MediaAsset",
    "ModelCapability",
    "ModelDescriptor",
    "ProcessingProfile",
    "ProcessingProfileName",
    "Project",
    "Segment",
    "Speaker",
    "SpeakerTurn",
    "SynthesisJob",
    "SynthesisJobState",
    "SynthesisOutputFormat",
    "SynthesisRequest",
    "SynthesizedAudio",
    "Transcript",
    "TranscriptionJob",
    "TranscriptionJobState",
    "Voice",
    "Word",
]
