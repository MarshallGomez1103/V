# Privacidad: ElevenLabs Scribe (opcional, cloud)

Estado: **experimental**. El adapter está probado solo con un transporte falso
(nunca se ha llamado al servicio real), así que no se declara soportado. Sigue
[ADR-0006](../adr/0006-local-first-privacy.md): VOZ es local por defecto y este
proveedor solo se usa por decisión explícita.

## Cuándo sale audio de tu equipo

Solo si se cumplen las dos condiciones a la vez:

1. Hay una clave de ElevenLabs configurada.
2. Eliges ElevenLabs Scribe para ese trabajo concreto.

Tener la clave **no** activa nada: sin selección explícita no se hace ninguna
petición. No hay fallback automático: si un modelo local falla, VOZ no reintenta
con ElevenLabs. Tampoco se recomienda por defecto.

## Qué se envía

Una petición `POST https://api.elevenlabs.io/v1/speech-to-text` (multipart) por
cada tramo de audio que procesa el trabajo:

| Dato | Detalle |
| --- | --- |
| Audio | El WAV normalizado del tramo (PCM 16 kHz mono), con el nombre fijo `audio.wav`. Los tramos se solapan unos segundos, y ese solape se envía (y se factura) dos veces. |
| `model_id` | `scribe_v1`. |
| `diarize` | `true` por defecto (separar hablantes). |
| `timestamps_granularity` | `word`. |
| `tag_audio_events` | `false` (no se insertan etiquetas como "(risas)"). |
| `language_code` | Solo si indicas idioma. |
| `keyterms` | Solo si el proyecto aporta términos clave (máx. 100, 50 caracteres cada uno). El modelo de glosario por proyecto es S13.01; este adapter solo recibe la lista ya construida. Si el modelo elegido no admite `keyterms`, la API puede rechazarlo: no verificado en vivo. |
| Cabecera `xi-api-key` | Tu clave, únicamente en la cabecera HTTPS. |

**No se envía**: nombre de archivo ni ruta del original, nombre de proyecto,
transcripciones previas, ediciones, base de datos ni ninguna ruta del host.

## Qué vuelve y dónde se guarda

Texto, tiempos por palabra e identificadores de hablante (`speaker_0`, ...). Se
guarda localmente como cualquier otra transcripción; los originales siguen
siendo inmutables y la respuesta cruda no se conserva ni se registra.

## Retención en ElevenLabs

Depende de su política y de tu plan; VOZ no puede verificarla ni controlarla.
Consulta la política vigente: <https://elevenlabs.io/privacy> y la
documentación de la API: <https://elevenlabs.io/docs>. Si necesitas retención
cero o residencia de datos, confirma con ElevenLabs que tu plan la incluye
antes de enviar material sensible.

## La clave

- Se lee de `ELEVENLABS_API_KEY` (o `VOZ_ELEVENLABS_API_KEY`) y, si no existe,
  de `$XDG_CONFIG_HOME/voz/secrets.toml` (modo `0600`).
- Nunca se guarda en SQLite, nunca se escribe en logs, errores, diagnósticos ni
  respuestas de la API, y la representación (`repr`) del proveedor y de la
  petición no la incluye.
- **Borrarla**: `DELETE /api/providers/elevenlabs/key` (quita la entrada del
  archivo), o borra la línea `elevenlabs` de `secrets.toml`, y desactiva la
  variable de entorno si la usas. Revoca además la clave en tu panel de
  ElevenLabs si sospechas exposición.

## Coste y límites

- `GET /api/providers/elevenlabs/estimate?media_asset_id=` estima minutos y USD
  **antes** de enviar nada (ver [providers](../api/providers.md)). El precio por
  hora es una referencia fechada (2026-09-30), **no verificada en vivo**; tu
  plan real puede diferir.
- Límite de subida por archivo configurable (`max_upload_bytes`, 3 GiB por
  defecto según la documentación pública recordada el 2026-09-30, no verificado
  en vivo). El adapter no subdivide: los tramos los define el trabajo.
- El timeout crece con la duración (300 s + la duración del audio, máx. 1 h).
- Una subida nunca se reintenta sola (evita doble facturación); los fallos
  429/5xx/red se marcan `retryable` y decide el trabajo.
- Se puede cancelar durante la subida; el progreso de bytes enviados lo expone
  el callback `on_upload_progress`.
