# Privacidad: OpenAI (opcional, cloud)

Estado: **experimental**. El adapter está probado solo con un transporte falso
(nunca se ha llamado al servicio real), así que no se declara soportado. Sigue
[ADR-0006](../adr/0006-local-first-privacy.md): VOZ es local por defecto y este
proveedor solo se usa por decisión explícita. La clave de API de OpenAI es
independiente de ChatGPT/Codex: se factura como API, no como suscripción.

## Cuándo sale audio de tu equipo

Solo si se cumplen las dos condiciones a la vez:

1. Hay una clave de OpenAI configurada.
2. Eliges un modelo `openai` (Whisper o GPT-4o Transcribe Diarize) para ese
   trabajo concreto.

Tener la clave **no** activa nada: crear el proveedor, listar opciones o
registrar la clave no hacen ninguna petición. No hay fallback automático: si un
modelo local falla, VOZ no reintenta con OpenAI. Las opciones cloud aparecen
marcadas `cloud: true` en `GET /api/transcription-options` y nunca se
recomiendan.

## Qué se envía

Una petición `POST https://api.openai.com/v1/audio/transcriptions` (multipart)
por cada tramo de audio:

| Dato | Detalle |
| --- | --- |
| Audio | El WAV normalizado del tramo, con el nombre fijo `audio.wav`. Si supera el límite de subida (25 MB por defecto, leído como 25.000.000 bytes) se divide en subclips WAV con 2 s de solape; ese solape se envía (y se factura) dos veces. |
| `model` | `whisper-1` o `gpt-4o-transcribe-diarize`. |
| `response_format` | `verbose_json` (Whisper) o `diarized_json` (diarizado). |
| `timestamp_granularities[]` | `segment` (solo Whisper). |
| `chunking_strategy` | `auto` (solo diarizado; la API lo exige para audio largo). |
| `language` | Solo si indicas idioma. |
| Cabecera `Authorization` | Tu clave, únicamente en la cabecera HTTPS. |

**No se envía**: nombre de archivo ni ruta del original, nombre de proyecto,
transcripciones previas, ediciones, base de datos ni ninguna ruta del host.

## Qué vuelve y dónde se guarda

Texto y tiempos por segmento y, con el modelo diarizado, una etiqueta opaca de
hablante. Se guarda localmente como cualquier otra transcripción; los originales
siguen siendo inmutables y la respuesta cruda no se conserva ni se registra. Si
el audio se dividió, las etiquetas de hablante se prefijan con el número de
tramo (`1:A`, `2:A`): OpenAI no garantiza que `A` sea la misma persona entre
peticiones, y VOZ no lo asume.

## Retención en OpenAI

Depende de la política vigente de OpenAI y de tu organización; VOZ no puede
verificarla ni controlarla. Consulta: <https://openai.com/policies/privacy-policy>
y, para datos enviados por API, <https://platform.openai.com/docs/guides/your-data>.
Si necesitas retención cero, confirma con OpenAI que tu organización la tiene
habilitada antes de enviar material sensible.

## Límites, reintentos y coste

- Límites y precios son constantes fechadas (`LIMITS_DATE`) tomadas de la
  documentación pública: **no verificados en vivo**. Fuentes:
  <https://platform.openai.com/docs/guides/speech-to-text> y
  <https://platform.openai.com/pricing>. El precio del modelo diarizado es una
  suposición igual al de `gpt-4o-transcribe`.
- Se reintenta con backoff exponencial y jitter solo ante 429, 5xx y timeouts
  (hasta 4 intentos; respeta `Retry-After`). Los errores 4xx de autenticación o
  validación nunca se reintentan.
- `GET /api/providers/openai/estimate?media_asset_id=...` estima minutos y USD
  antes de enviar nada ([contrato](../api/providers.md)). Es una estimación:
  no incluye el solape de subclips ni cambios de tarifa.

## La clave

- Se lee de `VOZ_OPENAI_API_KEY`, luego `OPENAI_API_KEY` y, si no existen, de
  `$XDG_CONFIG_HOME/voz/secrets.toml` (modo `0600`; si el modo es más abierto,
  o el archivo es un symlink, VOZ lo rechaza con `secrets_file_insecure`).
- Nunca se guarda en SQLite, nunca se escribe en logs, errores, diagnósticos ni
  respuestas de la API, y la representación (`repr`) del proveedor, de la
  petición y del gestor de secretos no la incluye.
- **Borrarla**: `DELETE /api/providers/openai/key` (quita la entrada del
  archivo), o borra la línea `openai` de `secrets.toml`. Si la clave viene de una
  variable de entorno, quítala de tu entorno: VOZ no puede borrarla. Sin clave, la
  opción OpenAI deja de estar disponible. Revoca además la clave en el panel de
  OpenAI si sospechas que se expuso.
