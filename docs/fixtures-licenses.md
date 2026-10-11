# Test fixture licenses

This document inventories every fixture file present in `tests/fixtures/` as of
this edition, its provenance and its license. It serves as the public record for
S16.17 of the [roadmap](../ROADMAP.md).

Only what can be verified directly in the repository is documented (existing
files, their provenance README and the tests that consume them). When a fact
cannot be verified from the repository, this document marks it explicitly as
"provenance to be confirmed" instead of assuming it.

## Inventory

As of this edition, `tests/fixtures/` contains two sets of fixtures:
`tests/fixtures/media/` (binary audio, described in detail in
[`tests/fixtures/README.md`](../tests/fixtures/README.md), which is the
authoritative source for it) and `tests/fixtures/whisper_cpp/` (text fixtures for
the whisper.cpp adapter, described below). This document summarizes them and does
not replace that file.

### `tests/fixtures/media/` — synthetic 440 Hz tone

The six files in this directory contain the same mathematical 440 Hz sine wave,
0.25 seconds, one channel, generated at 16 kHz. They contain no speech, personal
data or third-party recordings.

| File | Format | Audio codec | Bytes |
| --- | --- | --- | ---: |
| `synthetic-tone.wav` | WAV | `pcm_s16le` | 8,044 |
| `synthetic-tone.mp3` | MP3 | `mp3` (libmp3lame) | 1,296 |
| `synthetic-tone.m4a` | M4A | `aac` | 2,290 |
| `synthetic-tone.ogg` | OGG | `vorbis` | 3,622 |
| `synthetic-tone.opus` | OGG | `opus` | 867 |
| `synthetic-tone.webm` | WebM | `opus` | 1,264 |

SHA-256 of each file (integrity manifest):

| File | SHA-256 |
| --- | --- |
| `synthetic-tone.wav` | `d959e7258ec4ad502f79a133bee06ccfcd2eac7e7c4ef5040c4829f8c29915ee` |
| `synthetic-tone.mp3` | `8ca7afa2af2e68dde5d8a97abb6a86aef7bc210b040763835cd28df7d5ab0b7d` |
| `synthetic-tone.m4a` | `860592365328e72edc49fb5930b76246437fd121efc78a9fc421bd927217fab3` |
| `synthetic-tone.ogg` | `d9d96e65b0fb292a53868f6a412dcc4ade47e30586bae10822802263823017fd` |
| `synthetic-tone.opus` | `3255e94afd95eb8fd68d7072a8d4386db400cd0b776f8d55428a4746227186f7` |
| `synthetic-tone.webm` | `b673d57f775551995b9d7519c4c0d31372567e5b6c25ce70abbdc69c517cd063` |

**How they were generated:** with FFmpeg 8.1.2, from the `lavfi` source
`sine=frequency=440:sample_rate=16000:duration=0.25`, using `+bitexact` and
metadata stripping so the build is reproducible with the same FFmpeg version. The
exact commands used for each format are documented in
[`tests/fixtures/README.md`](../tests/fixtures/README.md#provenance-and-license).
For `.opus` and `.webm`, Opus decodes at its fixed 48 kHz codec clock even though
the source was generated at 16 kHz; this is the expected behavior of the codec,
not a generation error.

**License:** original test data by the V contributors, generated locally with
FFmpeg's `sine` tool. No external media was downloaded or adapted. They are
distributed under the same [MIT license](../LICENSE) as the repository.

**Use in tests:** the manifest of sizes and hashes is verified automatically in
[`test_media_fixtures.py`][test-media-fixtures], which also checks with a real
`ffprobe` that each file exposes the expected container and codec. Other tests
that consume these fixtures include:

- `tests/contract/test_media_probe_port.py`
- `tests/integration/application/test_import_media_sqlite.py`
- `tests/integration/application/test_normalize_imported_media.py`
- `tests/integration/audio/test_ffmpeg_media_normalizer_integration.py`
- `tests/integration/audio/test_ffprobe_media_probe.py`
- `tests/integration/test_media_upload_api.py`

[test-media-fixtures]: ../tests/integration/media/test_media_fixtures.py

### `tests/fixtures/whisper_cpp/` — whisper.cpp adapter fixtures

| File | What it is | Provenance and license |
| --- | --- | --- |
| `fake_whisper_cli.py` | A stdlib-only stand-in for the `whisper-cli` executable, steered through `FAKE_WCPP_*` environment variables | Original test code by the V contributors, MIT like the repository |
| `real_ojf_v1.9.4.json` | An excerpt of the real `--output-json-full` output of `whisper-cli` built from whisper.cpp tag v1.9.4 (CPU-only build), used to check that `WhisperCppProvider` maps the real format to segments and words | Output of MIT-licensed software run locally on 2026-09-30; machine-specific fields are redacted in the file (`systeminfo`, `params.model`). The transcribed text is model output on a synthetic clip. The exact source clip is not recorded in the repository (the benchmark audio of [benchmarks.md](benchmarks.md) was synthetic `espeak-ng` speech): **provenance of the audio to be confirmed** |

They are checked by
`tests/unit/infrastructure/asr/test_whisper_cpp_real_format.py` and the adapter
tests; see [whisper-cpp.md](whisper-cpp.md).

## Fixtures outside `tests/fixtures/`

No other fixture directories were found in `tests/` as of this edition (searched
by file name and by references to `fixtures/` from the test code).
If a future roadmap section adds more fixtures (for example audio with synthetic
speech for diarization or alignment), this document must be updated in the same
edit that adds them, following the same format: name, format, how it was
generated and license. Until then, any new fixture that does not appear here has
**provenance to be confirmed**.

## Rule for new fixtures

According to [AGENTS.md](../AGENTS.md) and [CONTRIBUTING.md](../CONTRIBUTING.md),
private recordings must not be used as test fixtures. A new audio/video fixture
must:

- be generated synthetically and reproducibly (for example with
  `ffmpeg -f lavfi`), or come from a source whose license explicitly allows
  redistribution in an MIT repository;
- be documented in this file with its provenance, generation command and license,
  before or in the same edit that adds it to the repository;
- if its source license is neither MIT nor public domain, this document must state
  the exact license and any required attribution, and that attribution must also
  be reflected in `NOTICE`.
