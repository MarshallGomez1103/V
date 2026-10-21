# SBC validation protocol: Linux aarch64, CPU

This protocol prepares measurements on a Raspberry Pi 5 or a specifically named
Orange Pi board. **No board has been validated by this document.** Run it on the
actual target; a constrained PC, an aarch64 wheel or a successful import does
not establish board compatibility. Record each board/OS/runtime/model combination
separately. The [dependency inventory](arm-linux-dependencies.md) is a dated
source review, not an installation guarantee for the current lockfile.

The executable contract is [Edge Lab](../edge-lab.md), its
[metric definitions](../edge-lab-benchmarks.md) and
[resource boundaries](../adr/0011-edge-lab.md). This procedure installs nothing,
downloads nothing, changes no host limits and uses no accelerator or cloud API.

## 1. Prerequisites and isolated state

Use a Linux **64-bit aarch64 userland** on the target, an already provisioned V
checkout/environment, and existing `ffmpeg` and `ffprobe` executables on PATH.
Do not run an installer as part of this protocol. V's main CLI prepares FFmpeg
before subcommands and can otherwise download its fallback bundle; stop if either
executable is missing. Use a subshell so HOME/XDG changes end when it exits.
Run all snippets below in that same subshell, from the repository root. If the
existing environment is elsewhere, adjust the `SBC_PYTHON` assignment before
running the first block:

```bash
bash
set -eu
umask 077
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
SBC_PYTHON="$PWD/.venv/bin/python"
test -x "$SBC_PYTHON"
export SBC_RUN="$(mktemp -d -t v-sbc-XXXXXXXX)"
export HOME="$SBC_RUN/home"
export XDG_CONFIG_HOME="$SBC_RUN/config"
export XDG_DATA_HOME="$SBC_RUN/data"
export XDG_CACHE_HOME="$SBC_RUN/cache"
export XDG_STATE_HOME="$SBC_RUN/state"
export XDG_RUNTIME_DIR="$SBC_RUN/runtime"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" \
  "$XDG_STATE_HOME" "$XDG_RUNTIME_DIR" "$SBC_RUN/definitions" "$SBC_RUN/reports"
export PYTHONPATH="$PWD/src"
"$SBC_PYTHON" -m voz.interfaces.cli.main lab run --help
"$SBC_PYTHON" -m voz.interfaces.cli.main lab compare --help
```

The direct interpreter avoids dependency resolution or environment synchronization.
Definitions, models, inputs and reports must resolve
outside the checkout; symlinks into it are also rejected. Never point this run
at an existing personal V data directory. Stop competing inference manually;
Edge Lab has no cross-process admission lock with a separate V server.

Save the source revision and tool versions privately:

```bash
git rev-parse HEAD > "$SBC_RUN/reports/source-revision.txt"
git diff --stat > "$SBC_RUN/reports/source-changes.txt"
ffmpeg -version > "$SBC_RUN/reports/ffmpeg-version.txt"
ffprobe -version > "$SBC_RUN/reports/ffprobe-version.txt"
"$SBC_PYTHON" - <<'PY' > "$SBC_RUN/reports/host.json"
import json, os, platform
from pathlib import Path

def read(path):
    try:
        return Path(path).read_text().strip().strip("\0")
    except (OSError, UnicodeError):
        return None

print(json.dumps({
    "architecture": platform.machine(),
    "kernel": platform.release(),
    "python": platform.python_version(),
    "os_release": read("/etc/os-release"),
    "board_model": read("/proc/device-tree/model"),
    "allowed_cpu_ids": sorted(os.sched_getaffinity(0)),
    "meminfo": read("/proc/meminfo"),
}, indent=2))
PY
```

Check that the observed architecture is `aarch64` or `arm64`. Also record board
revision/RAM, power supply, storage medium/filesystem, cooling, ambient conditions,
CPU governor/frequencies, swap/zram and other active workloads. Unknown values
remain unknown. Do not alter those settings to obtain a favorable result.
Record installed runtime versions from the resulting envelopes; additionally
record sherpa-onnx-core and any whisper-cli binary revision/build flags from the
existing installation's provenance. An absent package or executable is a blocker
for that engine, not permission to install it automatically.

## 2. Select existing model and corpus

The first STT candidate is catalog **`faster-whisper` / `tiny`**, CPU int8.
Supply an existing local snapshot of that exact catalog model, not a model name
that could trigger a download. Select a pre-existing, licensed/consented local
corpus directory with a valid [bench manifest](../benchmarks.md#personal-dataset-outside-git-s1309).
It must contain nonempty audio; references must describe the actual audio.
Do not use personal production transcripts or infer permission from file access.

```bash
read -r -p 'Existing faster-whisper tiny snapshot directory: ' SBC_STT_MODEL
read -r -p 'Existing licensed benchmark corpus directory: ' SBC_CORPUS
export SBC_STT_MODEL SBC_CORPUS
"$SBC_PYTHON" - <<'PY'
import json, os
from pathlib import Path
from voz.infrastructure.constrained_process import outside_checkout
from voz.interfaces.cli.bench import load_dataset

model = outside_checkout(Path(os.environ["SBC_STT_MODEL"]))
corpus = outside_checkout(Path(os.environ["SBC_CORPUS"]))
assert model.is_dir(), "Missing model directory"
assert all((model / name).is_file() for name in
           ("model.bin", "config.json", "tokenizer.json")), "Incomplete CT2 layout"
assert load_dataset(corpus).items, "Empty corpus"
allowed = sorted(os.sched_getaffinity(0))
assert allowed, "No available logical CPUs"
root = Path(os.environ["SBC_RUN"])
for name, mask in (("one-cpu", allowed[:1]), ("up-to-four-cpus", allowed[:4])):
    definition = {
        "schema_version": 1, "workload": "stt",
        "profile": {"device": "cpu", "cpu_mask": mask,
                    "address_space_bytes": None, "systemd": False},
        "model": {"engine": "faster-whisper", "model_id": "tiny",
                  "directory": str(model)},
        "input": {"path": str(corpus)},
        "timeout_seconds": 120,
    }
    (root / "definitions" / f"stt-{name}.json").write_text(json.dumps(definition))
PY
```

This preparation parses the corpus manifest without inference. It checks layout,
not model integrity or engine execution. Hash the selected files and record the
model source/revision, quantization and license in private evidence before running.
Edge Lab does not rehash an STT directory against its catalog. Record corpus
identity/license, manifest/audio/reference hashes, languages, duration and clip
count privately. WER/CER require actual references; missing references yield
unavailable accuracy, never zero error. Synthetic audio can test the procedure,
but cannot establish real-conversation accuracy.

The profiles choose available **logical CPU IDs**, not physical cores. If fewer
than four are available, the second profile uses that smaller set; on a one-CPU
system the profiles coincide and are not independent comparisons. Thread hints
follow mask size; record observed runtime behavior separately.

Both profiles leave address space unlimited except for inherited restrictions.
To test a specific product budget, copy a definition and set
`profile.address_space_bytes` to the chosen positive byte count; record why that
budget was chosen. It bounds per-process virtual address space, **not physical
RAM or aggregate tree RSS**. Never derive it by copying the board's RAM capacity.
`systemd: true` and CUDA are unavailable in this executor; do not use them here.

For a separate whisper.cpp trial, select its exact existing catalog ID and local
GGML directory, set `engine` to `whisper-cpp`, and make the already built
`whisper-cli` available through `VOZ_WHISPER_CPP_BIN` or PATH. Record binary hash,
version/build flags and GGML file hash/quantization. Do not reuse the CT2 model
or label a model-file quantization as a bench-selected precision. Whisper ONNX,
custom imports, diarization, KWS and MCU workloads are outside this executor.

## 3. Execute explicit, bounded repetitions

Review each definition first. The example deadline is 120 seconds per run,
including setup, loading and inference; it is a safety bound, not a performance
requirement. Choose a different explicit deadline before a longer corpus trial
if needed (maximum 86,400 seconds). A timeout is a recorded incomplete trial;
never silently extend it or replace it with success.

Run the two profiles serially, three times each, retaining every envelope and
exit code. Each invocation creates a fresh worker. This is a fresh-process test,
not a cold-storage-cache test: do not drop system caches or claim cold boots.

```bash
for SBC_REPETITION in 1 2 3; do
  for SBC_PROFILE in one-cpu up-to-four-cpus; do
    SBC_STEM="$SBC_RUN/reports/stt-$SBC_PROFILE-$SBC_REPETITION"
    if "$SBC_PYTHON" -m voz.interfaces.cli.main lab run \
      "$SBC_RUN/definitions/stt-$SBC_PROFILE.json" \
      > "$SBC_STEM.json" 2> "$SBC_STEM.stderr"; then
      SBC_EXIT=0
    else
      SBC_EXIT=$?
    fi
    printf '%s\n' "$SBC_EXIT" > "$SBC_STEM.exit"
    if test "$SBC_EXIT" -eq 130; then break 2; fi
  done
done
"$SBC_PYTHON" -m voz.interfaces.cli.main lab compare \
  "$SBC_RUN"/reports/stt-*.json > "$SBC_RUN/reports/comparison.md"
```

Inspect exit codes and envelopes, not just `compare`'s exit status. Comparison
success means valid reports, including failures; it does not mean inference
succeeded. A completed run requires exit 0, `status: completed`, verified effective
controls and actual workload measurements. Exit 2 rejects input/capability, 124
is timeout, 130 cancellation, and 1 an execution failure. Preserve failed trials.

For thermal stability, repeat a predeclared workload for the intended sustained
usage duration and retain board-specific temperature, CPU-frequency and throttle
observations alongside timestamps. Use only already available read-only telemetry;
record its method, units and sampling interval. Lack of telemetry means thermal
behavior is unverified. A single clip or start/end temperature cannot prove the
absence of throttling. Do not change cooling/governors or install monitoring tools
mid-comparison without starting a separately labeled configuration.

## 4. Optional TTS trial

TTS requires the already installed sherpa-onnx runtime and an **existing exported
catalog installation**, including `.voz-tts.json`, model files, phoneme data and
license notices. Copy that selected export into this disposable run's
`$XDG_DATA_HOME/voz/models/tts/<model_id>/`; do not point XDG at a production store,
follow links to one, invent an installation manifest or run `install()`.
The store checks manifest identity and file sizes, not a fresh archive digest.
Record the export's origin and hashes separately. If no prepared export exists,
leave TTS pending.

Use the TTS definition from [benchmark definitions](../edge-lab-benchmarks.md#tts-completed-chunks-and-render-throughput),
with an actually available catalog ID, voice ID and language-appropriate local
UTF-8 text. For example, `piper-es_MX-ald-medium` is family `vits`, voice `0`,
Spanish; `kitten-nano-en-v0_8-int8` is family `kitten`, voice `0`, English.
Kokoro needs its own catalog ID and validated voice selection. Keep text outside
the checkout and record its license/hash privately; the run discards synthesized
audio, so it cannot serve as a listening-quality review.

Apply the same explicit CPU masks/deadline/repetition policy, using separate
`tts-*.json` definitions and report names with the `lab run` and `lab compare`
commands above. TTS cannot override `model.directory` or select custom models in
version 1. Do not convert an STT definition by retaining STT-only input fields.

## 5. Metrics and compatibility decision

Preserve `measured` and `estimated` separately. Current envelopes leave `estimated`
empty. Any later PC/SBC extrapolation must show inputs/assumptions separately and
cannot substitute for a measurement on the target.

| Observation | Meaning and decision limit |
| --- | --- |
| STT RTF | Corpus wall seconds / audio seconds; report individual trials and spread, with corpus and warm-up policy. RTF below 1 describes this corpus running faster than real time, not universal compatibility. |
| STT load | One second of silent inference plus loading; not pure load latency. whisper.cpp reloads on each call. |
| WER/CER | Corpus edit totals with V's normalization; only on available licensed references. Report language/domain; no default quality threshold. |
| TTS first audio | First completed chunk, including its load/teardown; not first streamed sample or playback latency. |
| TTS throughput | Rendered audio seconds / render wall seconds; inverse is a derived TTS RTF, labeled as a calculation. Chunk silence is excluded. |
| Peak RSS | STT worker peak or largest completed-child peak; TTS reports those scopes separately. Never add them to claim simultaneous tree RAM or compare them to an address-space cap. |
| CPU/thermal/energy | Separate external observations with collector/scope/units. Envelope affinity and thread hints are not measured CPU utilization; energy requires an instrument. |

Use these distinct outcomes for **each exact board + OS image + Python/runtime +
engine/family + model/quantization + input/profile combination**:

- **Unmeasured:** no completed real run on that target, including import-only,
  synthetic-provider tests or PC proxies.
- **Blocked/incomplete:** prerequisite missing, failed control, timeout,
  cancellation or failed inference. Preserve the reason; do not generalize it to
  all ARM hardware or diagnose physical OOM without evidence.
- **Functionally validated for the tested combination:** every declared trial
  completed, requested controls were verified, output/metrics are valid and no
  owned worker remains. This says nothing about untested families or boards.
- **Meets the declared use-case budget:** in addition, the measured latency,
  quality, memory headroom and sustained thermal behavior meet requirements fixed
  **before** testing. Record those requirements and evidence. Batch transcription
  can be usable above RTF 1; a real-time use case requires its own latency policy.
  Board RAM minus one process's peak RSS does not prove system memory headroom.

No universal WER, latency, RAM margin or thermal threshold is assumed. If a
use-case budget or required measurement is absent, leave that assessment pending;
functional success alone cannot establish a recommended SBC configuration.

Raw definitions, model/corpus provenance, telemetry, stderr and results stay
outside Git. Retain the private run directory deliberately before temporary
storage is reclaimed; review/redact any selected report before publication.
Exit the subshell to restore the original environment. No board performance,
compatibility, thermal stability or real-model quality result is asserted here.
