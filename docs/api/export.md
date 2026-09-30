# Exportación de transcripciones — S10.07, S10.08, S10.14

Endpoint local (`127.0.0.1`); no invoca proveedores ni red. Los errores usan
`{"detail": {"code": "<snake_code>", "message": "<texto seguro>"}}`.

```
GET /api/transcripts/{transcript_id}/export?format=txt&timestamps=false&group_by_speaker=false
```

| Parámetro | Valores | Por defecto |
| --- | --- | --- |
| `format` | `txt`, `markdown`, `srt`, `vtt`, `json` | `txt` |
| `timestamps` | `true`/`false` | `false` |
| `group_by_speaker` | `true`/`false` | `false` |

## Respuesta 200

El cuerpo es el documento UTF-8. Cabeceras:

| `format` | `Content-Type` | Extensión |
| --- | --- | --- |
| `txt` | `text/plain; charset=utf-8` | `.txt` |
| `markdown` | `text/markdown; charset=utf-8` | `.md` |
| `srt` | `application/x-subrip; charset=utf-8` | `.srt` |
| `vtt` | `text/vtt; charset=utf-8` | `.vtt` |
| `json` | `application/json` | `.json` |

- `Content-Disposition: attachment; filename="<ascii>"`. Si el nombre contiene
  caracteres no ASCII se añade `filename*=UTF-8''<percent-encoded>` (RFC 5987) y
  `filename` queda como equivalente ASCII (sin diacríticos).
- Nombre base: el nombre del proyecto (o, si faltara, el del archivo importado
  sin extensión), saneado por `safe_export_filename`: solo el último componente,
  sin separadores, `..`, caracteres de control ni nombres reservados de Windows,
  máximo 100 caracteres, fallback `transcript`. Nunca contiene rutas del host.
- `X-Content-Type-Options: nosniff`.

## Opciones (solo `txt` y `markdown`)

- `timestamps=true`: prefijo `[HH:MM:SS.mmm]` por segmento (en Markdown en
  negrita: `**[HH:MM:SS.mmm]**`). SRT y VTT ya incluyen tiempos.
- `group_by_speaker=true`: los segmentos consecutivos del mismo speaker se
  agrupan bajo su nombre (`Nombre:` en TXT, `## Nombre` en Markdown). Un speaker
  que vuelve a hablar tras otro abre un grupo nuevo. Los segmentos sin speaker
  (o con un speaker que ya no existe) van bajo `Sin speaker`. Los speakers se
  leen del proyecto dueño de la transcripción.

Ejemplo TXT agrupado con tiempos:

```
Ana:
[00:00:00.000] Hola, soy Ana

Sin speaker:
[00:00:03.000] sin dueño
```

## Errores

| Estado | `code` | Cuándo |
| --- | --- | --- |
| 404 | `transcript_not_found` | La transcripción no existe |
| 422 | `export_format_unknown` | `format` no es uno de los cinco |
| 422 | `export_option_unsupported` | `timestamps`/`group_by_speaker` en `srt`, `vtt` o `json` |

Un valor no booleano en las opciones produce el 422 estándar de validación de
FastAPI. El formato se valida antes de consultar la base de datos.

## Cableado

`create_export_router(ExportTranscript(transcripts, segments, speakers, projects,
media_assets))` en `voz.interfaces.api.export`; caso de uso en
`voz.application.export.service`.
