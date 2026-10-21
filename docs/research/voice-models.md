# Local speech models: selection and compatibility

Source review: **2026-10-16**, extended **2026-10-20**. Scope: Spanish and English
recognition, multilingual synthesis, local inference and external models that
could extend V. The comparison is based on sources;
the separate CPU smoke checks below exercise loading and execution, not a
quality benchmark or listening test. There is no universal best model: recognition
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
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Approximately 600M; 25 languages, including Spanish/English | Alternative multilingual recognition architecture | CC-BY-4.0; the sherpa ONNX export can be imported with V's experimental CPU `nemo_transducer` family. Automatic language only; V does not provide aligned word timestamps |
| [Qwen3-ASR](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) | Named 0.6B/1.7B variants; 30 languages plus 22 Chinese dialects | Candidate for multilingual recognition, including difficult audio; upstream offline/streaming toolkit | Apache-2.0; official Safetensors and sherpa ONNX exports have different layouts. V needs a Qwen ASR family before either can be used |

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

## Additional providers (2026-10-19)

These candidates extend the comparison across publishers. They are not newly
installed engines or verified inference in V.

| Publisher / model | Language and intended use | Runtime and weights license | Current V compatibility |
| --- | --- | --- | --- |
| IBM: [Granite 4.0 1B Speech](https://huggingface.co/ibm-granite/granite-4.0-1b-speech) | Spanish plus English, French, German, Portuguese and Japanese; recognition and translation | Transformers / PyTorch, or a separate MLX runtime; weights Apache-2.0 | New engine required. The `1b` label describes the language-model base, not the entire speech checkpoint or a RAM budget. |
| IBM: [Granite Speech 5.0 470M TurboCTC](https://huggingface.co/ibm-granite/granite-speech-5.0-470m-turboctc) | English only; non-autoregressive recognition | Transformers >=5.16.0 or a separate compatible C++ runtime; weights Apache-2.0 | New engine required. Its English GPU benchmark does not establish Spanish performance or laptop CPU latency. |
| Mistral: [Voxtral Mini 4B Realtime 2602](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602) | 13 languages including Spanish; streaming recognition | Dedicated streaming runtime such as vLLM; weights Apache-2.0 | New engine required. The streaming protocol and audio tokenizer differ from Whisper. |
| Kyutai: [STT 1B en/fr](https://huggingface.co/kyutai/stt-1b-en_fr) | English and French; streaming recognition | Moshi / Transformers and Mimi codec; weights CC-BY-4.0 | New engine required; this checkpoint does not add Spanish recognition. |
| Kyutai: [Pocket TTS](https://huggingface.co/kyutai/pocket-tts) | Approximately 100M; CPU synthesis, current upstream includes Spanish | Native code MIT, weights CC-BY-4.0 with gated access; native Python path requires PyTorch >=2.5 | Sherpa exports exist, but V has no Pocket family or reference-audio workflow. The January English export does not establish compatibility with current multilingual weights. |
| Supertone: [Supertonic 2](https://huggingface.co/Supertone/supertonic-2) / [Supertonic 3](https://huggingface.co/Supertone/supertonic-3) | 66M / approximately 99M; 5 / 31 languages including Spanish; CPU synthesis | Sample code MIT; weights OpenRAIL-M, with use and redistribution conditions | [Sherpa supports the family](https://k2-fsa.github.io/sherpa/onnx/tts/supertonic.html), but V does not. Requires family configuration, voices/language handling and worker/import support. |

Qwen3-ASR and Qwen3-TTS remain relevant Spanish candidates from Alibaba's Qwen
team. Their [ASR toolkit](https://github.com/QwenLM/Qwen3-ASR) and
[TTS toolkit](https://github.com/QwenLM/Qwen3-TTS) use separate model classes;
installing generic Transformers support would not make either a Whisper model.
For ASR, [sherpa also publishes a Qwen3-ASR 0.6B int8 export](https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html)
with convolution frontend, encoder, decoder and tokenizer assets. Its documented
CPU path does not inherently require adding PyTorch to V. Likewise,
[sherpa exports Canary models](https://k2-fsa.github.io/sherpa/onnx/nemo/canary.html).
The installed loader exposing these constructors does not make their layouts
importable: V still needs matching family validation, worker configuration and
result mapping. Qwen3-TTS is a separate integration.
The official CUDA examples are not evidence of their speed or memory use on V's
hardware. Qwen, IBM and Mistral weights above use Apache-2.0, but their inference
frameworks and companion assets have their own notices.

Model license, loader license, voice/dataset provenance and phoneme-data terms
must be checked separately before redistribution. CC-BY requires attribution;
OpenRAIL-M also carries use restrictions and downstream conditions. A public
model card or downloadable conversion is not a blanket commercial clearance.

## Execution devices in V

Device selection belongs to each engine. More models do not imply that every
engine runs on both CPU and GPU, or that several engines run concurrently.

| Engine | Current execution policy |
| --- | --- |
| Faster Whisper / CTranslate2 | GPU-preferred profiles use a supported CUDA precision; if CUDA is unavailable or its precisions are unsupported, selection falls back to CPU with an explicit reason. CPU-only profiles remain on CPU. Memory admission is a separate check, not a promise to recover automatically from every GPU failure. |
| whisper.cpp | The current composition root forces CPU (`--no-gpu`). A separately built CUDA/Vulkan binary alone does not enable that backend inside V. See [whisper.cpp](../whisper-cpp.md). |
| Sherpa ASR: Whisper ONNX / NeMo transducer | CPU only. Whisper real-weight validation remains pending; Parakeet TDT v3 int8 completed one short synthetic CPU check. NeMo requires Automatic language and produces no aligned words. |
| Sherpa synthesis | CPU only in the current worker, including the current Kitten, Kokoro, VITS/Piper and Matcha families. |

The model selector labels CPU/GPU as engine compatibility and displays the
profile's automatic GPU preference separately from its initial device choice.
That initial choice is a preflight snapshot: a later CPU fallback inside the
engine does not turn it into proof that the job ran on GPU. Synthesis options
publish per-model capabilities; older responses without that field do not
establish a device. Remote providers process on their server and do not imply
use of this computer's GPU.

The shared compute slot serializes heavy jobs. ASR and diarization release
resources between stages; adding a family must preserve cancellation, bounded
workers, explicit progress and that ownership policy. A GPU capability in an
upstream library does not override V's configured provider.

## Three starting points

1. **CPU and quick setup:** start with Whisper small and Piper Spanish Mexico;
   Kitten nano is an English alternative. These families are already integrated.
   Adjust the model after checking representative recordings on the target CPU.
2. **Spanish quality:** compare large-v3 against turbo on the same recordings,
   and listen to Kokoro against Piper on the same text. Kokoro is an available
   candidate for voice preference, not a locally established quality winner.
3. **GPU and future extensions:** use Faster Whisper turbo/large-v3 now, subject
   to runtime/device availability. Compare Parakeet on CPU with representative
   recordings; Qwen3-ASR remains a family-integration candidate. Qwen3-TTS
   and Chatterbox are synthesis candidates after a compatible engine is added.

No comparative latency or peak-memory benchmark accompanies this review.
Parameters, archive sizes and quantization labels cannot predict end-to-end memory use;
runtime, audio length, batching and device also matter. Publisher GPU throughput
and first-packet latency figures are not promises for V's sequential job pipeline.

## External links and model import

The catalog is a convenience, not the limit of compatible models. External
Hugging Face repositories, file URLs and folders can supply weights for an
installed engine. V imports supported weights/configuration, fixes provenance
and SHA-256, and validates loading before publishing the installation. It does
not execute downloaded Python scripts or accept arbitrary Hugging Face model
architectures. See [model import](../api/models.md) and
[experimental ONNX ASR](../sherpa-onnx-asr.md).

Current families are CTranslate2 Whisper, Whisper GGML, sherpa TTS
kitten/kokoro/vits/matcha, and experimental sherpa ASR Whisper ONNX / NeMo
transducer. Whisper ONNX has not been validated with real weights. A generic ONNX, GGUF or Safetensors
extension alone does not prove compatibility; matching tokenizer, configuration
and companion files are required. Unsupported architectures need an engine
integration before their weights can be imported and used.

Parakeet uses the experimental CPU NeMo transducer family.
[Sherpa publishes its ONNX export](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html)
with encoder, decoder, joiner and tokens. V validates all four roles and loads
the recognizer in an owned child. Use Automatic language; no language override
or aligned word output is supported. Other candidates still require their own
family integration or a separate runtime.

## Reviewed export artifacts

The table separates compatible exports from families that still need
integration. All sizes are compressed archive bytes, not RAM/VRAM requirements.
A compatible family does not establish quality for every export.

| Official release asset | Bytes | Language / integration boundary |
| --- | --- | --- |
| `vits-piper-es_MX-claude-high-int8.tar.bz2` | 21,216,685 | Spanish Mexico; VITS family, short CPU synthesis checked. The [voice card](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_MX/claude/high/MODEL_CARD) declares Apache-2.0 dataset terms; retain repository and bundled phoneme-data notices. |
| `kitten-micro-en-v0_8.tar.bz2` | 44,423,643 | English, 40M; existing Kitten family; Apache-2.0 weights plus bundled phoneme-data terms. |
| `kitten-mini-en-v0_8.tar.bz2` | 67,547,594 | English, 80M; Kitten family, short CPU synthesis checked; Apache-2.0 weights plus bundled phoneme-data terms. |
| `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2` | 487,170,055 | Spanish and 24 other languages; experimental CPU NeMo transducer import, one short synthetic Spanish check; Automatic language, nominal windows only. |
| `sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2` | 128,774,318 | Spanish and 30 other languages; new Supertonic family with multiple graphs and voice/language assets. |
| `sherpa-onnx-pocket-tts-int8-2026-01-26.tar.bz2` | 98,336,520 | English export; new Pocket family and reference-audio generation semantics. |

Sources: the exporter's [TTS release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models),
[ASR release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models),
[Kitten export documentation](https://k2-fsa.github.io/sherpa/onnx/tts/kitten.html)
and [Pocket export documentation](https://k2-fsa.github.io/sherpa/onnx/tts/pocket.html).
Release tags are mutable: an installation entry must pin the exact asset's size
and SHA-256 and validate its contents and loading before it becomes available.
The Parakeet, Piper Claude and Kitten mini archives were downloaded and checked
against fixed size and SHA-256 before their short CPU checks. The other candidate
exports in this table were not downloaded as part of this comparison.

Short CPU checks on 2026-10-20 exercised Piper Claude in Spanish, Kitten mini
in English and Kokoro in Spanish, English, Portuguese and French. Kokoro voice
IDs and languages were read from the model metadata. In Speak, select the model,
then a declared language and a matching voice; a single-language model does not
show an unnecessary language selector. These checks produced audio without
subjective listening evaluation. Exact artifacts, process limits and measurements
are listed in [the model/device checks](../benchmarks.md#additional-model-and-device-smokes-2026-10-20).

For Spanish on the current stack, comparing existing Whisper small/turbo/large-v3
and Piper/Kokoro remains the shortest path. Extra compatible voices can broaden
choice without a new engine. For a different recognition architecture, Parakeet
is an experimental CPU alternative; Supertonic 3 remains a Spanish TTS
integration candidate. Qwen ASR needs its own V family even when using the
existing sherpa runtime; Qwen TTS and Granite need compatible engine integration.
The short CPU checks establish execution for those exact artifacts. They
do not establish a quality ranking, listening preference, representative
conversation accuracy or GPU support for NeMo or sherpa synthesis.

## Source snapshot

The original source snapshot below was reviewed on 2026-10-16 and is retained
for provenance. Additional model/release metadata was checked on 2026-10-19;
the Qwen ASR and Canary ONNX integration paths were rechecked on 2026-10-20.
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

Additional observed revisions (2026-10-19):

| Repository | Observed revision | Repository modification date |
| --- | --- | --- |
| `ibm-granite/granite-4.0-1b-speech` | `bd87ab862416353633ea431fe49b1614003623c5` | 2026-04-02 |
| `ibm-granite/granite-speech-5.0-470m-turboctc` | `947f59af40db9791170a0628cf0f3f4812d720f1` | 2026-10-02 |
| `mistralai/Voxtral-Mini-4B-Realtime-2602` | `2769294da9567371363522aac9bbcfdd19447add` | 2026-03-11 |
| `kyutai/pocket-tts` | `a0172fa05a0725a745539c88e4b58f1ee19cb9a7` | 2026-10-19 |
| `Supertone/supertonic-2` | `75e6727618a02f323c720cba9478152d4bc16ca4` | 2026-01-06 |
| `Supertone/supertonic-3` | `3cadd1ee6394adea1bd021217a0e650ede09a323` | 2026-05-18 |

These are repository commits, not weight-file SHA-256 digests. The observed
metadata may change; candidate file hashes and loading must be checked when an
installation is actually prepared.
