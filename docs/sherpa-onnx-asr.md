# Experimental Whisper ONNX transcription

The `sherpa-onnx-asr` engine runs the offline Whisper family through the installed
sherpa-onnx runtime. Other ASR families exposed by that library are not registered
in V. No model is downloaded automatically and no additional runtime is installed
when selecting this engine.

In Models, choose **Add a custom model**, select sherpa-onnx ASR and the Whisper
family, then select a folder with the browser. Specify the relative encoder,
decoder and tokens filenames, review the declared license and confirm the copy
and installation. Browser folder selection accepts top-level ONNX weights and
`tokens.txt`, plus license notices; other token names or nested layouts require
preparing that folder layout first. A multilingual export is required for Spanish; an English-only
export does not acquire Spanish support from a language hint. Matching ONNX
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
and native model inference have not been validated with real Whisper ONNX
weights. Automated checks use deterministic local recognizers and child fixtures,
including audio longer than 30 seconds, cancellation, malformed results, custom
imports and the shared provider contract. This is experimental support, not a
claim that every ONNX export or language works.
