# Perfiles de calidad, glosario y VAD (S13.01-S13.03, S13.11)

Un **perfil** es una receta de decodificación con nombre, versión y parámetros
fijos. El job guarda el perfil completo en su selección, así que repetirlo
usa exactamente lo mismo aunque las recetas incluidas cambien después.

## Perfiles incluidos

Definidos como datos inmutables en `application/quality_profiles.py`
(`QualityProfile`, `domain/entities/quality_profile.py`). Cambiar un valor exige
subir `version`.

| Parámetro | `default` v1 | `academic` v1 |
| --- | --- | --- |
| `beam_size` | 5 | 5 |
| `temperature` (reintentos) | 0,0 0,2 0,4 0,6 0,8 1,0 | 0,0 0,2 0,4 |
| `condition_on_previous_text` | sí | **no** |
| `no_speech_threshold` | 0,6 | 0,6 |
| VAD | apagado | **encendido** (umbral 0,5; voz mínima 250 ms; silencio mínimo 1000 ms; margen 400 ms) |

- `default` son los valores por defecto de Faster Whisper 1.2.1: un job con este
  perfil se comporta como antes de que existieran los perfiles (y como
  `voz bench`).
- `academic` apunta a clases y charlas largas: no arrastrar el texto previo evita
  que una frase alucinada o en bucle contamine la ventana siguiente; menos
  reintentos aleatorios reducen palabras inventadas; el VAD omite silencios y
  ruido. **Estas elecciones salen de lo que documenta la librería, no de una
  medición propia de VOZ**: `academic` figura como "sin medición" hasta que se
  corra `voz bench` con él. No lo vendas como más preciso.

Sin `profile` en la petición se usa `default`. Los jobs previos (columna `NULL`)
siguen con los valores del motor.

## Quién respeta qué

| Motor | Perfil | VAD | Glosario |
| --- | --- | --- | --- |
| Faster Whisper | sí (`beam_size`, `temperature`, `condition_on_previous_text`, `no_speech_threshold`) | sí (`vad_filter` + `vad_parameters`) | sí, vía `hotwords` |
| whisper.cpp | ignorado | ignorado | ignorado |
| Cloud (OpenAI) | ignorado | ignorado | ignorado |
| Cloud con *keyterms* (el proveedor que los admite) | ignorado | ignorado | sí, como `keyterms` |

La UI lo dice junto al selector y al editor. Las excepciones se registran en
`applies_to` (`GET .../glossary`).

### Glosario: `hotwords` y no `initial_prompt`

Faster Whisper ofrece las dos vías. Se usa `hotwords` porque la librería lo
antepone al prompt de **cada** ventana de decodificación, mientras que
`initial_prompt` solo siembra la primera, y además deja libre `initial_prompt`
para otros usos. Los términos se unen con `", "`. La librería trunca por su
cuenta si exceden la mitad del contexto, así que listas muy largas pierden los
últimos términos: pon primero los más importantes. `hotwords` no tiene efecto si
se usa `prefix` (VOZ no lo usa). Para proveedores cloud con *keyterms* se envía
cada término como campo aparte (se suma a los que el proveedor ya tuviera,
respetando su límite de 100 × 50 caracteres; si se supera, el job falla con un
error tipado, nunca se recorta en silencio). **El texto transcrito nunca se
reescribe con el glosario**: solo se sesga al motor y el resultado se guarda
literal.

Privacidad: el glosario viaja a un proveedor cloud solo si el usuario eligió
explícitamente ese proveedor (mismo consentimiento que el audio).

### VAD

`vad_filter`/`vad_parameters` salen del perfil (`vad = null` lo apaga). Faster
Whisper **ignora el VAD cuando se pasan `clip_timestamps` explícitos**; VOZ
transcribe cada chunk ya recortado con `clip_timestamps="0"`, así que el VAD sí
se aplica. El modelo Silero VAD viene dentro del paquete `faster-whisper`: no
descarga nada.

## Reproducibilidad

`transcription_job_selections.profile_json` guarda el perfil completo (nombre,
versión, parámetros y VAD) y `glossary_json` los términos congelados al crear el
job (migración `0007_project_glossary`). La selección es inmutable, y la
reanudación tras un reinicio reconstruye la petición desde ella.
`GET /api/jobs/{id}` expone `selection.quality_profile` y `selection.glossary`.

## Recomendación por idioma (S13.11)

`recommend_profile(language)` es una función pura. Solo usa la tabla
`MEASUREMENTS` de `application/quality_profiles.py`, cuyas filas son números que
existen en `docs/benchmarks.md`. Regla: entre los perfiles **medidos** para el
idioma (etiqueta regional reducida a la primaria: `es-CO` → `es`) elige el de
menor WER; si no hay ninguna fila, responde `measured: false` y
"sin medición para el idioma «xx»" (o "sin medición: elige un idioma" si no hay
idioma), sin recomendar nada. `unmeasured_profiles` lista los perfiles sin
medición para ese idioma.

Estado actual de las mediciones:

| Idioma | Perfil | WER | Origen |
| --- | --- | --- | --- |
| `es` | `default` | 1,66 % | `docs/benchmarks.md`, 2026-09-30, Faster Whisper turbo CUDA float16, 6 clips de ~36 s |

Limitaciones que la API repite en `evidence`/`synthetic`: el audio fue
**sintético** (espeak-ng), así que el WER es optimista y orientativo; solo se
midió el perfil `default` (la decodificación por defecto) y solo español.
`academic` no tiene medición en ningún idioma. Para añadir una fila: correr
`voz bench` con el perfil y el idioma, copiar el WER a `MEASUREMENTS` con su
procedencia y actualizar esta tabla; nunca estimar.
