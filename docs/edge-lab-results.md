# Comparing Edge Lab results

`v lab compare` reads one or more version-one JSON envelopes emitted by
[`v lab run`](edge-lab.md) and writes a Markdown table to standard output:

```bash
v lab compare "$XDG_DATA_HOME/voz/experiments/stt.json" "$XDG_DATA_HOME/voz/experiments/tts.json"
```

Use private report files outside the source checkout. Each file is limited to
1 MiB (1,048,576 bytes); directories, FIFOs and files resolving inside the checkout
are refused. The command reads saved results only: it does not run inference,
load models, install dependencies, download data or contact providers.

Rows preserve argument order. Exit status **0** means that all reports were valid
and the table was rendered; it does not mean every experiment succeeded. Failed,
cancelled and timed-out experiments retain their status. Invalid, unreadable,
oversized or unsupported-version reports produce exit status **2**, a fixed
path-free error on standard error, and no partial table.
Reports with a failed, cancelled or timed-out status must have an empty
`measured` object; measurements attached to these statuses make the report invalid.

## Columns and missing observations

| Column | Interpretation |
| --- | --- |
| Status | Original envelope status: completed, failed, cancelled or timed_out. |
| Model (engine) | Observed model identifier and engine, when available. |
| Device (effective) | Confirmed worker device, without falling back to the requested device. |
| CPU mask (effective) | Observed logical CPU IDs, not physical cores or a CPU time quota. |
| AS soft / hard (bytes, effective) | Observed per-process virtual address-space limits, not physical RAM usage or a tree-wide budget. |
| STT RTF | Measured corpus wall seconds divided by input audio seconds. |
| STT WER | Measured word error ratio; absent references leave it unavailable. Values may exceed one. |
| TTS first chunk (s) | Time from the first synthesis call until the first completed audio chunk returns. Preparation is excluded; loading inside synthesis is included. This is not time to the first streamed sample. |
| TTS throughput (audio s / wall s) | Rendered audio duration divided by synthesis wall time, including provider teardown. |
| STT peak RSS (MiB; scope) | Existing bench peak with its reported worker or largest completed-child scope. Unrecognized methods are labeled unknown scope. |
| TTS worker peak RSS (MiB) | Lifetime worker-process RSS peak, including interpreter and preparation. |
| TTS largest child peak RSS (MiB) | Largest completed-child RSS peak, including provider preparation children where accounted. |

Missing or null observations appear as **—**. A measured zero remains **0**.
The table uses only `measured`, selected model observations and effective
constraints; `estimated` never substitutes for a missing measurement. Null
address-space bounds are displayed as —, including the current producer's
representation of unlimited bounds; the table does not distinguish unlimited
from unobserved bounds. Requested limits are not evidence of enforcement.

Numbers must be finite; displayed metrics must be nonnegative numeric values,
not booleans or numeric strings. Numeric cells use six significant digits;
effective address-space bytes remain exact integers. Duplicate JSON keys,
inconsistent status/error codes and malformed envelopes are rejected.

RSS scopes remain separate. Peaks are neither summed nor interpreted as a
simultaneous process-tree total. See the
[benchmark metric definitions](edge-lab-benchmarks.md) for collection boundaries.

## Privacy and interpretation limits

Only selected columns are rendered. Input text, command fields, model source
paths, filenames, raw messages and arbitrary observation fields are omitted.
Model labels containing path separators or beginning with `~` are withheld as —,
including relative paths and namespace identifiers containing `/`. Markdown
metacharacters are escaped, HTML is encoded, and line breaks and control
characters in labels become spaces. Review even these selected identifiers
before publishing a table: a model identifier can itself contain private text.

Reports are validated data, not authenticated evidence that inference ran.
Synthetic tests validate parsing and presentation; they provide no hardware
benchmark, accuracy, performance or platform-support claim. Tables do not rank
models, normalize datasets, account for contention, establish variance or infer
ARM equivalence. Compare the original runtime, input, warm-up and hardware
observations before interpreting results. Resource boundaries and portability
limits remain those of [ADR-0011](adr/0011-edge-lab.md).
