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
