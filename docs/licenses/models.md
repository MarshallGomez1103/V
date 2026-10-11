# Licenses: V's code, third-party code and model weights

Last reviewed: 2026-10-11.

V keeps three kinds of licensing apart. Do not assume that one covers the
others.

## 1. V's own source code

V's source code is released under the **MIT license**. The legal text is in
[`LICENSE`](../../LICENSE). It applies to the code in this repository only. It
does not relicense third-party code or any model weights.

## 2. Third-party code dependencies

Python and Node packages that V depends on are listed, with the license
reported by each package, in [`NOTICE`](../../NOTICE). V does not vendor them.
Adapted third-party code, if any is ever added, is also recorded in `NOTICE`.

## 3. Model weights

Model weights are **not** part of this repository, are not shipped in any V
package, and are **not redistributed by V**. V downloads a model only when the
user explicitly asks for it (install action), from the upstream source listed
below, pinned to a fixed revision or URL and checked against a SHA-256 digest.
The user receives the weights directly from the upstream publisher and is
bound by that publisher's license.

Verification status. "Verified" means the license was read in the repository
itself or on the official upstream page on the date shown. "Not verified"
means it could not be confirmed from a primary source and must not be relied
on.

### 3.1 Speech recognition: faster-whisper (CTranslate2)

Catalog: `src/voz/infrastructure/asr/catalog.py`. Files are fetched from
`https://huggingface.co/<source>/resolve/<revision>/<file>`.

| Model id | Source (Hugging Face repo) | Weights license | Redistributed by V | Verification |
| --- | --- | --- | --- | --- |
| `turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |
| `large-v3` | `Systran/faster-whisper-large-v3` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |
| `medium` | `Systran/faster-whisper-medium` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |
| `small` | `Systran/faster-whisper-small` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |
| `base` | `Systran/faster-whisper-base` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |
| `tiny` | `Systran/faster-whisper-tiny` | MIT | No | Verified: model card shows "License: mit" (2026-10-11) |

Model cards consulted (2026-10-11):

- https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo
- https://huggingface.co/Systran/faster-whisper-large-v3
- https://huggingface.co/Systran/faster-whisper-medium
- https://huggingface.co/Systran/faster-whisper-small
- https://huggingface.co/Systran/faster-whisper-base
- https://huggingface.co/Systran/faster-whisper-tiny

The catalog also records `license="MIT"` for each of these entries. The
license of the upstream OpenAI Whisper weights from which these conversions
derive was not separately checked here: Not verified.

### 3.2 Speech recognition: whisper.cpp (GGML)

Catalog: `src/voz/infrastructure/asr/whisper_cpp_catalog.py`. All entries come
from one repository, pinned to revision
`5359861c739e955e79d9a303bcbc70fb988958b1`, one `ggml-<model>.bin` file each.

| Model id | Source | Weights license | Redistributed by V | Verification |
| --- | --- | --- | --- | --- |
| `large-v3-turbo-q5_0`, `large-v3-turbo-q8_0`, `large-v3-turbo`, `small-q5_1`, `small`, `base` | `ggerganov/whisper.cpp` (Hugging Face) | MIT | No | Verified: model card shows "License: mit" (2026-10-11); the catalog also records `license="MIT"` |

Model card consulted (2026-10-11): https://huggingface.co/ggerganov/whisper.cpp.
The card gives one license for the whole repository. Per-file licenses of the
individual quantized conversions were not checked separately.

### 3.3 Speaker diarization (sherpa-onnx)

Catalog: `src/voz/infrastructure/diarization/models.py`. Installed only by
`DiarizationModelStore.install`; downloaded from the sherpa-onnx GitHub
releases, with size and SHA-256 pinned in the code. The segmentation archive
carries its upstream `LICENSE`, which V stores next to the model as
`LICENSE-pyannote-segmentation-3-0.txt`.

| Artifact | Source | Weights license | Redistributed by V | Verification |
| --- | --- | --- | --- | --- |
| `sherpa-onnx-pyannote-segmentation-3-0` (ONNX export of pyannote/segmentation-3.0) | https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2 | MIT | No | Verified: the original card https://huggingface.co/pyannote/segmentation-3.0 shows "License: mit" (2026-10-11); the card is gated (the publisher asks for contact information before file access). The sherpa-onnx release page itself states no license. Also recorded in ADR-0007 and in the code |
| `wespeaker_en_voxceleb_resnet34_LM.onnx` (WeSpeaker ResNet34-LM speaker embeddings) | https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx | Not verified | No | Partly verified, see below |

WeSpeaker embedding model. The WeSpeaker **code** repository
(https://github.com/wenet-e2e/wespeaker) shows Apache-2.0 (2026-10-11), and
ADR-0007 and the code record "Apache-2.0 (WeSpeaker)". However, the WeSpeaker
pretrained-models page
(https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md,
2026-10-11) states that pretrained models follow the license of their training
dataset and that models trained on VoxCeleb follow Creative Commons
Attribution 4.0 International. That page does not name this exact ONNX file,
and the sherpa-onnx release page does not state a license for it. The weights
license is therefore **Not verified**: it may be Apache-2.0, CC BY 4.0, or
both may apply. Until the owner resolves this, do not describe these weights
as Apache-2.0 in user-facing material, and treat attribution to WeSpeaker and
VoxCeleb as required.

## 4. Future TTS models

Text-to-speech is planned (Program V, phase V-2 onward) and no TTS model is
installable today. When TTS providers are added:

- Each TTS model will **declare its weights license in the catalog**, next to
  its source and pinned revision, the same way ASR catalog entries carry a
  `license` field today. This document will gain a row per model at that time.
- The license of a model's weights is independent of the license of the code
  that runs it.
- Some weights carry **restrictions, including commercial ones**. Example from
  the project's own research (`.ai/audit-av/07-KITTENTTS-RESEARCH.md`, sources
  consulted 2026-10-10): the KittenTTS code is Apache-2.0, but the **KittenTTS 2
  weights are released under the Stellon Labs Community License**, quoted from
  the model card. The model card says research, non-commercial and limited
  commercial use are free, that the commercial grant ends above a revenue or
  funding cap, and that distributing the weights, a derivative, or a product
  built on them carries attribution requirements. The full text of that license
  was **not read**, so any further term (registration, attribution wording,
  revocation, acceptable use) is Not verified.
- Consequently V will not bundle TTS weights in an installer or release, and
  will not present a model as freely usable commercially without a verified
  license.
