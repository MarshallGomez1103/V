# Biblioteca, renombrar y eliminar proyectos — plan v3, Slice A

Local (`127.0.0.1`). Errores con la forma `{"detail": {"code", "message"}}`; sin
rutas del host. La biblioteca es la pantalla de inicio: una fila por proyecto.

## `GET /api/library` (CP-A1)

→ `200 {"items": [item]}` ordenado por **actividad más reciente** primero
(`max(creación del proyecto, última actualización de su último job)`; el id
desempata). Una sola consulta por tabla, sin N+1.

```json
{
  "project_id": "uuid",
  "name": "Clase de física",
  "created_at": "2026-10-03T01:17:42+00:00",
  "updated_at": "2026-10-03T01:37:13+00:00",
  "media": {
    "media_asset_id": "uuid",
    "filename": "clase.m4a",
    "media_type": "audio/aac",
    "duration_ms": 6464073
  },
  "latest_job": {
    "id": "uuid",
    "state": "COMPLETED",
    "transcript_id": "uuid",
    "model_id": "turbo",
    "progress": 1.0,
    "error_code": null,
    "created_at": "2026-10-03T01:18:33+00:00"
  },
  "speaker_count": 11,
  "segment_count": 1312
}
```

- `updated_at` es la fecha de actividad por la que se ordena.
- `media`: la grabación del último job; si el proyecto no tiene job, la primera
  grabación subida. **`null` si el proyecto nunca recibió una grabación** (un
  proyecto creado cuyo upload falló): la UI debe tolerarlo. `filename` es el
  nombre original (`display_name`); `media_type` es el tipo detectado al
  importar y, si el sondeo no lo reconoció, el que sugiere la extensión del
  archivo (`mimetypes`, solo como pista); queda `null` si no hay ninguno.
- `latest_job`: el job más reciente del proyecto (`created_at`, id); `null` sin
  jobs. `transcript_id` solo existe cuando la fila del transcript ya está
  guardada (desde el final del ASR, antes de los hablantes); `model_id` es el
  modelo de la selección del job. `state` ∈ estados de job (`QUEUED` …
  `COMPLETED`, `FAILED`, `CANCELLING`, `CANCELLED`).
- `speaker_count` y `segment_count` son los **del transcript de ese último job**
  (`0` si aún no hay transcript). `speaker_count` cuenta solo los hablantes con
  **al menos un segmento** (un hablante que solo aparece en turnos, sin ningún
  segmento, no cuenta).

## `GET /api/media/{media_asset_id}`

Ficha de la grabación sin rutas, para reabrir un job por URL sin adivinar nada:

```json
{"media_asset_id": "uuid", "project_id": "uuid", "filename": "clase.m4a",
 "media_type": "audio/aac", "duration_ms": 6464073, "sha256": "…", "size_bytes": 81037665}
```

`404 media_asset_not_found`. Mismo `media_type` con la regla de la biblioteca.

## `PATCH /api/projects/{project_id}` (CP-A2)

Body `{"name": str}`. Misma validación que al crear: se recorta y debe tener de
1 a 200 caracteres sin caracteres de control. → `200` el proyecto
(`{"id","name","created_at"}`).

| Estado | Código | Significado |
| --- | --- | --- |
| 404 | `project_not_found` | el proyecto no existe (se evalúa antes que el nombre) |
| 422 | `project_name_invalid` | vacío, solo espacios, > 200 o con caracteres de control; no se guarda nada |

## `DELETE /api/projects/{project_id}` (CP-A2)

Exige la cabecera `X-VOZ-Action: delete-project` (como el apagado del servidor:
una página de otro origen no puede enviarla sin preflight, que VOZ nunca
permite). → `204` sin cuerpo.

Borra **todo** lo del proyecto:

- filas, en una sola sentencia con `ON DELETE CASCADE`: jobs, selecciones,
  checkpoints, transcripts, segmentos, palabras, hablantes, turnos, grabaciones
  (`media_assets`) y glosario;
- archivos: la carpeta `projects/<project_id>/` de la carpeta de datos de VOZ
  (originales de solo lectura y derivados). Se usan las primitivas de
  `infrastructure/safe_fs.py` (`remove_directory_tree`): cadena de directorios
  sin seguir enlaces, los symlinks internos se borran como enlace (nunca su
  destino) y en Windows se quita el atributo de solo lectura.

Orden: **primero los archivos y luego las filas**. Si los archivos no se pueden
borrar el proyecto sigue intacto y se puede reintentar (el borrado de archivos
es idempotente).

| Estado | Código | Significado |
| --- | --- | --- |
| 403 | `project_delete_forbidden` | falta la cabecera `X-VOZ-Action: delete-project` |
| 404 | `project_not_found` | el proyecto no existe |
| 409 | `project_busy` | algún job del proyecto no es terminal (`QUEUED` … `PERSISTING`, `CANCELLING`); cancelar y esperar |
| 500 | `project_delete_failed` | no se pudieron borrar los archivos; no se borró nada de la base |

No se toca nunca el cache de modelos ni el de Buzz (no pertenecen al proyecto).
Queda sin borrar el pequeño cache de formas de onda (`cache/waveforms/`), que
está direccionado por contenido y puede compartirse entre proyectos.
