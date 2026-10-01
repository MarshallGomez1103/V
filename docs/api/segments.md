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
  "quality": {"flags": ["low_confidence"], "avg_logprob": -1.3},
  "words": [{"start_ms": 0, "end_ms": 120, "text": "Hola,", "speaker_id": "uuid | null"}]
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

`words[].speaker_id` (S7.05) es el hablante de la palabra: el del turno acústico
que contiene su punto medio (`start <= (start_ms+end_ms)/2 < end`; con turnos
solapados gana el que empieza antes); si ningún turno la cubre, hereda el
`speaker_id` del segmento (puede ser `null`). Se calcula al vuelo en la vista
(`application/word_speakers.py`), sin columna nueva en `words`: no hay
persistencia que migrar ni que mantener idempotente. Mientras el endpoint de
listado no entregue los turnos a `segment_view`, todas las palabras heredan el
hablante del segmento.

## Calidad del segmento (S13.04, S13.05, S13.12)

`quality.flags` son pistas **no destructivas** calculadas al persistir la
transcripción (`application/quality_flags.py`, función pura) a partir de las
métricas que reporta el motor (hoy solo faster-whisper; whisper.cpp y los
proveedores cloud no las dan, así que sus segmentos salen sin flags salvo los
que no necesitan métricas). `quality.avg_logprob` es `null` si el motor no la
dio. Los flags tienen orden estable y códigos estables:

| Flag | Cuándo |
| --- | --- |
| `repetition` | `compression_ratio > 2.4`, o un n-grama (1 a 4 palabras) repetido seguido: una palabra 5 o más veces, una frase 3 o más |
| `silence_hallucination` | `no_speech_prob > 0.6` y `avg_logprob < -1.0`; o una frase típica de alucinación ("Thank you.", "Gracias por ver el video", "Suscríbete"...) con `no_speech_prob > 0.3` o fuera de los límites del audio |
| `out_of_bounds` | el motor devolvió un tramo más allá del audio que recibió (tolerancia 500 ms); el tramo se recorta al guardar, pero se marca |
| `low_confidence` | `avg_logprob < -1.0` (umbral de Whisper) |

Ejemplo real: Whisper sobre un tono sin voz devolvió `" Thank you."` con
`end = 29,98 s` en un clip de 0,25 s: se marca `out_of_bounds` y
`silence_hallucination`.

**Ningún postproceso reescribe texto (S13.12).** `text` es el ASR literal
(sin espacios extremos) hasta que el usuario lo edita; los flags se guardan
aparte (columna `segments.quality_json`) y no cambian, borran ni "corrigen"
texto. Las ediciones del usuario son la única vía de cambiar lo que dice una
transcripción, y conservan el literal en `original_text`. Editar un segmento no
recalcula ni borra sus flags. El cálculo es idempotente: reanudar un job tras
un fallo solo añade los segmentos que faltan.

Flujo de revisión (S13.06): `ReviewQueue` (frontend) lista los segmentos con
flags, filtra por tipo y permite marcarlos como revisados. Ese estado es local a
la sesión (no se persiste; recargar la página lo reinicia).

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

Migración `0006_segment_quality`: columna `quality_json` (Text, nullable) en
`segments`, con `ALTER TABLE ADD COLUMN` (sin recrear la tabla, para no
arrastrar `words` como habría pasado en 0004). Contiene
`{"flags": [...], "avg_logprob": x}` o `NULL` si no hay nada que señalar; los
segmentos existentes quedan sin flags. Downgrade elimina la columna (las pistas
se pueden recalcular) y conserva texto, ediciones y palabras. Un JSON dañado se
lee como "sin pistas", nunca como error.
