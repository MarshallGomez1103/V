# Gestor de modelos — consulta y borrado (S8.02, S8.03, S8.07, S8.08)

Sección 8 del roadmap. El catálogo canónico (`faster_whisper_catalog()`, S8.01)
define seis modelos Faster Whisper con fuente y revisión fijadas. Este contrato
solo consulta y borra; no descarga (eso lo hace el store por otra vía). Ninguna
respuesta contiene rutas del host.

## `GET /api/models`

HTTP 200. Una entrada por cada modelo del catálogo, instalado o no.

```json
{
  "models": [
    {
      "model_id": "tiny",
      "display_name": "Faster Whisper Tiny (fast)",
      "source": "Systran/faster-whisper-tiny",
      "revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
      "license": "MIT",
      "multilingual": true,
      "profile": "fast",
      "size_bytes": 77003619,
      "installed": true,
      "disk_bytes": 77010000,
      "external": [{ "origin": "buzz" }]
    }
  ],
  "disk": { "models_bytes": 77010000, "free_bytes": 120000000000 }
}
```

| Campo | Significado |
| --- | --- |
| `model_id` | Identificador del catálogo; el mismo que en `/api/transcription-options`. |
| `source`, `revision` | Procedencia fijada (SHA de commit de 40 caracteres). |
| `profile` | `fast` o `quality`. |
| `size_bytes` | Suma de los archivos esperados del catálogo (lo que se descargaría). |
| `installed` | `true` si hay un manifest VOZ válido para exactamente esa fuente y revisión. Una revisión distinta instalada antes no cuenta. |
| `disk_bytes` | Bytes realmente ocupados en disco por la instalación; `null` si no está instalado. |
| `external` | Orígenes de otras herramientas que tienen exactamente esa fuente y revisión y podrían importarse (`buzz`). Vacío sin fuente externa. Sin duplicados, sin rutas. |
| `disk.models_bytes` | Suma de `disk_bytes` de los modelos instalados. |
| `disk.free_bytes` | Bytes libres del volumen de datos; `null` si no se puede consultar. |

## `DELETE /api/models/{model_id}?confirm=<model_id>`

Borra la instalación fijada del catálogo. `confirm` debe repetir el id exacto
(distingue mayúsculas); es una protección contra borrados accidentales, no
autenticación.

| HTTP | `detail.code` | Cuándo |
| --- | --- | --- |
| 200 | (cuerpo) | `{ "model_id": "tiny", "freed_bytes": 77010000 }` |
| 400 | `model_delete_unconfirmed` | Falta `confirm` o no coincide con `model_id`. Se evalúa primero, sin tocar el disco. |
| 404 | `model_not_installed` | El id no está en el catálogo o no está instalado. |
| 409 | `model_in_use` | Un job no terminal (en cola, en proceso o cancelándose) tiene una selección con ese modelo y esa revisión. Termina o cancela el job y reintenta. |
| 500 | `model_remove_failed` | Error de E/S al borrar; mensaje sin rutas. |

Errores con forma `{"detail": {"code", "message"}}`. Los jobs completados,
fallidos o cancelados no bloquean el borrado; conservan su snapshot de selección
y su transcripción, pero no podrán reejecutarse con el modelo hasta reinstalarlo.

Límite conocido: un job creado entre la comprobación de uso y el borrado no queda
protegido (ventana muy corta, app local monousuario).

## Instalación en segundo plano (MODELS-TASKS-001)

Descargar (1-3 GB desde Hugging Face) o importar (desde la caché de Buzz) no
cabe en un request: el POST encola una tarea y el cliente consulta su estado.
Las tareas viven **solo en memoria** (`ModelTaskRunner`, un hilo worker y cola
FIFO: una tarea pesada a la vez). No son durables a propósito: si la app se
cierra a mitad, la descarga se reanuda sola desde los `.part` cuando el usuario
vuelve a pulsar instalar. Al apagar el servidor las tareas en cola o en curso se
cancelan. Ninguna respuesta contiene rutas ni URLs.

### `POST /api/models/{model_id}/install`

```json
{ "method": "download", "confirm": true }
{ "method": "import", "origin": "buzz", "confirm": true }
```

`method` es `download` o `import` (otro valor: 422 de validación); `origin` solo
aplica a `import` (por ahora `buzz`, valor por defecto). `confirm` debe ser
`true`: la descarga es siempre explícita.

| HTTP | `detail.code` | Cuándo |
| --- | --- | --- |
| 202 | (cuerpo `TaskView`) | Tarea encolada. Si ya hay una tarea activa (`queued`/`running`) para ese modelo, se devuelve esa misma sin crear otra. |
| 400 | `model_install_unconfirmed` | `confirm` ausente o distinto de `true`. Se evalúa primero; no encola nada. |
| 404 | `model_unknown` | El id no está en el catálogo. |
| 409 | `model_already_installed` | Ya hay una instalación válida de esa fuente y revisión. |
| 404 | `external_model_not_found` | `method=import` y no hay copia compatible en el origen. |

### `GET /api/model-tasks`

`{ "tasks": [TaskView, ...] }`: las activas y las últimas 20 terminadas, de más
antigua a más reciente.

### `GET /api/model-tasks/{task_id}`

`TaskView`, o 404 `model_task_not_found` (id desconocido o ya descartado del
historial).

### `POST /api/model-tasks/{task_id}/cancel`

202 con el `TaskView`. Una tarea en cola pasa a `cancelled` al instante; una en
curso sigue `running` hasta que el store atiende la cancelación (entre bloques
de 1 MiB) y entonces pasa a `cancelled`, conservando los `.part`. Repetir el
cancel sobre una tarea en curso es idempotente. 409 `model_task_terminal` si ya
terminó; 404 `model_task_not_found` si no existe.

### `TaskView`

```json
{
  "id": "5f0c...e1",
  "model_id": "large-v3",
  "method": "download",
  "origin": null,
  "state": "running",
  "done_bytes": 1073741824,
  "total_bytes": 3087284237,
  "error_code": null,
  "created_at": "2026-09-30T10:00:00Z",
  "updated_at": "2026-09-30T10:00:12Z"
}
```

| Campo | Significado |
| --- | --- |
| `state` | `queued`, `running`, `completed`, `failed` o `cancelled`. |
| `done_bytes`, `total_bytes` | Progreso acumulado de todos los archivos. En cola valen 0 y la suma del catálogo; al completar, `done == total`. |
| `origin` | `buzz` para `import`; `null` para `download`. |
| `error_code` | Solo con `failed`; `null` en el resto. Códigos estables: los de `ModelInstallationFailureCode` (`model_installation_network_error`, `model_installation_http_error`, `model_installation_checksum_mismatch`, `disk_space_insufficient`, `model_installation_io_error`, `model_installation_invalid_snapshot`, ...), `external_model_not_found` si la copia desapareció antes de importar, y `model_task_failed` para cualquier error inesperado (el detalle va al log, nunca a la respuesta). |

Flujo típico del cliente: `POST install` -> sondear `GET /api/model-tasks/{id}`
mientras `state` sea `queued`/`running` -> al terminar refrescar `GET /api/models`
(`installed: true`).
