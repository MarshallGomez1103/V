# Edición de segmentos — S5.12 (oleada 3, 2026-09-30)

Local (`127.0.0.1`), sin red ni proveedores. Los errores usan
`{"detail": {"code", "message"}}`; nunca rutas del host ni tracebacks.

## Item de segmento (contrato compartido con el frontend)

Es el mismo shape en `GET /api/transcripts/{transcript_id}/segments`
(`{"segments": [item]}`) y en la respuesta de la edición:

```json
{
  "id": "uuid", "start_ms": 0, "end_ms": 250, "text": "Hola, mundo.",
  "edited": true, "revision": 1, "speaker_id": "uuid | null",
  "words": [{"start_ms": 0, "end_ms": 120, "text": "Hola,"}]
}
```

`edited` es `false` y `revision` es `0` hasta la primera edición; cada edición
correcta suma 1 a `revision`. `speaker_id` es `null` si el segmento no tiene
hablante asignado.

`words` (S7.04) son los timings de palabra del ASR dentro del segmento: ordenados,
sin solapes, en milisegundos y con `start_ms < end_ms` dentro de
`[start_ms, end_ms]` del segmento; `text` va sin espacios extremos. Es `[]` cuando
el modelo no entregó palabras (fallback S7.08: el job completa igual, solo sin
timing de palabra) y **siempre `[]` si el segmento está editado (`edited: true`)**:
los timings describen el texto ASR original, no el corregido, así que no se
exponen (siguen guardados). La probabilidad de cada palabra se conserva en los
checkpoints pero no se expone.

## `PUT /api/segments/{segment_id}`

Body: `{"text": str, "revision": int}`. `revision` es la que el cliente cargó
(concurrencia optimista). El servidor guarda `text` sin espacios extremos.

| Estado | Código | Significado |
| --- | --- | --- |
| 200 | — | item de segmento actualizado (`edited: true`, `revision + 1`) |
| 404 | `segment_not_found` | el segmento no existe |
| 409 | `segment_revision_conflict` | la revisión enviada no es la guardada; `detail.current` trae el item actual |
| 422 | `segment_text_invalid` | texto vacío tras quitar espacios (un body mal formado también da 422 estándar de FastAPI) |

### Reglas

- **Texto literal preservado.** En la primera edición el texto ASR literal pasa
  a `original_text` (columna interna, no expuesta en el item); las ediciones
  posteriores no lo sobrescriben. Nunca se reemplaza silenciosamente un
  transcript literal.
- **Atomicidad.** La escritura es `UPDATE segments SET … WHERE id = ? AND
  revision = ?`; si otra pestaña editó entre la lectura y la escritura, el
  resultado es 409 (con el estado actual), no una pérdida silenciosa.
- Los timings de palabras (`words`) no se borran al editar el texto del
  segmento, pero la respuesta los oculta (`words: []`) desde la primera edición.
  Guardar un texto idéntico al actual también cuenta como edición.

## Persistencia

Migración `0004_segment_editing`: columnas en `segments` `speaker_id`
(FK `speakers.id`, `ON DELETE SET NULL`), `edited` (bool, default false),
`revision` (int, default 0) y `original_text` (nullable). Los segmentos
existentes quedan como sin editar. Downgrade descarta las columnas (se pierden
ediciones y asignaciones de hablante) pero conserva segmentos y palabras.
