# Edge feasibility: TinyML, wake-word and wearables

Status: research only (slice V9-03). No hardware was bought, no firmware was
flashed, no model was downloaded and nothing was run. Every figure below is
either quoted from a primary source with its URL, or explicitly marked
**unverified / inferred**.

Research date: **2026-10-11** (all URLs below were read on that date; the
repositories move, so re-check before relying on a number).

Starting point: [the earlier audit](../../.ai/audit-av/08-TINYML-EDGE-FEASIBILITY.md),
which could not find the licence or size of microWakeWord. Both are resolved
in section 2. For wheel and runtime availability on aarch64 see
[arm-linux-dependencies.md](arm-linux-dependencies.md) (written in parallel by
another slice). For how V measures things today see
[benchmarks.md](../benchmarks.md).

Legend: **[V]** verified against a primary source, **[I]** inferred or
reasoned, **[?]** not found / unknown.

---

## 1. Hardware classes and realistic voice workloads

V's current workload is full-file STT and local TTS on a PC. The table says
which *kinds* of voice work are plausible on each class. It is a plan for what
to measure, not a compatibility claim: **no class below has been run with V**.

| Class | Examples | Memory order of magnitude | OS |
|---|---|---|---|
| A. Limited PC | Laptop without GPU, 8-16 GB | GBs | Full Linux/Windows/macOS |
| B. Linux ARM SBC | Raspberry Pi 4/5, Orange Pi, RK3588 boards | 1-8 GB | Full Linux |
| C. Microcontroller | ESP32-S3 | hundreds of KB internal SRAM, optional external PSRAM | RTOS / bare metal |
| D. Wearable with OS | Wear OS or Linux-based watch | 1-2 GB (**[I]**, varies by model) | Mobile OS |
| E. Device with no full OS | Camera, toy, MCU without filesystem | KBs to low MBs | Firmware only |

Capability matrix. "Yes" means the workload class is known to exist and be
used at that tier in some public project, not that V supports it.

| Workload | A | B | C (MCU) | D | E |
|---|---|---|---|---|---|
| Full STT (minutes of audio, Whisper-class) | Yes (what V does today) | Plausible with tiny/base-size models, **must be measured** [I] | **No** | **No** locally; offload [I] | **No** |
| Streaming/short-command recognition (fixed vocabulary) | Yes | Yes [V for sherpa-onnx KWS existing; speed not published] | Yes, tiny fixed-vocabulary models (TFLite Micro `micro_speech` is under 20 kB, 2 keywords) [V] | Plausible [I] | Plausible, fixed list [I] |
| Wake-word | Yes | Yes | Yes (microWakeWord, sec. 2) [V] | Plausible if the OS allows always-on audio [I] | Depends on the chip [I] |
| Full natural TTS (neural, multi-sentence) | Yes | Only some models are faster than real time on a Pi 4 (sec. 4) [V] | **No** [I] | Possible only with a small model; **measure** [I] | **No** |
| Prerecorded phrases | Yes | Yes | Yes | Yes | Yes |

Explicitly out of scope: running Whisper, KittenTTS or any neural
vocoder-based TTS on a microcontroller. Nothing in the sources below suggests
it is feasible, and the model files alone (tens of MB, sections 3 and 4)
exceed the memory of that class by orders of magnitude. [I]

---

## 2. microWakeWord (confirmed from primary sources)

### 2.1 Licence **[V]**

| Item | Licence | Source |
|---|---|---|
| Training framework / code (`kahrendt/microWakeWord`) | Apache License 2.0 (GitHub licence detection returns `apache-2.0`; the repo `LICENSE` is the Apache 2.0 text) | https://github.com/kahrendt/microWakeWord and https://api.github.com/repos/kahrendt/microWakeWord, read 2026-10-11 |
| Published models (`esphome/micro-wake-word-models`), weights and manifests | Apache License 2.0. README: "These terms cover the entire contents of this repository, including the trained model weights (`.tflite`) and their manifests (`.json`). There are no separate or additional terms for the model binaries." `NOTICE`: "Copyright 2024-2026 Open Home Foundation" | https://github.com/esphome/micro-wake-word-models (README, `NOTICE`), read 2026-10-11 |
| ESPHome `micro_wake_word` component | GitHub reports `NOASSERTION` for the whole ESPHome repo (mixed licences); not analysed here | https://api.github.com/repos/esphome/esphome, read 2026-10-11 |

Caveats:

- The README of the models repo warns that wake-word *names* ("Alexa", "Hey
  Jarvis", "Okay Nabu"...) "may refer to products, services, or characters
  owned by third parties" and imply no affiliation. The Apache licence "grants
  no rights to any third-party trademark" (`NOTICE`). Shipping a wake word
  called "Alexa" in a product is a trademark question, not a licence question.
- **[?]** The licences of the *training data* behind each published model
  (synthetic Piper-generated positives, negative-speech and noise datasets)
  are not stated in the README. The training README says positives are
  generated with `rhasspy/piper-sample-generator` and that pre-generated
  negative-dataset features live in a Hugging Face dataset
  (`kahrendt/microwakeword`); that dataset's licence was not checked. If V ever
  *trains* models rather than shipping the published `.tflite`, this must be
  reviewed.

### 2.2 Model size **[V]**

Sizes of the `.tflite` files, from the GitHub contents API
(https://api.github.com/repos/esphome/micro-wake-word-models/contents/models and
the `models/v2` subdirectory), read 2026-10-11:

| Model | Manifest version | `.tflite` size (bytes) |
|---|---|---|
| `alexa`, `hey_jarvis`, `okay_nabu` (original, `models/`) | 1 | 115,400 each (about 113 KiB) |
| `okay_nabu` (`models/v2/`) | 2 | 60,264 |
| `hey_jarvis` (`models/v2/`) | 2 | 52,272 |
| `hey_mycroft` (`models/v2/`) | 2 | 57,248 |
| `alexa` (`models/v2/`) | 2 | 55,856 |
| `vad` (`models/v2/`, voice-activity model, not a wake word) | 2 | 34,328 |
| `hey_home_assistant`, `choo_choo_homie`, `hey_peppa_pig`, `okay_computer` (`models/v2/experiments/`) | 2 | 62,112 each |

So a wake-word model is **roughly 35-115 KB on disk**: three orders of
magnitude smaller than the ASR/TTS models V ships (tens to hundreds of MB).

### 2.3 RAM **[V for the arena; [?] for the total]**

The v2 manifests publish `tensor_arena_size`, the minimum TFLite Micro
tensor arena in bytes. ESPHome docs define it as "The minimum size of the
tensor arena in bytes" (https://esphome.io/components/micro_wake_word.html,
read 2026-10-11).

| Model (v2) | `tensor_arena_size` | `probability_cutoff` | `sliding_window_size` | Source |
|---|---|---|---|---|
| `okay_nabu` | 26,080 B | 0.97 | 5 | `models/v2/okay_nabu.json` |
| `vad` | 16,772 B | 0.5 | 5 | `models/v2/vad.json` |
| docs example value | 22,860 B | n/a | n/a | esphome.io page, Model JSON section |

The ESPHome component source (`esphome/components/micro_wake_word/__init__.py`,
`dev` branch, read 2026-10-11) states that the original (v1) manifest models
"require a minimum of 45672 bytes" of arena (it hard-codes this value when
converting a v1 manifest).

Important: the arena is **not** the whole RAM cost. Per the source, the
component also allocates a 1,024-byte variable-tensor arena
(`STREAMING_MODEL_VARIABLE_ARENA_SIZE`), a ring buffer for audio, spectrogram
feature buffers, an inference task stack (optionally placed in PSRAM via
`task_stack_in_psram`), plus the model itself. **No published total-RAM or
CPU-load figure was found** in the ESPHome page, the model repos or the
microWakeWord README. [?]

### 2.4 Pipeline numbers **[V]** (microWakeWord README)

Source: https://github.com/kahrendt/microWakeWord, read 2026-10-11.

- Input: mono audio at 16 kHz.
- Features: 40 spectrogram features over a 30 ms window with a 10 ms stride
  (TFLite Micro `micro_speech` preprocessor, with noise suppression and
  automatic gain control).
- Streaming inference every 30 ms (the first conv layer strides over three
  10 ms slices).
- Architecture: MixConv-style mixed depthwise convolutions; trained
  non-streaming, converted to streaming, quantised.
- Decision: "If the model consistently predicts the wake word over multiple
  windows, then we predict that the wake word has been said" (sliding-window
  average above `probability_cutoff`).

### 2.5 Supported hardware

- **[V]** Framework target: "low power devices" via "TensorFlow Lite for
  Microcontrollers" (README). The README names no specific chip.
- **[V]** The ESPHome component is restricted to ESP32-family targets
  (`cv.only_on_esp32` in `__init__.py`) and pulls `espressif/esp-tflite-micro`
  and `espressif/esp-nn` as ESP-IDF components.
- **[V, correction to the earlier audit]** The ESPHome documentation page does
  **not** mention "ESP32-S3" or any PSRAM *requirement*; the only PSRAM
  reference is the optional `task_stack_in_psram` setting. The claim in the
  earlier audit that detection is documented "on ESP32-S3 with PSRAM" was not
  reproduced in the page read today. Which ESP32 variants run it well is
  therefore **[?]**; the ESP32-S3 is a plausible target [I] (Espressif lists
  "512 KB of internal SRAM", PSRAM support and "vector instructions" for AI
  acceleration: https://www.espressif.com/en/products/socs/esp32-s3, read
  2026-10-11), but that is a capability of the chip, not a statement about
  microWakeWord.
- **[?]** Non-ESP targets (RP2040, nRF, STM32) were not documented in the
  sources read.

**Takeaway for V:** licence is permissive for both code and weights; a model
fits in about 35-115 KB flash and about 17-46 KB arena (plus the overheads
above); V does not need to host anything: wake-word is a firmware concern.

---

## 3. Keyword spotting and short commands

### 3.1 On microcontrollers (TFLite Micro)

- **[V]** TFLite Micro ships a `micro_speech` example that recognises 2
  keywords ("yes", "no") with "a less than 20 kB model"
  (https://github.com/tensorflow/tflite-micro/tree/main/tensorflow/lite/micro/examples/micro_speech,
  read 2026-10-11). The page shows a desktop build and a Cortex-M0 QEMU
  target; it lists no supported boards, arena size or licence in the content
  retrieved.
- **[V]** microWakeWord (sec. 2) is, technically, a single-keyword spotter
  built on the same runtime and the same `micro_speech` audio front end.
- **[?]** Other MCU keyword-spotting stacks (Espressif ESP-SR / WakeNet /
  MultiNet, Edge Impulse, Picovoice) exist, but their licences, sizes and
  supported chips were **not** verified in this slice and must not be assumed
  open source or free for commercial use. Note, as a pointer only, that the
  ESP32-S3 page above mentions ESP-SR and ESP-Skainet.
- **[I]** A multi-command recogniser on a MCU is a fixed-vocabulary classifier
  (tens of commands at most). It cannot take arbitrary speech; anything open
  vocabulary needs an SBC or more.

### 3.2 On SBCs (sherpa-onnx KWS)

Source: https://k2-fsa.github.io/sherpa/onnx/kws/index.html and
https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html, read
2026-10-11.

- **[V]** Three pretrained streaming zipformer KWS models are published:
  `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` (Chinese + English),
  `sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01` (Chinese) and
  `sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01` (English).
- **[V]** Keywords are open-ended text (you supply keywords with boosting
  scores and trigger thresholds via the CLI `sherpa-onnx-keyword-spotter`),
  not a fixed trained set.
- **[V]** Sizes (from the page's file listings):

| Model | int8 encoder | fp32 encoder | decoder | joiner | Directory total shown |
|---|---|---|---|---|---|
| zh-en-3M-2025-12-20 (chunk-8 or chunk-16 variant) | 4.4 MB | 12 MB | 743 KB (fp32 only) | 85 KB int8 / 331 KB fp32 | "total 38M" (contains both chunk variants and `en.phone` 3.2 MB) |
| wenetspeech-3.3M-2024-01-01 | 4.6 MB | 12 MB | 177 KB int8 / 660 KB fp32 | 64 KB int8 / 248 KB fp32 | "total 18M" |
| gigaspeech-3.3M-2024-01-01 | 4.6 MB | 12 MB | 272 KB int8 / 1.1 MB fp32 | 160 KB int8 / 628 KB fp32 | "total 19M" |

- **[V]** Algorithmic latency of the zh-en model: chunk_size=8 gives 160 ms,
  chunk_size=16 gives 320 ms.
- **[V]** Training data: WenetSpeech L subset (10,000 h) and GigaSpeech XL
  subset (10,000 h) for the two 2024 models; not stated for the 2025 model.
- **[V]** The page documents the CLI and a prebuilt Android APK
  (https://k2-fsa.github.io/sherpa/onnx/kws/apk.html).
- **[?]** The KWS page does **not** mention Raspberry Pi, ARM or embedded
  targets, and publishes **no RTF, RAM or CPU numbers** for KWS. Parameter
  counts are not given ("3M"/"3.3M" in the names are the only hint). Whether
  these run comfortably on a Pi must therefore be measured (section 6).
- **[?]** Model licences were not checked here; check them before bundling.

Practical reading: on an SBC the KWS models are an order of magnitude bigger
than microWakeWord (about 5 MB vs about 0.05 MB) but handle arbitrary,
user-defined keywords. [I]

---

## 4. Lightweight TTS on SBC (sherpa-onnx, Raspberry Pi 4)

Source: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/rtf.html
(table), and the raw sources
`docs/source/onnx/tts/pretrained_models/{rtf,vits}.rst` in
https://github.com/k2-fsa/sherpa, read 2026-10-11.

What the source states:

- Hardware: **Raspberry Pi 4 Model B Rev 1.5**.
- Binary: `sherpa-onnx-offline-tts`, run in a loop with `--num-threads` set to
  1, 2, 3 and 4.
- Text: one sentence per model (English: "Friends fell out often because life
  was changing so fast. The easiest thing in the world was to lose touch with
  someone."; Chinese models use a Chinese sentence).
- RTF = synthesis time / audio duration, so **below 1 is faster than real
  time**. (The page does not define RTF; this is the standard meaning and the
  one V uses in [benchmarks.md](../benchmarks.md).)
- The last column of the table has no header on the page; the values match the
  model sizes in the per-model sections (for example 61 MB for
  `en_US-glados`, confirmed in its download listing), so it is read as
  **model size**. [I, small]
- Not stated: sherpa-onnx version, quantisation, run count, whether the
  figure is a single run or an average, RAM, CPU frequency/governor, cooling.

Selected values (RTF; full table at the URL above):

| Model | Language / speakers | 1 thread | 2 threads | 4 threads | Size |
|---|---|---|---|---|---|
| `aishell3` VITS | Chinese, 174 speakers | 0.365 | 0.220 | 0.156 | 30 MB |
| `vits-piper-en_US-libritts_r-medium` | English, 904 speakers | 0.790 | 0.493 | 0.357 | 75 MB |
| `en_US-lessac-medium` (Piper VITS) | English, 1 speaker | 0.774 | 0.482 | 0.357 | 61 MB |
| `vits-piper-en_US-glados` | English, 1 speaker | 0.812 | 0.480 | 0.349 | 61 MB |
| `matcha-icefall-zh-baker` | Chinese, 1 speaker | 0.892 | 0.536 | 0.391 | 73 MB |
| `matcha-icefall-en_US-ljspeech` | English, 1 speaker | 0.941 | 0.561 | 0.411 | 71 MB |
| `vits-ljspeech` | English, 1 speaker | 6.057 | 3.517 | 2.206 | 109 MB |
| `vits-melo-tts-zh_en` | zh + en, 1 speaker | 6.727 | 3.877 | 2.518 | 163 MB |
| `kokoro-en-v0_19` | English, 11 speakers | 6.629 | 3.870 | 2.774 | 330 MB |
| `kokoro-multi-lang-v1_1` | zh + en, 103 speakers | 7.635 | 4.470 | 3.191 | 311 MB |

Reading **[V, numbers; I, interpretation]**:

- On a Pi 4, the Piper/VITS "medium" voices and the Matcha models are below
  RTF 1.0 even with a single thread (0.77-0.94), so they synthesise faster
  than real time; Kokoro, Melo and the plain LJSpeech/VCTK VITS models are
  **not** (RTF 2.2-7.6 even with 4 threads). A model's name or its size on disk
  does not predict this: `vits-ljspeech` (109 MB) is about 8x slower than
  `en_US-lessac-medium` (61 MB).
- **KittenTTS in sherpa-onnx**: the TTS index lists `kitten-nano-en-v0_1-fp16`,
  `kitten-nano-en-v0_2-fp16` and `kitten-mini-en-v0_1-fp16`, but the page
  gives them **no Raspberry Pi RTF** (nor for PocketTTS, SupertonicTTS or
  ZipVoice). So there is no citable Pi figure for KittenTTS from this source.
  [?] Note these are sherpa-onnx's packaging of KittenTTS v0.1/v0.2, not the
  KittenTTS 0.8 / 2 releases discussed in the earlier audit.
- These are a Pi 4. A Pi 5 or an RK3588 board will differ; no figure for them
  was found in these sources. [?]
- The RTF measures compute only for a single sentence; it says nothing about
  time-to-first-audio, which for an offline (non-streaming) synthesiser
  equals the whole synthesis time. [I]

whisper.cpp numbers (carried over from the earlier audit, not re-fetched
today): README table lists memory tiny about 273 MB, base about 388 MB, small
about 852 MB, and disk tiny 75 MiB, base 142 MiB. The audit flagged that
secondary sources (Turing Pi) give different RAM figures and that nothing was
measured on a Pi. Treat STT-on-SBC RAM as **unverified** until section 6 is
run.

---

## 5. Wearables and cameras: what could run locally

This section is reasoning from sections 1-4, not from device measurements.
No source here covers a specific watch or camera. All of it is **[I]**.

| Workload | Local on the device? | Why |
|---|---|---|
| Wake-word | Yes, plausible | microWakeWord models are tens of KB with a 17-46 KB arena (sec. 2); this class of model is what always-on low-power cores are for. Cost to verify: continuous microphone + 30 ms inference cadence is a standby-power question, not a model-size question. |
| Fixed-list command spotting | Yes, plausible | `micro_speech`-style models are under 20 kB (sec. 3.1); open-vocabulary spotting (sherpa-onnx KWS, about 5 MB int8 encoder) fits a wearable with a mobile OS but not an MCU. |
| Voice activity detection | Yes | The published `vad` model is 34 KB with a 16.7 KB arena (sec. 2). |
| STT of long audio | No: external processor | Whisper-class models are hundreds of MB in memory (sec. 4 note); a battery-powered device would have to sustain heavy CPU for the length of the audio. Offload to a phone, SBC or PC (V). |
| Natural TTS | No on MCU/camera; maybe on a wearable with an OS | Even on a Pi 4 only some models beat real time (sec. 4), and they weigh 30-330 MB. |
| Prerecorded phrases | Yes | Flash storage + a DAC/speaker; no model. Generate the phrases with V on a PC and ship the audio files. |

Architecture implied: a small always-on front end (wake-word/VAD/short
commands) wakes a "processor external" (phone, SBC, PC running V) that does
the STT and TTS, with prerecorded phrases covering the offline-feedback gap.
The audio transport, security of that link and privacy implications are not
analysed here and would need their own design.

Cameras: nothing in the sources links cameras to voice workloads. A camera
with a microphone is a class E device for this purpose. [I]

---

## 6. Validation proposal (no hardware purchases, no firmware flashing)

Goal: replace each **[?]** and **[I]** above with a measurement, using only
what exists or is free, and without touching V's core. This extends the
metric set of the earlier audit and of V's Edge Lab (planned in the V-8
slices: limits applied only to the experiment subprocess: core affinity, RAM
cap, optional `systemd-run --user --scope`).

### 6.1 Metrics (same names as Edge Lab)

| Metric | Definition | Applies to |
|---|---|---|
| Time to first result | Input start to first segment (STT) or first audio sample (TTS) | STT, TTS, KWS |
| RTF | Compute time / audio duration; below 1 = faster than real time | STT, TTS |
| Throughput | Seconds of audio produced per second of compute (inverse of TTS RTF) | TTS |
| Peak RAM | Peak RSS of the experiment process (`ru_maxrss`); report the TFLite `tensor_arena_size` separately for MCU-class models | all |
| CPU | Mean and peak utilisation during inference, and core count/frequency | all |
| Model size | Bytes on disk of the exact artefact tested (int8 vs fp32 stated) | all |
| Load time | Process start to first inference | all |
| Energy | Joules per minute of audio, **only** if an instrument exists (USB power meter, etc.) | optional |
| Quality | WER/CER on the same corpus (`voz bench`); for KWS, false-accept rate per hour on ambient audio and false-reject rate on spoken keywords | STT, KWS |

### 6.2 What can be measured on the existing PC (no new hardware)

1. **Constrained-PC proxy** (Edge Lab, class A, simulating B): pin the process
   to 2-4 cores and cap RAM, then run the sherpa-onnx TTS models of section 4
   to compare against the published Pi 4 RTF. Purpose: calibrate how a PC
   limited to N cores relates to the published Pi numbers. It does not
   replace a real Pi; report the ratio as an *estimate* in the `estimated`
   JSON field, separate from `measured`.
2. **sherpa-onnx KWS** (the 3 models in sec. 3.2): RTF, peak RAM, CPU and
   model size per chunk variant and int8 vs fp32, with the same constrained
   profile. This fills the missing KWS performance numbers.
3. **microWakeWord on the PC**: the `.tflite` files can be loaded with a
   stock TFLite interpreter on a laptop to count false accepts per hour on
   ambient recordings and false rejects on spoken phrases. This validates
   *accuracy* only; it says nothing about MCU speed. It requires downloading
   the models, so it is a separate approved step.
4. **Corpus**: a small personal dataset kept outside the repository, as
   `voz bench` already does ([benchmarks.md](../benchmarks.md)).

### 6.3 What needs a real device (later, owner decision, `[A]`)

- **Raspberry Pi 5 / Orange Pi** (class B): a Pi 4 figure exists for TTS but
  not for a Pi 5; run the same Edge Lab definition there. Aarch64 wheel
  availability is covered in [arm-linux-dependencies.md](arm-linux-dependencies.md).
  Pass/fail criteria belong to the SBC validation plan (V9-02); this document
  proposes only that "compatible" requires RTF below 1.0 for the chosen TTS or
  STT model, peak RAM below the board's memory with headroom, and no thermal
  throttling over a sustained run.
- **ESP32-S3 + microWakeWord**: would need flashing firmware and a microphone;
  out of scope for this slice. The questions to answer there are the total RAM
  (internal vs PSRAM), CPU duty per 30 ms inference, flash use, and standby
  current, none of which is published (sec. 2.3).
- **Wearable with OS**: only after the above, as an app/APK experiment
  (sherpa-onnx publishes an Android KWS APK, sec. 3.2).

### 6.4 Reporting rules

- Always record device model, OS, runtime versions, thread count, quantisation
  and whether power-saving governors were on.
- Keep `measured` and `estimated` values in separate fields; never present a
  PC-proxy ratio as a Pi result.
- Say "compatible" only after the run on the target; until then the status is
  "plausible, unmeasured".

---

## 7. Summary of verified vs unverified

| Verified (with URL, 2026-10-11) | Unverified / inferred |
|---|---|
| microWakeWord code and published models: Apache-2.0 (sec. 2.1) | Licences of the training datasets |
| Published model sizes: 34-115 KB; tensor arena 16.7-26 KB (v2), 45.7 KB (v1 minimum) | Total RAM, CPU load and standby power on a real MCU |
| ESPHome component is ESP32-only; no S3/PSRAM requirement in its docs | Which ESP32 variants run it well; non-ESP targets |
| sherpa-onnx KWS: 3 models, int8 encoder 4.4-4.6 MB, latency 160/320 ms | Any KWS RTF/RAM on an SBC; model licences |
| sherpa-onnx TTS RTF on Raspberry Pi 4 (sec. 4 table) | Pi 5 / RK3588 figures; KittenTTS RTF; RAM of any TTS model |
| TFLite Micro `micro_speech`: 2 keywords, under 20 kB | Other MCU KWS stacks (ESP-SR, Edge Impulse, Picovoice): licences and sizes |
| Wearable/camera capability split (sec. 5) | Everything in it: reasoned, not measured |
| STT on SBC memory figures | Contradictory secondary sources; not measured |
