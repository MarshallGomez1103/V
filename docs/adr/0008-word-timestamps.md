# ADR-0008: Timestamps de palabra nativos de Faster Whisper, sin WhisperX

- Estado: Aceptada
- Fecha: 2026-09-30
- Responsables: mantenedores de VOZ
- Alcance: origen, modelo y persistencia de los timings de palabra (S7.01, S7.03,
  S7.04, S7.08); S7.02 (evaluar WhisperX) **queda abierto y no evaluado**
- Relacionadas: [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (chunks y
  checkpoints), [ADR-0005](0005-transcription-providers.md) (port de providers),
  [ADR-0006](0006-local-first-privacy.md) (sin cloud implícito)

## Contexto

El dominio ya tiene `Word` (`start_ms < end_ms`, dentro del segmento) y SQLite ya
guarda `words`, pero el ASR se invocaba con `word_timestamps=False`. Hacen falta
timings de palabra para la reconciliación con hablantes (S6) y para resaltar y
navegar por palabra. El plan maestro (sección 4.3) contempla WhisperX
(forced alignment con wav2vec2), que añade torch, modelos por idioma y un segundo
paso de inferencia.

## Decisión

1. **Nativo.** El adapter de Faster Whisper pide `word_timestamps=True`
   (alineamiento por atención cruzada/DTW que ya trae el motor). **WhisperX no se
   instala** ni es dependencia: cero dependencias nuevas, cero modelos extra.
2. **Tipos canónicos.** `TranscriptionSegment.words: tuple[TranscriptionWord, ...] = ()`
   con `TranscriptionWord(start_ms, end_ms, text, probability | None)`.
   `TranscriptionOptions.word_timestamps` (por defecto `True`) lo controla. El
   texto del segmento sigue siendo el literal del ASR; las palabras son solo una
   pista de timing.
3. **Mismo offset y propiedad que el segmento.** `globalize_chunk_result` suma
   `process_start_ms` a segmento y palabras; `owned_chunk_segments` decide por el
   punto medio del segmento y recorta las palabras a la región poseída
   (`clamp_words`). Las palabras heredan la propiedad de su segmento: el solape
   entre chunks no duplica palabras.
4. **`clamp_words`** deja las palabras ordenadas, sin solapes, no negativas y
   dentro de los límites; descarta las que quedan sin duración (el dominio exige
   `start_ms < end_ms`). Perder una palabra nunca cambia el texto del segmento.
5. **Checkpoints** serializan `words` en el JSON del segmento solo cuando las hay;
   los checkpoints anteriores (sin la clave) se leen como `words=()`. No hay
   migración de esquema.
6. **JobRunner** persiste `Word` con id `uuid5(segment_id, "word:{i}")`. El segmento
   y sus palabras se insertan en una sola transacción y los segmentos ya
   guardados se saltan, así que reanudar o repetir la persistencia es idempotente.
   Aplica la misma regla de strip que el texto: palabras vacías tras `strip()` se
   descartan.
7. **Fallback (S7.08).** Si el paso de palabras falla en el motor (excepción que no
   es cancelación ni audio inválido), el adapter reintenta el chunk una vez sin
   palabras. Un modelo o motor sin palabras produce `words=()` y el job completa
   igual. Los checkpoints que ya existen no se recalculan.
8. **API.** `GET /api/transcripts/{id}/segments` añade `words` a cada segmento
   (`segment_view`, compartido con `PUT /api/segments/{id}`). Un segmento editado
   expone `words: []` porque el timing describe el texto ASR, no la corrección
   (los datos se conservan). Ver [docs/api/segments.md](../api/segments.md).
9. **Aligner futuro (S7.01).** `AlignmentProvider` en
   `application/ports/alignment.py` solo fija la costura
   (`align(audio, segments, language, cancellation) -> palabras por segmento`).
   No tiene implementación ni registry: AGENTS.md prohíbe un framework de plugins
   antes de dos providers reales. Hoy las palabras vienen del ASR cuando declara
   `ModelCapability.WORD_TIMESTAMPS`.

## Consecuencias positivas

- Timings de palabra sin dependencias, sin descargas y sin segundo modelo; sigue
  siendo offline.
- Los chunks recuperables, la cancelación y la idempotencia se conservan: las
  palabras viajan dentro de los mismos checkpoints y segmentos.
- El fallo de palabras no hace fallar el job.

## Costes y límites

- El DTW nativo es menos preciso que un forced alignment dedicado (suele bastar
  para resaltado y reconciliación de hablantes, no para subtitulado de fotograma).
  No medimos aún esa precisión con audio real.
- Pedir palabras cuesta tiempo de inferencia extra por chunk (no medido aquí).
- La `probability` de palabra se guarda en checkpoints, pero el dominio `Word` y la
  API no la exponen todavía.
- Editar el texto de un segmento no reajusta los timings; quedan ocultos.
- La capability `WORD_TIMESTAMPS` la anuncia cada catálogo/runtime; el adapter de
  Faster Whisper ya puede producirla, pero el probe de runtime aún no la declara
  (pendiente del dueño de `infrastructure/asr/options.py`).

## Alternativas consideradas

- **WhisperX / forced alignment.** Mayor precisión, pero torch, modelos wav2vec2 por
  idioma y un segundo pase. **S7.02 sigue abierto: no se evaluó**; se reabre si la
  precisión nativa resulta insuficiente con audio real.
- **Alinear después con un proceso aparte.** Es lo que reserva `AlignmentProvider`;
  no se construye hasta que exista un segundo proveedor real.

## Evidencia actual

- `src/voz/application/ports/transcription.py`, `ports/alignment.py`,
  `chunked_transcription.py`, `job_runner.py`,
  `infrastructure/asr/faster_whisper.py`,
  `infrastructure/persistence/transcription_checkpoints.py`,
  `interfaces/api/segments.py`.
- Tests: `tests/unit/application/test_word_timestamps.py`,
  `tests/unit/infrastructure/asr/test_faster_whisper_words.py`,
  `tests/integration/application/test_job_runner.py` (palabras, reanudación sin
  duplicar), `tests/integration/application/test_recoverable_transcription.py`
  (round-trip y checkpoints antiguos), `tests/integration/test_segments_api.py`,
  `tests/integration/test_jobs_api.py`.
- La prueba con modelo real (`test_faster_whisper_real_opt_in.py`) es opt-in y no
  se ejecutó en esta pasada.

## Verificación

`uv run pytest -q`, `uv run ruff check`, `uv run pyright` sobre los archivos
listados. Precisión y costo con audio real: **sin verificar**.
