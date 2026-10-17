# Local speech models: selection and compatibility

Reviewed: **2026-10-16**. Scope: Spanish and English, local inference, and
external models that could extend V. This is a source review, not a new local
benchmark or listening test. There is no universal best model: recognition
accuracy, voice preference, latency, hardware and license are separate criteria.
Upstream quality and speed claims remain publisher-reported results; results
from different corpora, languages or hardware do not establish a common ranking.

## Speech recognition (STT)

Parameter counts below describe the published model or named variant, **not
RAM or VRAM requirements**. A CTranslate2 conversion, Whisper GGML file and
Whisper ONNX export are different artifacts, even when their names match.

| Model and primary source | Parameters / language coverage | Practical role | License and V compatibility |
| --- | --- | --- | --- |
| [Whisper small](https://github.com/openai/whisper#available-models-and-languages) | 244M; multilingual, including Spanish/English | CPU starting point; smaller models trade accuracy for speed | MIT; cataloged as [Faster Whisper CTranslate2](https://huggingface.co/Systran/faster-whisper-small) and Whisper GGML |
| [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3) | Approximately 1.55B; multilingual | Quality comparison baseline; heavier than small | V's [Systran CTranslate2 conversion](https://huggingface.co/Systran/faster-whisper-large-v3) declares MIT and is cataloged |
| [Whisper large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | 809M; multilingual | Faster transcription alternative to large-v3 | MIT; cataloged CTranslate2 and Whisper GGML variants. [Not trained for speech translation](https://github.com/openai/whisper#command-line-usage) |
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Approximately 600M; 25 languages, including Spanish/English | Candidate for efficient multilingual recognition and timestamps | CC-BY-4.0; upstream ONNX exports exist, but V does not implement this family |
| [Qwen3-ASR](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) | Named 0.6B/1.7B variants; 30 languages plus 22 Chinese dialects | Candidate for multilingual recognition, including difficult audio; upstream offline/streaming toolkit | Apache-2.0; official Safetensors require a compatible engine. Not importable with V's current engines |

The [OpenAI repository](https://github.com/openai/whisper#license) declares
Whisper code and weights MIT; the large-v3 Hugging Face card labels its snapshot
Apache-2.0. Preserve the license of the exact artifact selected rather than
assuming every conversion or distribution has identical metadata.

Other candidates serve narrower needs. [Canary 1B v2](https://huggingface.co/nvidia/canary-1b-v2)
(978M, CC-BY-4.0) adds translation across its supported languages.
[Cohere Transcribe 03-2026](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
(2B, Apache-2.0) supports 14 languages, but requires access conditions and has
neither automatic language detection nor timestamps/diarization.
[Moonshine's current streaming Spanish models](https://moonshine-voice.readthedocs.io/en/latest/models/available-models/)
(34M/123M, MIT) are CPU-oriented candidates; the older non-streaming Spanish
Base has a different Community license. None of these families is integrated in V.

## Speech synthesis (TTS)

| Model and primary source | Parameters / languages | Practical role | License and V compatibility |
| --- | --- | --- | --- |
| [Piper voices](https://huggingface.co/rhasspy/piper-voices) | Depends on voice; V catalogs Spanish Mexico/Spain and US English | Low-latency CPU speech with a fixed voice | Per-voice terms below; V uses sherpa's VITS loader, not the native Piper engine |
| [Kokoro v1.0](https://huggingface.co/hexgrad/Kokoro-82M) | 82M; 8 language groups / 54 voices, including Spanish/English | Alternative voices and multilingual synthesis | Apache-2.0; V catalogs the sherpa-compatible multilingual int8 export |
| [Kitten nano 0.8 int8](https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8) | [15M](https://github.com/KittenML/KittenTTS#available-models); V's export is English-only | Small CPU option | Apache-2.0; V catalogs the sherpa-compatible export, not arbitrary ONNX layouts |
| [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) | Named 0.6B/1.7B variants; 10 languages, including Spanish/English | Base voice cloning; separate CustomVoice and VoiceDesign variants | Apache-2.0; candidate requiring its own integration/runtime, not the current sherpa TTS loader |
| [Chatterbox Multilingual V3](https://huggingface.co/ResembleAI/chatterbox) | 500M; 23 languages, including Spanish/English | Voice cloning and expression; a dedicated [Latin American Spanish finetune](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-mx-latam) also exists | MIT; candidate requiring companion assets and a compatible engine. Chatterbox Turbo is a separate English model |
| [KittenTTS 2](https://huggingface.co/KittenML/kitten-tts-2) | [1.7B / 20 languages](https://github.com/KittenML/KittenTTS#features), including Spanish/English | Voice cloning/expression with distinct PyTorch/GGUF tooling | Stellon Labs Community License; not compatible with V's Kitten nano loader or Whisper GGML engine |

Piper licensing is per artifact. The voices repository declares MIT; the
[ald card](https://huggingface.co/rhasspy/piper-voices/raw/main/es/es_MX/ald/medium/MODEL_CARD)
lists an Unlicense dataset and derivation from davefx. The
[davefx card](https://huggingface.co/rhasspy/piper-voices/raw/main/es/es_ES/davefx/medium/MODEL_CARD)
lists CC0 data and derivation from Lessac; the
[Lessac card](https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/lessac/medium/MODEL_CARD)
links the Blizzard 2013 dataset terms. These notices must remain visible;
permissive metadata for a new dataset does not erase the documented lineage.
The current [native Piper engine](https://github.com/OHF-Voice/piper1-gpl)
is GPL-3.0; it is distinct from V's sherpa execution path. V's cataloged
phoneme-data bundles also carry their own GPL-3.0 notice. See
[model licensing](../licenses/models.md).

[KittenTTS 2's weights license](https://huggingface.co/KittenML/kitten-tts-2/raw/main/LICENSE.md)
differs from the Apache-licensed loader and nano weights. It includes commercial
registration, revenue/funding thresholds and distribution attribution terms;
it must not be described as unrestricted Apache/MIT weights.

## Three starting points

1. **CPU and quick setup:** start with Whisper small and Piper Spanish Mexico;
   Kitten nano is an English alternative. These families are already integrated.
   Adjust the model after checking representative recordings on the target CPU.
2. **Spanish quality:** compare large-v3 against turbo on the same recordings,
   and listen to Kokoro against Piper on the same text. Kokoro is an available
   candidate for voice preference, not a locally established quality winner.
3. **GPU and future extensions:** use Faster Whisper turbo/large-v3 now, subject
   to runtime/device availability. Evaluate Parakeet or Qwen3-ASR next; Qwen3-TTS
   and Chatterbox are synthesis candidates after a compatible engine is added.

No new latency or peak-memory measurements accompany this review. Parameters,
archive sizes and quantization labels cannot predict end-to-end memory use;
runtime, audio length, batching and device also matter. Publisher GPU throughput
and first-packet latency figures are not promises for V's sequential job pipeline.

## External links and model import

The catalog is a convenience, not the limit of compatible models. External
Hugging Face repositories, file URLs and folders can supply weights for an
installed engine. V imports supported weights/configuration, fixes provenance
and SHA-256, and validates loading before publishing the installation. It does
not execute downloaded Python scripts or accept arbitrary Hugging Face model
architectures. See [model import](../api/models.md) and
[experimental Whisper ONNX](../sherpa-onnx-asr.md).

Current families are CTranslate2 Whisper, Whisper GGML, sherpa TTS
kitten/kokoro/vits/matcha, and experimental sherpa ASR Whisper ONNX. Whisper ONNX
has not been validated with real weights. A generic ONNX, GGUF or Safetensors
extension alone does not prove compatibility; matching tokenizer, configuration
and companion files are required. Unsupported architectures need an engine
integration before their weights can be imported and used.

Parakeet is a practical next integration candidate because
[sherpa publishes its ONNX export](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html)
with encoder, decoder, joiner and tokens. V still needs the `nemo_transducer`
family, import validation and worker support; adding a catalog row alone cannot
make it run. Other candidates may require a separate runtime.

## Source snapshot

Upstream cards and Hugging Face model metadata were reviewed on 2026-10-16.
Observed revisions are research references, **not V installation pins**:

| Repository | Observed revision | Repository modification date |
| --- | --- | --- |
| `nvidia/parakeet-tdt-0.6b-v3` | `541d1f99c6b0c3cd0b11a95167540bb8edefd82b` | 2026-08-05 |
| `Qwen/Qwen3-ASR-1.7B` | `7278e1e70fe206f11671096ffdd38061171dd6e5` | 2026-01-30 |
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | `fd4b254389122332181a7c3db7f27e918eec64e3` | 2026-01-23 |
| `ResembleAI/chatterbox` | `5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18` | 2026-06-10 |
| `KittenML/kitten-tts-2` | `f2eee74f4467855ad58fe16f1fb7b7df473263fd` | 2026-10-07 |

Repository modification dates are not necessarily release dates. Qwen variant
names are publisher labels, not total tensor counts or memory measurements.
