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
| `wespeaker_en_voxceleb_resnet34_LM.onnx` (WeSpeaker ResNet34-LM speaker embeddings) | https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx | CC BY 4.0 (WeSpeaker VoxCeleb-trained weights) | No | Verified from WeSpeaker's own statements (2026-10-11), see below |

WeSpeaker embedding model (re-checked 2026-10-11, slice V1-10a). Sources
read on 2026-10-11:

- https://github.com/wenet-e2e/wespeaker: the **code** is Apache-2.0. The
  README says nothing about pretrained-model licenses and asks users to cite
  the two WeSpeaker papers listed below.
- https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md:
  "The pretrained model in WeNet follows the license of it's corresponding
  dataset. For example, the pretrained model on VoxCeleb follows Creative
  Commons Attribution 4.0 International License." The VoxCeleb row lists
  "ResNet34 / ResNet34_LM" with `.pt` and `.onnx` downloads.
- https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM: model card
  metadata declares "License: cc-by-4.0".
- https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models
  (where V downloads the file): "Each model has its own license. Please see the
  corresponding repository for the specific license of a given model." The
  corresponding repository is WeSpeaker, so the WeSpeaker statement applies.
- https://www.robots.ox.ac.uk/~vgg/data/voxceleb/ asks users of the dataset
  to cite the three VoxCeleb papers below. Its subpages
  https://www.robots.ox.ac.uk/~vgg/data/voxceleb/vox1.html and
  https://www.robots.ox.ac.uk/~vgg/data/voxceleb/vox2.html state that the
  VoxCeleb1/VoxCeleb2 **metadata** is licensed CC BY-SA 4.0; neither page
  states a license for models trained on the data.

Conclusion. The weights are recorded as **CC BY 4.0**, the license the model
publisher (WeSpeaker) states for its VoxCeleb-trained models; they are **not**
Apache-2.0. The catalog string in `models.py` is
`"CC-BY-4.0 (WeSpeaker, VoxCeleb-trained)"`. Two points remain unverified and
are stated so as not to overclaim: (a) the sherpa-onnx ONNX file is assumed to
be the WeSpeaker ResNet34-LM export (same name; no byte comparison with the
WeSpeaker/Hugging Face `.onnx` was made); (b) whether the dataset's CC BY-SA
4.0 metadata license has any bearing on trained weights is a legal question not
settled by any source above.

Required attribution (CC BY 4.0). V does not redistribute these weights, but
any material that presents or ships them must credit:

- WeSpeaker, ResNet34-LM speaker-embedding model trained on VoxCeleb, CC BY 4.0
  (https://github.com/wenet-e2e/wespeaker), with no changes made by V. Papers
  requested by WeSpeaker: Hongji Wang, Chengdong Liang, et al., "Wespeaker: A
  research and production oriented speaker embedding learning toolkit",
  ICASSP 2023; Shuai Wang, Zhengyang Chen, et al., "Advancing speaker embedding
  learning: Wespeaker toolkit for research and production", Speech
  Communication 162, 2024.
- VoxCeleb (Visual Geometry Group, University of Oxford,
  https://www.robots.ox.ac.uk/~vgg/data/voxceleb/). Papers requested: A.
  Nagrani, J. S. Chung, W. Xie, A. Zisserman, "VoxCeleb: Large-scale speaker
  verification in the wild", Computer Speech and Language, 2019; J. S. Chung,
  A. Nagrani, A. Zisserman, "VoxCeleb2: Deep Speaker Recognition",
  INTERSPEECH 2018; A. Nagrani, J. S. Chung, A. Zisserman, "VoxCeleb: a
  large-scale speaker identification dataset", INTERSPEECH 2017.

### 3.4 Speech synthesis (sherpa-onnx TTS)

Catalog: `src/voz/infrastructure/tts/catalog.py`. Installed only by
`TtsModelStore.install` (Model Manager install action); each model is one
`.tar.bz2` downloaded from the `tts-models` release of `k2-fsa/sherpa-onnx`
(`https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/<archive>`),
with size and SHA-256 pinned in the code and checked before extraction. The
license strings below are the exact `license` values of the catalog, verified
on 2026-10-12 (slice V4-01, `.ai/v-plan/findings/V4-01.md`).

| Model id | Archive | Weights license | Redistributed by V | Verification |
| --- | --- | --- | --- | --- |
| `piper-en_US-lessac-medium` | `vits-piper-en_US-lessac-medium.tar.bz2` | MIT (rhasspy/piper-voices code and weights repository); voice trained on lessac (Blizzard 2013; research-only dataset license); espeak-ng-data GPL-3.0 (phoneme data included in the archive) | No | Verified: repository license MIT; the archive's `MODEL_CARD` points to the Lessac/Blizzard 2013 research license |
| `piper-es_ES-davefx-medium` | `vits-piper-es_ES-davefx-medium.tar.bz2` | MIT (rhasspy/piper-voices code and weights repository); davefx dataset CC0; fine-tuned from lessac (voice trained on lessac (Blizzard 2013; research-only dataset license)); espeak-ng-data GPL-3.0 (phoneme data included in the archive) | No | Verified: `MODEL_CARD` states the CC0 dataset; the lessac fine-tune origin is recorded in the same card |
| `piper-es_MX-ald-medium` | `vits-piper-es_MX-ald-medium.tar.bz2` | MIT (rhasspy/piper-voices code and weights repository); ald dataset Unlicense; fine-tuned from davefx, itself fine-tuned from lessac (voice trained on lessac (Blizzard 2013; research-only dataset license)); espeak-ng-data GPL-3.0 (phoneme data included in the archive) | No | Verified: `MODEL_CARD` states the Unlicense dataset and the davefx origin |
| `kitten-nano-en-v0_8-int8` | `kitten-nano-en-v0_8-int8.tar.bz2` | Apache-2.0; espeak-ng-data GPL-3.0 (phoneme data included in the archive) | No | Verified: `LICENSE` in the archive; Hugging Face card `KittenML/kitten-tts-nano-0.8-int8` declares `apache-2.0` |
| `kokoro-int8-multi-lang-v1_0` | `kokoro-int8-multi-lang-v1_0.tar.bz2` | Apache-2.0; espeak-ng-data GPL-3.0 (phoneme data included in the archive) | No | Verified: `LICENSE` in the archive; Hugging Face card `hexgrad/Kokoro-82M` declares `apache-2.0` |

Points to keep in mind:

- **Piper voices and the Lessac dataset.** The `piper-voices` repository is MIT,
  but the English voice is trained on the Lessac/Blizzard 2013 dataset, whose
  license is for research use. The two Spanish voices are fine-tunes that start
  from that voice (davefx from lessac, ald from davefx), so the dataset chain is
  not clean even though their own datasets are CC0 and Unlicense. V does not
  present these voices as freely usable commercially. The owner decides whether
  to keep them in the default catalog; Kitten and Kokoro (Apache-2.0) are the
  alternatives with a clean chain.
- **espeak-ng-data (GPL-3.0).** Every archive contains the phoneme data of
  espeak-ng, which is GPL-3.0. V does not redistribute it: it is downloaded by
  the user from upstream and stored next to the model. It matters to anyone
  who would repackage the archives.
- **No quality claim.** Voice quality was not evaluated by ear; only that the
  audio is not silent.
- The release is mutable upstream, so the code pins SHA-256 and rejects any
  other file.

## 4. Other speech synthesis models

Only the models in section 3.4 are installable. When more TTS models are added:

- Each TTS model will **declare its weights license in the catalog**, next to
  its pinned archive, the same way ASR catalog entries carry a `license` field.
  This document gains a row per model at that time.
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
