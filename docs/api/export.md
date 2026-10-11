# Transcript export — S10.07, S10.08, S10.14

Local endpoint (`127.0.0.1`); it calls no providers and uses no network. Errors
use `{"detail": {"code": "<snake_code>", "message": "<safe text>"}}`. Common
rules: [README.md](README.md).

```
GET /api/transcripts/{transcript_id}/export?format=txt&timestamps=false&group_by_speaker=false
```

| Parameter | Values | Default |
| --- | --- | --- |
| `format` | `txt`, `markdown`, `srt`, `vtt`, `json` | `txt` |
| `timestamps` | `true`/`false` | `false` |
| `group_by_speaker` | `true`/`false` | `false` |

## 200 response

The body is the UTF-8 document. Headers:

| `format` | `Content-Type` | Extension |
| --- | --- | --- |
| `txt` | `text/plain; charset=utf-8` | `.txt` |
| `markdown` | `text/markdown; charset=utf-8` | `.md` |
| `srt` | `application/x-subrip; charset=utf-8` | `.srt` |
| `vtt` | `text/vtt; charset=utf-8` | `.vtt` |
| `json` | `application/json` | `.json` |

- `Content-Disposition: attachment; filename="<ascii>"`. If the name contains
  non-ASCII characters, `filename*=UTF-8''<percent-encoded>` (RFC 5987) is added
  and `filename` stays as the ASCII equivalent (without diacritics).
- Base name: the project name (or, if missing, the imported file's name without
  extension), sanitized by `safe_export_filename`: last component only, no
  separators, `..`, control characters or Windows reserved names, at most 100
  characters, fallback `transcript`. It never contains host paths.
- `X-Content-Type-Options: nosniff`.

## The `json` format

`format=json` is the canonical, lossless interchange document: `{"format":
"voz.transcript", "version": 1, "transcript": …, "speakers": […], "segments":
[…]}` with sorted keys, ordered segments and a trailing newline, so equal inputs
produce byte-identical files. The identifier `voz.transcript` v1 is unchanged by
the rename to V, so existing exports stay valid
([ADR-0009](../adr/0009-rename-to-v.md)).

## Options (`txt` and `markdown` only)

- `timestamps=true`: a `[HH:MM:SS.mmm]` prefix per segment (in bold in Markdown:
  `**[HH:MM:SS.mmm]**`). SRT and VTT already include times.
- `group_by_speaker=true`: consecutive segments by the same speaker are grouped
  under their name (`Name:` in TXT, `## Name` in Markdown). A speaker who talks
  again after another one opens a new group. Segments without a speaker (or with
  a speaker that no longer exists) go under the literal label `Sin speaker`
  (emitted as-is by the exporter, regardless of UI language). Speakers are read
  from the project that owns the transcript.

Example of grouped TXT with times:

```
Ana:
[00:00:00.000] Hola, soy Ana

Sin speaker:
[00:00:03.000] sin dueño
```

## Errors

| Status | `code` | When |
| --- | --- | --- |
| 404 | `transcript_not_found` | The transcript does not exist |
| 422 | `export_format_unknown` | `format` is not one of the five |
| 422 | `export_option_unsupported` | `timestamps`/`group_by_speaker` with `srt`, `vtt` or `json` |

A non-boolean value in the options produces FastAPI's standard 422 validation
response. The format is validated before the database is queried.

## Wiring

`create_export_router(ExportTranscript(transcripts, segments, speakers, projects,
media_assets))` in `voz.interfaces.api.export`; use case in
`voz.application.export.service`.
