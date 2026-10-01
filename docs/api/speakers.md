# Hablantes — S6.09, S6.10, S6.11, S6.12 (oleada 5b, 2026-09-30)

Local (`127.0.0.1`), sin red ni modelos: todas estas operaciones editan filas
existentes, nunca reejecutan la diarización. Los errores usan
`{"detail": {"code", "message"}}`; nunca rutas del host ni tracebacks.

## Item de hablante

```json
{"id": "uuid", "name": "Ana", "color": "#4e79a7", "segment_count": 12}
```

`color` es `#rrggbb` en minúsculas. `segment_count` cuenta los segmentos que hoy
apuntan al hablante. Un hablante "pertenece" a una transcripción si alguno de
sus segmentos o turnos (`speaker_turns`) pertenece a ella.

## `GET /api/transcripts/{transcript_id}/speakers`

→ `200 {"speakers": [item]}` en orden de creación (el orden de primera aparición
del audio). `404 transcript_not_found`.

## `PATCH /api/speakers/{speaker_id}` (S6.09, S6.10)

Body: `{"name"?: str, "color"?: "#rrggbb"}`. El nombre se guarda sin espacios
extremos (1–80 caracteres). Al menos un campo es obligatorio. Nombre y color se
guardan en el hablante, así que sobreviven a nuevas ejecuciones de diarización
sobre la misma transcripción (`AssignSpeakers` reutiliza el hablante).

| Estado | Código | Significado |
| --- | --- | --- |
| 200 | — | item actualizado |
| 404 | `speaker_not_found` | el hablante no existe |
| 422 | `speaker_update_invalid` | nombre vacío o de más de 80 caracteres, color que no es `#rrggbb`, o body sin campos (un body mal formado da el 422 estándar de FastAPI) |

## `POST /api/speakers/{speaker_id}/merge` (S6.11)

Body: `{"into": "<speaker_id destino>"}` → `200 {"speaker": item_destino}`.

En **una transacción** SQLite reasigna al destino todos los segmentos y turnos
del origen y borra el origen. Textos, revisiones y timings no cambian. El
destino conserva su nombre y color.

| Estado | Código | Significado |
| --- | --- | --- |
| 404 | `speaker_not_found` | el origen no existe |
| 409 | `speaker_merge_invalid` | destino igual al origen, inexistente, o sin ninguna transcripción en común con el origen |

## `PUT /api/segments/{segment_id}/speaker` (S6.12)

Body: `{"speaker_id": "uuid" | null}` → `200` item de segmento (mismo shape que
`docs/api/segments.md`). Solo cambia `speaker_id`: no toca texto, `edited` ni
`revision`. `null` deja el segmento sin hablante.

| Estado | Código | Significado |
| --- | --- | --- |
| 404 | `segment_not_found` | el segmento no existe |
| 409 | `segment_speaker_invalid` | el hablante no existe o no pertenece a la transcripción del segmento |

## Hablantes de proveedores cloud (INTEGRITY-001)

Cuando el proveedor ASR ya etiqueta cada segmento (`speaker`: ElevenLabs con
diarización, OpenAI diarizado) y el trabajo **no** pidió diarización local, el
pipeline crea los hablantes al persistir la transcripción:

- Un `Speaker` por etiqueta, llamado `Hablante 1..N` en orden de primera
  aparición, con el color de la paleta fija. Aparecen en
  `GET .../speakers` y en `segment_count` como cualquier otro hablante.
- El id del hablante deriva de la transcripción y la etiqueta
  (`uuid5(transcript_id, "speaker:<etiqueta>")`): reanudar el trabajo reutiliza
  las mismas filas y conserva nombre/color editados. No se crean turnos
  (`speaker_turns`): el proveedor no los entrega.
- Si hay diarización local pedida, gana la local y las etiquetas cloud se
  ignoran. Segmentos sin etiqueta quedan sin hablante.
- Si crear los hablantes falla, la transcripción se conserva y el código queda
  en `diarization_error_code` de la selección del trabajo.
- Limitación: ElevenLabs reutiliza etiquetas (`speaker_0`) por fragmento de
  audio largo, así que una misma etiqueta en fragmentos distintos se fusiona en
  un hablante. OpenAI prefija la etiqueta con el fragmento (no se fusionan).

## Notas

- Sin transacción común con `AssignSpeakers` (ver su nota `ponytail:`): editar
  hablantes mientras corre una diarización sobre la misma transcripción no está
  soportado.
- Reasignar a mano no crea hablantes nuevos; solo se elige entre los de la
  transcripción (`GET .../speakers`).
