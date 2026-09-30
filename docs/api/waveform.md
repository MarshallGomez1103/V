# Waveform — S5.09 y S5.14

Peaks precalculados para dibujar la forma de onda en el navegador. Local
(`127.0.0.1`), sin red ni proveedores cloud. Los errores usan
`{"detail": {"code", "message"}}`; nunca se devuelven rutas del host.

## `GET /api/media/{media_asset_id}/peaks?buckets=2000`

- `buckets`: entero entre **100 y 20000** (por defecto 2000).
- Respuesta 200:

```json
{
  "media_asset_id": "uuid",
  "duration_ms": 61234,
  "buckets": 2000,
  "peaks": [[-0.412, 0.398], [-0.05, 0.07]]
}
```

`peaks` tiene exactamente `buckets` pares `[min, max]` en orden temporal,
normalizados para que la muestra más fuerte valga ±1 y redondeados a 3
decimales. El audio en silencio devuelve todo `[0.0, 0.0]`. `duration_ms` es la
duración sondeada del asset (o la decodificada si faltara).

| Estado | `code` | Cuándo |
| --- | --- | --- |
| 404 | `media_asset_not_found` | El asset no existe |
| 422 | `peaks_buckets_invalid` | `buckets` no es entero o está fuera de 100–20000 |
| 500 | `waveform_unavailable` | FFmpeg ausente, medio ilegible o sin audio decodificable |

## Cálculo

- Fuente: el derivado normalizado (`*.inference.wav`) si existe; si no, el
  original inmutable. Se abre por descriptor, sin exponer rutas.
- FFmpeg decodifica por pipe a PCM s16le mono a 8 kHz y el adaptador lo consume
  en streaming (bloques de 64 KiB). La memoria es O(`buckets`): los bloques de
  min/max se fusionan por pares al superar `2 * buckets` y se remuestrean a
  exactamente `buckets` al terminar. Una hora de audio tarda ~1 s y ~70 MB de
  RSS en total (proceso Python incluido).
- La ruta es síncrona (`def`), así que FastAPI la ejecuta en su threadpool.
  Un vigilante mata FFmpeg si supera 600 s.

## Caché

`<XDG_CACHE_HOME>/voz/waveforms/v1-<sha256 del medio>-<buckets>.json`, con
`{"duration_ms", "peaks"}`. Escritura atómica (temporal + `os.replace`); un
archivo corrupto o con otra forma se ignora y se reescribe. Un fallo al escribir
la caché no rompe la petición. Al ser una clave por contenido, el mismo audio
reimportado reutiliza los peaks.

## Frontend

`Waveform` (`apps/web/src/components/Waveform.tsx`) pide `?buckets=4000` con un
`AbortController`, dibuja solo la porción visible en un `<canvas>` (dimensionado
con `devicePixelRatio`) y ofrece zoom 1x–32x (botones Acercar/Alejar y control
deslizante), scroll horizontal, clic para buscar y flechas izquierda/derecha
(±5 s) con el foco en el waveform.
