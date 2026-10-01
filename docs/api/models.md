# Gestor de modelos — consulta y borrado (S8.02, S8.03, S8.07, S8.08)

Sección 8 del roadmap. El catálogo canónico (`faster_whisper_catalog()`, S8.01)
define seis modelos Faster Whisper con fuente y revisión fijadas. Este contrato
consulta y borra; la descarga va como tarea en segundo plano (sección final).
Ninguna respuesta contiene rutas del host.

## Claves con espacio de nombres (MODELS-UI-002)

El gestor reúne en un solo catálogo (`ManagedModelCatalog`) los modelos de
faster-whisper, los de whisper.cpp (solo si existe `whisper-cli`) y la
separación de hablantes (sherpa-onnx). Un `model_id` suelto puede repetirse entre
proveedores (`small` existe en faster-whisper y en whisper.cpp), así que la API
direcciona cada modelo por su **clave** `"<provider_id>:<model_id>"`:

| Clave | Familia |
| --- | --- |
| `faster-whisper:turbo` | ASR faster-whisper |
| `whisper-cpp:small` | ASR whisper.cpp (requiere `whisper-cli`) |
| `diarization:sherpa-default` | Segmentación + embeddings de hablantes |

Todos los endpoints de esta página (`DELETE /api/models/{clave}`,
`POST /api/models/{clave}/install`) aceptan la clave en la ruta (los `:` son
válidos; el cliente la codifica con `encodeURIComponent`). Por compatibilidad,
un id **sin** `:` se interpreta como faster-whisper. En `DELETE`, `confirm` debe
repetir exactamente lo enviado en la ruta.

## `GET /api/models`

HTTP 200. Una entrada por cada modelo del catálogo, instalado o no.

```json
{
  "models": [
    {
      "key": "faster-whisper:tiny",
      "provider_id": "faster-whisper",
      "kind": "asr",
      "requires": null,
      "runtime_available": true,
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
| `key`, `provider_id` | Clave de la API (ver arriba) y proveedor. |
| `kind` | `asr` o `diarization`. La UI agrupa "Hablantes" aparte. |
| `requires` | Runtime que el modelo necesita para usarse: `whisper-cli` (whisper.cpp), `diarization` (extra opcional con sherpa-onnx) o `null`. |
| `runtime_available` | `false` si falta ese runtime: el modelo se lista pero la UI no ofrece instalarlo ("requiere el extra diarization"). whisper.cpp ni se lista sin `whisper-cli`. |
| `model_id` | Identificador dentro del proveedor; en faster-whisper, el mismo que en `/api/transcription-options`. |
| `source`, `revision` | Procedencia fijada (SHA de commit de 40 caracteres). `null` en diarización: sus artefactos son assets de release verificados por SHA-256. |
| `profile` | `fast` o `quality`; `null` en diarización. |
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
| 200 | (cuerpo) | `{ "key": "faster-whisper:tiny", "model_id": "tiny", "freed_bytes": 77010000 }` |
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
  "key": "faster-whisper:large-v3",
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
| `key` | Clave del modelo (`provider:model`). |
| `state` | `queued`, `running`, `completed`, `failed` o `cancelled`. |
| `done_bytes`, `total_bytes` | Progreso acumulado de todos los archivos. En cola valen 0 y la suma del catálogo; al completar, `done == total`. |
| `origin` | `buzz` para `import`; `null` para `download`. |
| `error_code` | Solo con `failed`; `null` en el resto. Códigos estables: los de `ModelInstallationFailureCode` (`model_installation_network_error`, `model_installation_http_error`, `model_installation_checksum_mismatch`, `disk_space_insufficient`, `model_installation_io_error`, `model_installation_invalid_snapshot`, ...), `external_model_not_found` si la copia desapareció antes de importar, y `model_task_failed` para cualquier error inesperado (el detalle va al log, nunca a la respuesta). |

Flujo típico del cliente: `POST install` -> sondear `GET /api/model-tasks/{id}`
mientras `state` sea `queued`/`running` -> al terminar refrescar `GET /api/models`
(`installed: true`).

### Separación de hablantes (`diarization:sherpa-default`)

Se instala y borra como cualquier otro modelo: `POST install` con
`method=download` encola una tarea que descarga los dos artefactos fijados
(segmentación pyannote 3.0, 6 958 444 bytes, MIT; embeddings WeSpeaker, 26 530 550
bytes, Apache-2.0), con progreso agregado, cancelación y reanudación desde
`.part`. `DELETE` con `confirm=diarization:sherpa-default` los borra. No admite
`method=import`. El runtime (`sherpa-onnx`, extra `diarization`) es independiente:
sin él, `runtime_available` es `false` y la UI no ofrece instalar.

Límite conocido: el borrado no comprueba jobs de diarización en curso (la
selección de job solo registra el modelo ASR).
