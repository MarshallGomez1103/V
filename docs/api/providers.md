# Proveedores cloud: claves y estimación de coste (S11.01, S11.08)

Solo loopback (el servidor escucha en `127.0.0.1` por defecto). Ninguna
respuesta devuelve jamás una clave. Errores con
`{"detail": {"code", "message"}}`. Privacidad de OpenAI:
[docs/privacy/openai.md](../privacy/openai.md).

## `GET /api/providers`

```json
[{"id": "openai", "label": "OpenAI", "privacy_url": "https://openai.com/policies/privacy-policy", "configured": false, "cloud": true}]
```

El backend es la fuente de verdad de la lista: la UI muestra exactamente estos
proveedores (en este orden) y no conoce ids ni nombres propios. `label` es el
nombre visible y `privacy_url` (o `null`) el enlace a la política de privacidad
del proveedor; el composition root los toma de
`infrastructure/cloud/provider_info.py` y se los pasa al router como
`CloudProviderInfo`. Un proveedor nuevo solo se declara allí.

`configured` es true si hay clave en el entorno (`VOZ_<ID>_API_KEY` o
`<ID>_API_KEY`) o en `$XDG_CONFIG_HOME/voz/secrets.toml`. Un archivo de secretos
inseguro o corrupto cuenta como no configurado. Configurar un proveedor **no** lo
activa: solo un job que lo seleccione explícitamente envía audio.

## `PUT /api/providers/{id}/key`

Cuerpo `{"key": "..."}`. Responde `204` sin cuerpo (nunca hace eco). Escribe el
archivo de forma atómica con modo `0600`; nada va a SQLite ni a logs.

| Estado | `detail.code` | Causa |
| --- | --- | --- |
| 404 | `provider_not_found` | Proveedor desconocido. |
| 422 | `secrets_key_invalid` | La clave debe tener 1-512 caracteres ASCII imprimibles sin espacios. |
| 409 | `secrets_file_insecure` | `secrets.toml` no es un archivo regular con modo `0600`. |
| 409 | `secrets_file_invalid` | `secrets.toml` no se pudo leer. |
| 500 | `secrets_write_failed` | No se pudo escribir. |

Si hay variable de entorno, esta tiene prioridad sobre el archivo.

## `DELETE /api/providers/{id}/key`

Responde `204` (idempotente). Quita la entrada del archivo; no puede borrar
variables de entorno. Mismos errores 404/409/500.

## `GET /api/providers/{id}/estimate?media_asset_id=<uuid>[&model=<id>]`

Estima sin enviar nada. `model` por defecto: `whisper-1` para OpenAI.

```json
{"minutes": 5.0, "usd": 0.03, "price_source": "https://platform.openai.com/pricing (no verificado en vivo)", "price_date": "2026-09-30"}
```

Minutos y USD se redondean hacia arriba. Errores: 404 `provider_not_found` (o
sin precio para ese modelo), 404 `media_not_found`, 409 `media_duration_unknown`.
El precio es una constante fechada, no verificada en vivo.

## Campo `cloud` en las opciones

`GET /api/transcription-options` añade `cloud: bool` y `provider_label: string | null`
(nombre visible del proveedor, solo en opciones cloud; `null` en las locales) a
cada opción. La UI usa `cloud` para el aviso de envío y `provider_label` para
nombrar al proveedor; no mantiene una lista de ids cloud. Las opciones
cloud nunca llevan `recommendation`, `execution` ni `profile`, y `can_start`
depende solo de que la clave esté configurada.

## Aviso cloud en un trabajo

La pantalla de un trabajo decide si es cloud buscando su `selection.provider_id`
en `GET /api/providers` (todos los que devuelve son cloud) y usa su `label`. Si
esa consulta falla no se muestra aviso; nunca se infiere de un id codificado.

## ElevenLabs (`elevenlabs`, Scribe)

Proveedor cloud opcional, **experimental** (solo probado con transporte falso).
Privacidad, datos enviados y borrado de la clave:
[privacy/elevenlabs.md](../privacy/elevenlabs.md).

- **Clave**: mismos endpoints `PUT`/`DELETE /api/providers/elevenlabs/key`; se
  lee de `ELEVENLABS_API_KEY`, `VOZ_ELEVENLABS_API_KEY` o `secrets.toml`.
- **Estimación**: `GET /api/providers/elevenlabs/estimate?media_asset_id=`. Modelo
  por defecto `scribe_v1`, precio de referencia de 0,40 USD por hora de audio
  (2026-09-30, **no verificado en vivo**). Requiere que el composition root
  añada `ELEVENLABS_PRICES`/`ELEVENLABS_DEFAULT_MODELS` (módulo
  `infrastructure/cloud/elevenlabs_pricing.py`) a la tabla de precios y `elevenlabs`
  a los `provider_ids` del router. El solape entre tramos se factura dos veces y
  la estimación lo ignora.
- **Modelo**: `elevenlabs_scribe_descriptor()` (`provider_id="elevenlabs"`,
  `model_id="scribe_v1"`, capacidades transcripción, palabras, diarización y
  detección de idioma; sin CPU/GPU).
- **Resultado canónico**: segmentos por hablante (`speaker` = `speaker_id` del
  proveedor, etiqueta opaca), pausas de más de 0,8 s y puntuación final; palabras
  en milisegundos monótonos. El idioma detectado (ISO 639-3) se traduce a ISO 639-1.
- **Errores** (`TranscriptionFailureCode`): sin clave o clave rechazada
  (401/403) y respuestas inesperadas, `transcription_provider_failed` con
  `retryable=false`; 429, 5xx y fallos de red o timeout, el mismo código con
  `retryable=true`; 413/415 y audio no WAV, `transcription_invalid_audio`;
  cancelación (también durante la subida), `transcription_cancelled`. Los mensajes
  no incluyen la clave, el cuerpo de la respuesta ni rutas.
- **Límites** (constantes fechadas en `elevenlabs_scribe.py`, no verificadas en
  vivo): subida máxima 3 GiB, 100 keyterms de hasta 50 caracteres.
