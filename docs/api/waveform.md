# Waveform — S5.09 and S5.14

Precomputed peaks to draw the waveform in the browser. Local (`127.0.0.1`), no
network or cloud providers. Errors use `{"detail": {"code", "message"}}`; host
paths are never returned. Common rules: [README.md](README.md).

## `GET /api/media/{media_asset_id}/peaks?buckets=2000`

- `buckets`: integer between **100 and 20000** (default 2000).
- 200 response:

```json
{
  "media_asset_id": "uuid",
  "duration_ms": 61234,
  "buckets": 2000,
  "peaks": [[-0.412, 0.398], [-0.05, 0.07]]
}
```

`peaks` has exactly `buckets` `[min, max]` pairs in time order, normalized so the
loudest sample is ±1 and rounded to 3 decimals. Silent audio returns all
`[0.0, 0.0]`. `duration_ms` is the asset's probed duration (or the decoded one if
it were missing).

| Status | `code` | When |
| --- | --- | --- |
| 404 | `media_asset_not_found` | The asset does not exist |
| 422 | `peaks_buckets_invalid` | `buckets` is not an integer or is outside 100–20000 |
| 500 | `waveform_unavailable` | FFmpeg missing, unreadable media, or no decodable audio |

## Computation

- Source: the normalized derivative (`*.inference.wav`) if it exists; otherwise
  the immutable original. It is opened by descriptor, without exposing paths.
- FFmpeg decodes through a pipe to mono 8 kHz s16le PCM and the adapter consumes
  it as a stream (64 KiB blocks). Memory is O(`buckets`): min/max blocks are
  merged in pairs when they exceed `2 * buckets` and resampled to exactly
  `buckets` at the end. One hour of audio takes ~1 s and ~70 MB of RSS in total
  (Python process included).
- The route is synchronous (`def`), so FastAPI runs it in its threadpool. A
  watchdog kills FFmpeg if it exceeds 600 s.

## Cache

`<XDG_CACHE_HOME>/voz/waveforms/v1-<sha256 of the media>-<buckets>.json`, with
`{"duration_ms", "peaks"}`. Atomic write (temporary file + `os.replace`); a
corrupt file or one with another shape is ignored and rewritten. A failure to
write the cache does not break the request. Because the key is content-based, the
same audio re-imported reuses the peaks.

## Frontend

`Waveform` (`apps/web/src/components/Waveform.tsx`) requests `?buckets=4000` with
an `AbortController`, draws only the visible portion on a `<canvas>` (sized with
`devicePixelRatio`) and offers 1x–32x zoom (zoom in/out buttons and a slider),
horizontal scroll, click to seek, and left/right arrows (±5 s) while the waveform
has focus.
