# Edge Lab: local experiments

Edge Lab executes an already installed local model in a fresh process tree and
emits JSON with observations and measurements. Resource controls apply to that
tree only; the CLI/server parent retains its affinity, limits and environment.
The architectural boundary is [ADR-0011](adr/0011-edge-lab.md).

This executor is experimental. Linux CPU affinity and address-space limits are
covered by disposable-process tests; real model performance and other operating
systems have not been validated by those tests. PC constraints do not establish
SBC equivalence or support for ARM boards.

## Run an experiment

Save definitions, models, datasets and input text outside the source checkout.
For example, with an experiment saved under the XDG data directory:

```bash
v lab run "$XDG_DATA_HOME/voz/edge-lab/stt.json"
```

`voz lab run` is the compatibility alias. `XDG_DATA_HOME` in this example must
be an absolute directory outside the checkout. The command neither downloads
models nor installs or updates runtimes. It emits one JSON envelope on stdout;
raw worker diagnostics and paths are not echoed. Ctrl+C cancels the experiment.

Relative paths in a definition resolve against the definition's directory,
not the command's working directory. A leading `~` expands to the current home
directory first. Definitions, model directories, input paths
and the XDG experiment cache are rejected if they resolve inside the checkout,
including through symlinks. Temporary request/result files use a private run
directory under V's XDG cache and are removed after completion or failure.
Reports are not automatically saved or published.

## Definition version 1

A CPU STT definition:

```json
{
  "schema_version": 1,
  "workload": "stt",
  "profile": {
    "cpu_mask": null,
    "address_space_bytes": 2147483648,
    "device": "cpu",
    "systemd": false
  },
  "model": {
    "engine": "faster-whisper",
    "model_id": "tiny",
    "directory": "../models/faster-whisper-tiny"
  },
  "input": {
    "path": "../datasets/speech",
    "language": "es"
  },
  "timeout_seconds": 120
}
```

The model directory and dataset must already exist. STT engines are
`faster-whisper` and `whisper-cpp`; the model ID selects an entry of their pinned
catalog. Source and revision come from that entry, never from guessed metadata.
The supplied directory is not rehashed, so catalog identity is not proof that
its files match the pinned revision. STT uses the existing
[`bench` dataset manifest and scoring rules](benchmarks.md).

A CPU TTS definition using an installed catalog model:

```json
{
  "schema_version": 1,
  "workload": "tts",
  "profile": {
    "device": "cpu"
  },
  "model": {
    "engine": "sherpa-onnx-tts",
    "model_id": "kitten-nano-en-v0_8-int8"
  },
  "input": {
    "path": "../inputs/speech.txt",
    "voice_id": "0",
    "speed": 1.0
  },
  "timeout_seconds": 120
}
```

TTS reads the existing V model store under its XDG data root. A model directory
override is not accepted, and custom models outside the pinned TTS catalog are
not selected by this version. Input is a nonempty UTF-8 text file of at most
65,536 bytes and 20,000 characters. The existing chunk planner and synthesis
provider render every chunk; audio is measured and discarded, not saved.
`voice_id` is required and validated by the provider. Language follows that voice;
TTS does not accept a separate language override.

| Field | Accepted values and default |
| --- | --- |
| `schema_version`, `workload` | Required: integer `1`; `stt` or `tts`. |
| `profile.device` | Required. `cpu` executes; `cuda` returns `lab_device_unavailable` without falling back. |
| `profile.cpu_mask` | Optional null or a nonempty array of unique nonnegative logical CPU IDs. IDs must belong to the child's inherited allowed set. Null preserves inherited affinity. |
| `profile.address_space_bytes` | Optional null or a positive integer below 2^63. Null preserves inherited limits. This bounds each process's virtual address space, not RSS, total tree RAM or VRAM. |
| `profile.systemd` | Optional boolean, default false. True currently returns `lab_limit_unsupported`; no systemd command or host change occurs. |
| `model.engine`, `model.model_id` | Required catalog engine/model identity, matched to the workload. Cloud and HTTP inference engines are rejected. |
| `model.directory` | Required local directory for STT; omitted or null for TTS. |
| `input.path` | Required dataset directory for STT or text file for TTS. URLs are rejected. |
| `input.language` | Optional STT language; otherwise use the dataset language or engine detection. |
| `input.voice_id`, `input.speed` | TTS only: required voice ID; speed defaults to 1.0, range 0.5–2.0. |
| `timeout_seconds` | Optional positive finite wall-clock deadline, at most 86,400 seconds; default 120. Input duration does not replace this deadline. |

Unknown fields, duplicate JSON keys, booleans used as numbers and nonfinite
budgets are rejected. Definitions are limited to 65,536 bytes. There is no
command, argv, script, import, environment or systemd-property escape hatch.

## Process and resource behavior

The supervisor launches a fixed V worker with `shell=False`, no interactive
stdin and a new POSIX session. The fresh worker applies and verifies affinity
and `RLIMIT_AS` before importing engine code. It does not use `preexec_fn`.
Native children inherit those constraints and must stay in the experiment's
process group. This contains trusted installed engines, not arbitrary code.

Only the child environment receives offline mode, CPU-only device visibility
and thread-count hints. Existing OpenMP affinity overrides are removed there;
the parent environment remains unchanged. Thread hints use the selected mask's
size, or one when no mask is supplied. Native runtime thread counts can differ;
the report records hints separately from CPU affinity. TTS explicitly configures
its provider's thread count.

Setup must produce a readiness record within 15 seconds and also within the
overall deadline. The monotonic deadline includes setup, loading and inference.
Process creation itself can be delayed by the OS. Cancellation or expiration
terminates the owned process group, allows a bounded grace, kills remaining
members and reaps the direct worker. Orphaned grandchildren are reaped by the
OS; engines that detach descendants are not supported. Cleanup waits are bounded
and may add time after the inference deadline.

Systemd scopes remain unavailable until capability detection, effective
`MemoryMax`/`CPUQuota` verification, disabled argument expansion and scope-wide
cleanup are implemented and tested together. Selecting systemd never silently
executes without it. No system units, scheduler policy, swap, GPU settings,
controllers, parent limits or unrelated processes are modified.

The standalone CLI has no cross-process compute lock with an independently
running V server. Its observations disclose that external contention is not
measured; run comparisons without competing inference. There is no server/UI
experiment integration in this executor.

## Result envelope and measurements

| Top-level field | Meaning |
| --- | --- |
| `schema_version` | Edge Lab envelope version, currently 1; distinct from the bench report version. |
| `status`, `code`, `message` | `completed`, `failed`, `cancelled` or `timed_out`; stable failure code and fixed safe message, null on completion. |
| `constraints` | Separate requested profile and effective child controls, including thread environment values read by the child. Empty effective controls mean setup did not produce verified readiness. |
| `observations` | CPU identity when available, architecture, OS, Python/package versions, selected CPU device, model provenance and workload settings. Unknown versions are null. whisper-cli's binary version is currently unavailable. |
| `measured` | Values collected while actually executing the workload, with units/methods below. Readiness alone never produces a completed run. |
| `estimated` | Empty object in this version. No unavailable measurement is replaced by an estimate. |

STT reuses `bench` execution and exposes its schema version, load time, corpus
totals, memory and clip count. RTF is wall seconds / input audio seconds;
WER/CER use the existing corpus edit totals and normalization. Load includes
one second of silent inference. Missing references produce unavailable accuracy.
Faster Whisper executes CPU int8. whisper.cpp uses its model-file quantization;
the bench `compute_type` label does not change that binary's quantization.

RSS is the worker's process high-water mark for Faster Whisper, or the largest
completed child peak for whisper.cpp. It is not a sum of simultaneous tree RSS.
CPU runs do not query GPU memory: VRAM fields remain null. Address-space limits,
RSS observations and cgroup memory are different quantities.

TTS reports render wall seconds, input character count, rendered audio seconds,
frames, sample rate and chunk count. Worker and largest completed-child RSS
peaks are separate. Render duration excludes inserted inter-chunk silence because
this command does not assemble or export audio. `first_audio_seconds` measures the first completed chunk returned to the caller,
including initial model loading; it is not streaming latency to the first sample.
`throughput_audio_seconds_per_second` divides rendered audio duration by render
wall time, including provider teardown. Preparation is excluded. Unavailable RSS
observations remain null with a reason. See
[benchmark definitions](edge-lab-benchmarks.md) for precise scope and comparison
rules; these metrics are not validated hardware performance results.

Use [`v lab compare`](edge-lab-results.md) to render saved reports as a
Markdown comparison table without running another experiment.

Failed and interrupted runs return empty measurements and preserve readiness
observations when available. An allocation failure is not automatically diagnosed
as physical RAM exhaustion; no OOM attribution is fabricated. Output excludes
source paths, audio filenames, input text and raw exceptions. A single run does
not establish variance or SBC compatibility.

## Exit codes and platform limits

Exit code 0 means a complete workload, 2 means invalid input or unsupported
capability, 124 means deadline expiration, 130 means cancellation, and 1 covers
other execution failures. A failed model/runtime check cannot return success.

The supervisor requires POSIX process groups. Address-space limiting is enabled
only on Linux in this version; affinity additionally requires the scheduler APIs
and permissions. Other POSIX systems can reject controls they do not expose.
Windows returns `lab_limit_unsupported` before spawning. No constrained Windows,
macOS, GPU or real-model performance support is claimed from disposable Linux
process tests.
