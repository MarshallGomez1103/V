# Local OpenAI-compatible audio endpoints

V exposes a **partial** audio compatibility interface. Requests use installed
local models through the existing audio service. No model is downloaded and no
cloud provider is activated by these endpoints. Use the model IDs returned by
`GET /v1/models`; OpenAI model names are not aliases for local models.

The server binds to loopback by default. Network exposure uses V's server
credentials. Authentication failures retain V's `detail` error envelope rather
than the OpenAI-compatible `error` envelope described below. This interface is
not a complete replacement for the OpenAI API or every SDK feature.

## Supported operations

| Endpoint | Accepted fields | Result |
| --- | --- | --- |
| `GET /v1/models` | No query parameters | `{"object":"list","data":[...]}` |
| `POST /v1/audio/transcriptions` | Multipart `file`, `model`; optional `language`, `prompt`, `response_format` | JSON, plain text or verbose JSON |
| `POST /v1/audio/speech` | JSON `model`, `input`, `voice`; optional `speed`, `response_format` | WAV bytes with `audio/wav` |

Model objects have `id`, `object: "model"`, `created`, `owned_by` and the V
extension `capabilities`. **`created: 0` is an unavailable-timestamp sentinel**,
not the actual installation or creation date. Capabilities identify the
operations available for that local model.

Transcription defaults to `response_format: "json"`, returning only `text`.
`text` returns UTF-8 plain text. `verbose_json` returns `task: "transcribe"`,
`text`, `language`, `duration` in seconds and `segments` containing `id`, `start`,
`end` and `text`. Segment offsets are in seconds. Token IDs, word arrays,
confidence fields and other provider-specific metadata are not fabricated.
Language and prompt are passed to the local service; an engine that cannot honor
a supplied option rejects it.

Speech defaults to `speed: 1.0` and **`response_format: "wav"`**. Only WAV is
supported, unlike OpenAI's default format. Speed must be a finite number between
0.25 and 4; the selected local engine can impose further restrictions. Voice
identifiers are those understood by that engine. Audio is generated before the
response starts; chunked delivery of the finished WAV is not inference streaming.

Unknown parameters and query parameters are rejected with a fixed 400 error.
This includes `stream`, `instructions`, transcription formats such as `srt` or
`vtt`, timestamp options and speech formats such as MP3. Even `stream: false` is
an unsupported parameter. Duplicate JSON keys or multipart fields are rejected.

## Upload and resource boundaries

- The full request body is limited to **26 MiB** (27,262,976 bytes), including
  multipart framing. The file itself must be nonempty and no larger than
  **25 MiB** (26,214,400 bytes). Oversized requests return 413.
- Multipart allows at most 16 parts; each text field is limited to 8 KiB of
  UTF-8. JSON string fields have the same 8 KiB limit. Multipart defects,
  duplicate headers or disposition parameters, nested parts and supplied
  Content-Transfer-Encoding are rejected. Valid UTF-8 filenames are accepted
  despite MIME's non-ASCII header warning.
- A filename must be a Unicode basename of at most 200 characters with a
  supported audio extension:
  `.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`, `.webm`, `.mp4`, `.mpeg`, `.mpga` or
  `.oga`. Paths, colon, controls, unsafe bidi characters, traversal and
  unsupported suffixes are rejected without echoing
  their values. The filename is never used as the stored basename.
- The bounded body is buffered in memory. Standard-library email parsing creates
  additional bounded copies; **26 MiB is an input limit, not a process-memory
  ceiling**. Parsing and local service calls run in the threadpool.
- Uploads use a generated private temporary directory under the configured cache
  root and a generated file with a validated extension (0700 directory and 0600
  file on POSIX). Temporary uploads are removed on success and failure.
- Reception has a 300-second deadline. Execution has a **separate** 300-second
  cancellation deadline; this is not a single end-to-end 300-second budget.
  Client disconnection also sets the service's cooperative cancellation flag.
  The router waits for the service to release the source before deleting it.
  Cancellation is cooperative, not forced thread termination; engine cleanup can
  extend the time before the request handler returns.
- Returned WAV handles are closed after delivery, disconnection or send failure,
  with a response-level `finally` and a background cleanup fallback.

## Stored history

Requests reuse V's persistent projects, imported originals, transcripts and
synthesis history. These records remain after completion, failure, timeout or
disconnection; deleting the temporary upload does not delete imported media.
Manage retained results through the normal library and synthesis controls.

## Errors

Endpoint validation and service failures use:

```json
{
  "error": {
    "message": "Invalid or unsupported request parameter.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_request"
  }
}
```

Messages and codes are fixed, without request values, host paths or tracebacks.
`param` is a supported field name when available. Server failures use
`type: "server_error"` and a fixed safe message. The HTTP deadline returns 408; a service processing deadline can return 504.
A detected client disconnection uses 499 if a response can still be delivered.
Server middleware errors, notably authentication failures, are outside this
partial error compatibility contract.

## References

The supported subset follows the shapes of the official
[transcription endpoint](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create),
[speech endpoint](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)
and [model list endpoint](https://developers.openai.com/api/reference/resources/models/methods/list).
Additional options in those APIs are not implicitly supported by V.
