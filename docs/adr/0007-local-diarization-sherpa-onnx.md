# ADR-0007: Local diarization with sherpa-onnx (no torch, no token)

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-30
- Owners: VOZ maintainers
- Scope: default diarization engine and its model installation
  (S6.04, S6.05-S6.07, S6.16)
- Related: [ADR-0005](0005-transcription-providers.md) (providers),
  [ADR-0006](0006-local-first-privacy.md) (local-first, explicit downloads)

## Context

Diarization answers "who spoke when" and feeds editable speakers. The usual
candidate, pyannote `speaker-diarization-community-1`, requires PyTorch
(hundreds of MB of dependencies) and a Hugging Face token with accepted terms.
That contradicts VOZ's goal: local, free, open source and account-free
(ADR-0006). Nor is it desirable for the default installation to drag in torch
alongside CTranslate2 on an immutable system (Bazzite).

## Decision

1. **Engine:** `sherpa-onnx` (ONNX Runtime, CPU wheels, no torch) behind the
   `DiarizationProvider` port (`src/voz/application/ports/diarization.py`). It
   is an optional extra (`pip install voz[diarization]`); it is imported lazily
   and, if missing, the error is `diarization_runtime_unavailable`.
2. **Pinned models** (no token; URL, size and SHA-256 verified before
   publishing):
   - segmentation: `sherpa-onnx-pyannote-segmentation-3-0` (ONNX export of
     pyannote/segmentation-3.0), **MIT** license;
   - embeddings: `wespeaker_en_voxceleb_resnet34_LM.onnx` (WeSpeaker ResNet34),
     **Apache-2.0** license.

     > **Correction 2026-10-11 (V1-10a):** Apache-2.0 is the license of the
     > WeSpeaker *code*, not of these weights. WeSpeaker's
     > [`docs/pretrained.md`](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md)
     > states that pretrained models follow the license of their training
     > dataset and that VoxCeleb-trained models follow Creative Commons
     > Attribution 4.0 International; the Hugging Face card
     > [`Wespeaker/wespeaker-voxceleb-resnet34-LM`](https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM)
     > declares `cc-by-4.0`. The embedding weights are therefore recorded as
     > **CC BY 4.0** (attribution to WeSpeaker and VoxCeleb required). The
     > decision above is unchanged. Details and attribution:
     > [`docs/licenses/models.md`](../licenses/models.md#33-speaker-diarization-sherpa-onnx).
   They are installed only by explicit action (`DiarizationModelStore.install`)
   in `<XDG data>/models/diarization/`, with `.part` files, resumption through
   `Range`, atomic publication and a manifest; they are never downloaded at
   import time or when diarizing.
3. **Clustering:** sherpa's `FastClustering`. Automatic by threshold (0.3);
   exact with `num_clusters=N`; min/max range = automatic and, if the result
   falls outside, a second pass with `num_clusters` clamped to the limit,
   without reloading the models (`set_config` only changes the clustering).
4. **Threshold 0.3.** Measured with synthetic Spanish dialogue: 0.5 merges
   different voices and 0.3 separates A/B/A. Over-segmentation is preferred:
   merging speakers in the UI is trivial; separating a merged voice is not.
5. **Contract:** input is mono 16 kHz s16 PCM WAV (the normalized ASR
   derivative; any other format is `diarization_invalid_audio`); output is
   `DiarizedTurn` in ordered integer ms with an opaque `cluster`. Cancellation
   is polled from the native progress callback. Host paths do not leave the
   infrastructure.

## Positive consequences

- Lightweight installation (~33 MB of models) and no accounts; works without a
  network after the explicit download.
- Runs on CPU; does not compete for VRAM with ASR (S14.07).
- The port allows replacing the engine without touching use cases.

## Costs and limits

- Quality somewhat lower than pyannote Community-1; the embedding is trained on
  VoxCeleb (English), so separation in Spanish relies on voice, not language.
- Fast clustering does not model overlapping voices beyond what the
  segmentation gives; reconciliation with ASR segments lives in application.
- Range = at most two passes (segmentation + embeddings are repeated;
  ponytail: only the clustering could be cached with an upstream change).
- The audio is loaded entirely into memory as float32 (about 230 MB per hour).

## Alternatives considered

| Alternative | Why it is not the default option |
| --- | --- |
| pyannote Community-1 with torch | Requires torch and an HF token with accepted terms |
| NVIDIA NeMo (MSDD/Sortformer) | Very heavy dependencies; GPU/CUDA-oriented |
| WhisperX | Couples ASR, alignment and diarization (which uses pyannote and a token) |

## How to change the model

Change the pinned catalog in `DiarizationModelStore` (URL, size, SHA-256 and
file names) and the paths passed to `SherpaOnnxDiarizationProvider`; a whole
different engine only needs to implement `DiarizationProvider`. The manifest
compares the pinned sources, so a different catalog forces a clean
reinstallation.

## Current evidence (2026-09-30)

| Requirement | Code or test |
| --- | --- |
| Verified, resumable and atomic download | `src/voz/infrastructure/diarization/models.py`, `tests/unit/infrastructure/diarization/test_diarization_models.py` |
| Provider, strict WAV, cancellation, typed errors | `src/voz/infrastructure/diarization/sherpa.py`, `tests/unit/infrastructure/diarization/test_sherpa_provider.py` |
| Auto / range / exact with a fake engine | same file (`test_range_reruns_clamped_without_reloading_models`) |
| Opt-in real test | `test_real_engine_finds_at_least_two_speakers` (`VOZ_DIARIZATION_E2E_MODELS` and `VOZ_DIARIZATION_E2E_AUDIO`) |

## Verification

This decision is considered respected when:

- no module outside `infrastructure/diarization` imports `sherpa_onnx`;
- no path downloads models without an explicit call to `install`;
- the `diarization` extra does not add torch to the environment;
- every new model is pinned with size and SHA-256.
