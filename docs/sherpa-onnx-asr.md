# Experimental ONNX speech recognition

The `sherpa-onnx-asr` engine runs the offline Whisper and NeMo transducer
families through the installed sherpa-onnx runtime. Other ASR families exposed
by that library are not registered in V. No model is downloaded automatically
and no additional runtime is installed when selecting this engine.

In Models, choose **Add a custom model**. Use automatic link detection, or open
**Manual configuration**, select sherpa-onnx ASR and the matching family:

| Family | Required file roles | Language selection |
| --- | --- | --- |
| `whisper` | encoder, decoder and tokens | Automatic or a language supported by the export |
| `nemo_transducer` | encoder, decoder, joiner and tokens | Automatic only; explicit language overrides are rejected before loading |

Select a folder, Hugging Face repository or compatible `.tar.bz2` archive URL.
For manual configuration, specify relative filenames for every required role,
review the declared license and confirm copying or downloading and installation.
Browser folder selection accepts top-level ONNX weights and
`tokens.txt`, plus license notices; other token names or nested layouts require
preparing that folder layout first. A multilingual export is required for
Spanish; an English-only export does not acquire Spanish support from a language
hint. Matching ONNX
exports and tokens must be compatible with the installed runtime. V validates
loading in a separate process before publishing an imported model.

Installed models appear in transcription options and the local compatible audio
API. CPU execution reports **Native** precision: the model files determine
quantization, and V does not claim to convert arbitrary ONNX weights to int8 or
float16. Declared capabilities are transcription and CPU only.

Each transcription invocation starts an owned child and loads the recognizer
once. Normalized mono 16 kHz PCM audio is processed in consecutive windows of at
most 30 seconds, including the final partial window. Segment times describe
those windows; they are not measured speech boundaries. Word timestamps,
alignment, confidence and language detection capability are not advertised.
Language metadata is retained only when supplied by native results, without
substituting a requested language for a detected one. Cancellation and deadlines
terminate the owned child and remove temporary input and result files.

Decoding profiles, prompts and project glossaries are unsupported and rejected.
The default selection uses engine defaults without storing a Faster Whisper
recipe. A project with an existing glossary must have it cleared before using
this engine; it is not silently ignored. Speaker diarization remains a separate pipeline stage.

The windows do not overlap. Words across boundaries may lose accuracy; quality
has not been evaluated on representative conversations. Native inference with
real Whisper ONNX weights remains unverified. Automated checks use deterministic
local recognizers and child fixtures,
including audio longer than 30 seconds, cancellation, malformed results, custom
imports and the shared provider contract. This is experimental support, not a
claim that every ONNX export or language works.

## NeMo transducer verification

The [Parakeet TDT 0.6B v3 int8 sherpa export](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html)
completed a short CPU smoke check on 2026-10-20 through V's isolated provider,
using two threads and one synthetic Spanish clip of approximately 5.18 seconds.
The output contained text, no aligned words and no detected-language metadata;
progress reached the clip end and temporary worker files were removed. Network
access was disabled for the process namespace. The archive was checked against
SHA-256 `5793d0fd397c5778d2cf2126994d58e9d56b1be7c04d13c7a15bb1b4eafb16bf`.

This verifies one model's CPU execution path, not WER, real-conversation quality,
GPU support or compatibility with arbitrary NeMo checkpoints. The upstream
model's timestamp capabilities do not change V's current nominal-window output.
Parakeet's original weights are [CC-BY-4.0](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3);
the sherpa conversion and its four-file layout are distinct from a native `.nemo`
checkpoint. No weights are bundled with V. See
[the recorded model/device checks](benchmarks.md#additional-model-and-device-smokes-2026-10-20)
for the artifact digest, measured process limits and scope of the verification.
