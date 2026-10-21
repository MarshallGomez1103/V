# ADR-0011: Edge Lab experiment resource boundaries

- Status: Accepted
- Date: 2026-10-15
- Owners: V maintainers
- Scope: resource constraints, process lifecycle and evidence for local Edge Lab
  experiments (V8-01). The executor and result format are **planned**.
- Related: [ADR-0001](0001-modular-monolith.md) (hexagonal boundaries),
  [ADR-0010](0010-voice-engines-and-tts.md) (engines and shared compute),
  [ADR-0006](0006-local-first-privacy.md) (privacy),
  [local benchmarks](../benchmarks.md) (existing STT measurements)

> Note (2026-10-22): SBC validation was dropped from the roadmap. Mentions of
> SBCs below are historical; Edge Lab remains a CPU experiment
> tool for the host PC.

## Context

Edge Lab will measure installed voice models on a PC under explicit resource
constraints. Restricting a desktop CPU and memory budget can reveal whether a
workload fits that budget on that host. It cannot reproduce an ARM instruction
set, SBC memory bandwidth, thermal envelope, accelerator or runtime availability.
No constrained PC result establishes Raspberry Pi, Orange Pi, Windows or other
unexercised platform support.

V already has `voz bench` for local STT and child-process TTS workers. Edge Lab
must preserve their metric meanings and the monolith's dependency boundaries,
without restricting the server, UI, normal jobs or unrelated applications.

## Decision

### 1. One experiment process tree, no host configuration

Resource controls apply only to a newly spawned experiment worker and its
descendants. The CLI/server supervisor stays outside that boundary. Never set
affinity or resource limits on the supervisor, move it into the experiment's
scope, or reuse a normal job worker whose limits would persist afterward.

Each run uses already installed engines and local model data. It neither
downloads models nor installs dependencies. HTTP inference endpoints, including
loopback servers, cannot be constrained by limiting their client process and
are excluded from constrained local inference experiments.

Domain and application code describe the experiment and requested budget without
OS APIs. Infrastructure owns spawning, capability detection, limits and cleanup;
the composition root wires it. The CLI validates data and translates outcomes.
No plugin loader, additional service or dependency is required by this decision.

The existing [compute slot](../../src/voz/application/compute_slot.py) remains
the admission mechanism when an experiment shares V's supervisor: it must not
overlap heavy normal inference. The slot is process-wide, not a host lock. A
standalone CLI cannot claim to serialize against a separately running server;
reports must disclose known concurrent work and this isolation limit.

### 2. Explicit, distinguishable controls

Every report records requested controls separately from effective controls,
including unsupported or failed controls. If a requested control cannot be
applied and verified, stop before model loading. Never silently substitute an
unconstrained run. An explicitly selected unconstrained measurement remains
possible, labeled as such.

| Control | Mechanism and meaning | Boundary and limitation |
| --- | --- | --- |
| CPU affinity | In the fresh worker, `os.sched_setaffinity(0, mask)` before runtime imports or thread creation; verify with `os.sched_getaffinity(0)`. Validate a nonempty mask within the inherited allowed set. | Logical CPU IDs, not physical core count, clock speed or CPU time quota. Worker threads and children inherit the restriction; native runtimes must not widen it. |
| Address-space budget | In the worker, `resource.setrlimit(resource.RLIMIT_AS, ...)`, respecting inherited hard limits; read back the effective limit. Record bytes and soft/hard values. | Per-process virtual address space, including mappings and libraries. Not a physical RAM/RSS cap, aggregate process-tree cap or VRAM limit. Descendants inherit the limit, but each has its own address space. |
| Optional scope memory/CPU budget | Only after explicit activation and successful detection: `systemd-run --user --scope` with generated `-p MemoryMax=...` and `-p CPUQuota=...` arguments for this experiment alone. Verify the new scope's effective properties and worker membership before inference. | `MemoryMax` bounds cgroup-accounted memory of the scope's processes; `CPUQuota` limits aggregate CPU time relative to one CPU (100% = one CPU). Neither emulates slower hardware. |

Affinity availability and CPU IDs are platform observations, not inferred from
`os.cpu_count()`. See the Python [scheduler APIs](https://docs.python.org/3.12/library/os.html#os.sched_setaffinity).
The distinction between virtual memory and resident memory follows Python's
[`RLIMIT_AS` contract](https://docs.python.org/3.12/library/resource.html#resource.RLIMIT_AS).
Large reservations or mapped weights can exhaust address space before RSS reaches
the nominal budget; a failed allocation alone does not prove physical RAM exhaustion.

The optional systemd backend requires the executable, a reachable user manager,
the necessary cgroup controllers and permission to apply the requested properties.
Executable presence alone is insufficient. Discovery does not activate it.
There is no `sudo`, system scope, persistent unit, lingering configuration,
controller enablement, ancestor-slice modification, swap reconfiguration or
change to system settings. An unavailable backend is reported, not repaired.

Create a uniquely named transient scope for the experiment child, using only
validated numeric properties. `MemoryMax` is not an RSS measurement and does not
by itself set a swap budget. Ancestor constraints may make effective limits
stricter. Record those restrictions when observable; scope OOM evidence is needed
to attribute an OOM failure. These meanings follow upstream
[resource-control documentation](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.resource-control.xml).

### 3. Safe spawn, cancellation and deadlines

Launch a fixed V-owned worker through an argument vector with `shell=False`.
The JSON definition is data: allowlisted workload/engine/model identifiers,
local input references, device selection, positive finite budgets and deadlines.
Reject arbitrary executables, shell strings, Python imports, scripts, environment
overrides and arbitrary systemd properties. Resolve data paths with the existing
privacy and traversal rules; model files never supply executable code.

Apply affinity and `RLIMIT_AS` in the new interpreter's minimal bootstrap,
before heavy imports and threads, then enter the known workload. Do not use
`preexec_fn` or temporarily limit the parent around spawn: V has threads and
Python warns that such callbacks can deadlock before exec. POSIX process-group
isolation uses supported `Popen` options such as `start_new_session=True`.
See Python's [subprocess contract](https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen).

For the systemd backend, generate the scope name and argv internally. Detect
support for `--expand-environment=no` and disable argument expansion; otherwise
declare this backend unavailable. A shell-free argv alone does not disable
systemd's variable expansion. See upstream
[`systemd-run` documentation](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd-run.xml).

The outer launcher uses `stdin=DEVNULL`. A worker protocol that needs input,
such as the existing TTS protocol, may use a bounded pipe whose writer closes it;
it never inherits an interactive terminal. Drain output without unbounded buffers
or pipe deadlocks. Readiness and wall-clock deadlines cover setup, loading,
inference and teardown; use a monotonic clock and bounded waits. Input audio
duration is metadata, not the execution timeout.

Cancellation and timeout stop only the experiment tree: request termination,
allow a bounded grace, escalate to kill, reap children and close pipes. With
systemd, target the generated experiment scope, not just the `systemd-run`
launcher PID. Without it, the adapter must demonstrate descendant cleanup for
the selected platform; terminating one PID does not establish tree cleanup.
Release any held compute slot in all outcomes. Distinguish cancellation,
timeout, unavailable limit, worker failure and evidenced resource exhaustion
through stable, path-free outcomes. Partial measurements remain explicitly
partial; they never become a successful complete benchmark.

### 4. Child device and resource observations

Select CPU or a supported accelerator explicitly for the child. Pass validated
runtime/thread settings and device visibility only in the child's configuration
or environment. Do not modify the supervisor's environment, GPU power/clock
settings, drivers or host scheduler policy. Thread counts and affinity are
different controls; record both. Fail an unavailable device request rather than
silently changing device or precision.

Record requested and observed device identity, host CPU/architecture and OS,
runtime versions, engine/model provenance, precision, effective affinity and
memory/quota controls. Unknown observations remain unknown. CPU/address-space
limits do not bound GPU memory or accelerator compute, and visibility settings
are not a security sandbox. Record the device and sampling scope of GPU metrics
so other GPU workloads cannot be mistaken for experiment-only usage.

### 5. Measured results and estimates are separate

The planned Edge Lab JSON envelope separates `measured` from `estimated`.
`measured` contains observations from that run, with units, collection method,
scope and completion status. A requested budget is configuration, not measured
usage. `estimated` contains only labeled calculations with inputs, assumptions
and method; it may be empty. Missing measurements are null/unavailable with a
reason, never fabricated zeros or silently replaced by estimates.

STT reuses the behavior of [the existing bench CLI](../../src/voz/interfaces/cli/bench.py)
and [evaluation functions](../../src/voz/application/evaluation.py). Its current
`schema_version: 1` output remains unchanged; Edge Lab wraps or maps that report
without claiming the current CLI already emits the new envelope.

| Measurement | Required interpretation |
| --- | --- |
| STT time and RTF | Per-clip wall time; RTF = compute seconds / input audio seconds. Corpus totals sum durations. |
| Load time | Current `bench` warm-up forces loading with one second of silent inference; it is not pure model-load time. whisper.cpp reloads on each invocation. |
| WER/CER | Existing normalization and corpus edit totals; absent references mean unavailable accuracy, not zero error. |
| Peak RAM | Current `bench` uses process peak RSS, or completed-child accounting for whisper.cpp. It includes interpreter/libraries; child accounting is not a simultaneous sum of tree RSS. Keep RSS, address-space limit and cgroup usage distinct. |
| VRAM | Current NVIDIA sampling every 0.2 seconds is device-wide on the first GPU, with baseline/delta; sampled peaks can miss shorter spikes. Do not label it child-only memory or apply it to another selected GPU. |
| TTS latency and throughput (planned) | Time to first usable audio from request start, with loading/chunking stated; output audio seconds / compute wall seconds. Complete-chunk output is not evidence of sample streaming. Record peak memory with its actual collection scope. |

Windows child-memory accounting currently returns `0.0` for whisper.cpp; Edge
Lab must mark that value unavailable rather than describe it as measured zero
usage. Record actual input duration, repetition count and cache/warm-up policy.
A single run supplies no measured variance, and synthetic clips do not establish
accuracy on real conversations. Constrained PC results remain PC results;
SBC compatibility and performance require measurements on the actual board.

Definitions, datasets, raw outputs and diagnostics live outside the checkout
under private runtime storage. Public reports omit recordings, input text,
secrets and absolute host paths; publication is separate from experiment execution.

## Positive consequences

- A failed or cancelled experiment does not leave limits on normal V work.
- Standard-library controls cover the basic process boundary; systemd remains
  optional and explicitly activated.
- Results retain their provenance and metric meanings without suggesting SBC
  equivalence or untested platform support.

## Costs and portability limits

| Platform | Planned boundary, subject to tests |
| --- | --- |
| Linux | Affinity and `RLIMIT_AS` where exposed and permitted. Optional user scopes require functional controllers and effective-property verification. Containers or inherited restrictions can prevent a requested profile. |
| Other POSIX systems, including macOS | `resource` availability does not guarantee every limit exists or is enforced identically. Linux scheduler APIs and systemd scopes are not portable. Reject unsupported requested controls; do not advertise Linux-equivalent enforcement. |
| Windows | Python `resource` and these scheduler APIs are unavailable; no systemd backend. Equivalent hard limits and tree cleanup would need a separately implemented and tested native adapter. No constrained Windows support is established here. |

Limits do not reserve resources, prevent thermal throttling or isolate shared
storage/GPU contention. Per-process address-space limits cannot provide an
aggregate memory budget without a verified group mechanism. This is resource
containment for trusted installed engines, not an untrusted-code sandbox.

## Alternatives considered

| Alternative | Reason for rejection |
| --- | --- |
| Apply limits to V or the login session | Restricts normal jobs or unrelated applications and survives the experiment boundary. |
| Require systemd or change system configuration | Breaks portability and the explicit, optional scope policy. |
| Use thread counts as CPU quotas or `RLIMIT_AS` as physical RAM | Conflates different controls and produces misleading results. |
| Use a threaded parent's `preexec_fn` | Can deadlock before execution; a fresh worker bootstrap provides the boundary. |
| Execute commands from experiment JSON | Adds an arbitrary-code interface unrelated to benchmarking registered engines. |
| Translate a desktop budget into SBC performance/support | CPU architecture, memory, thermals and runtime behavior have not been reproduced. |

## Current evidence (2026-10-15)

These are existing contracts and precedents, not proof of Edge Lab enforcement:

| Existing behavior | Source |
| --- | --- |
| STT schema, timing, memory, provenance and dataset validation | [bench CLI](../../src/voz/interfaces/cli/bench.py), [bench tests](../../tests/unit/test_bench_cli.py), [metric documentation](../benchmarks.md) |
| Child-process TTS, pipe protocol, cancellation and timeout | [subprocess provider](../../src/voz/infrastructure/tts/subprocess_provider.py), [protocol](../../src/voz/infrastructure/tts/protocol.py), [provider tests](../../tests/unit/infrastructure/tts/test_subprocess_provider.py) |
| Compute admission within one supervisor process | [compute slot](../../src/voz/application/compute_slot.py), [slot tests](../../tests/unit/application/test_compute_slot.py) |

The Edge Lab executor, definition schema, envelope and platform-specific
enforcement tests are **planned**. This ADR establishes no new runtime capability
or hardware benchmark result.

## Verification

Implementation must demonstrate, using synthetic inputs and disposable children:

- Parent affinity, limits and environment remain unchanged after success,
  setup failure, timeout and cancellation; unrelated processes are untouched.
- Effective limits are established before inference. Unsupported controls fail
  safely, and systemd is never invoked without explicit activation.
- JSON cannot select executable code or inject shell/systemd options. Missing
  models and runtimes do not trigger installation or network access.
- Hangs, broken pipes, partial output and descendant processes are cleaned up
  within bounded waits; outcomes and partial measurements remain distinguishable.
- STT retains the documented `bench` semantics and schema. Estimates never
  populate missing measurements; unsupported memory/GPU observations stay unavailable.
- Each claimed OS/control/device combination has an exercised test and recorded
  environment. SBC claims additionally require runs on the actual SBC.

Revisit this decision if an engine cannot preserve inherited limits, a native
Windows adapter is introduced, or stronger aggregate resource isolation is needed.
