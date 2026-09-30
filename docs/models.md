# Almacén de modelos: descarga, importación y borrado

Comportamiento del adapter `FileSystemModelStore`
(`src/voz/infrastructure/model_storage.py`) para la Sección 8 (S8.04-S8.06,
S8.15) y la Sección 14 (S14.04, S14.09). Contrato de aplicación:
`ModelFile` y `ModelDownloadPort` en `application/ports/model_installation.py`.
La decisión de fondo (revisión fijada, manifest, instalación explícita) sigue en
[ADR-0004](adr/0004-local-asr-and-recoverable-chunks.md). Nada de esto se
ejecuta sin que el caller lo pida: importar VOZ no descarga nada.

## Entrada: `ModelFile`

Cada archivo del snapshot se declara con `name` (basename, sin `/`, `\`, `..`,
no `.voz-model.json` ni sufijo `.part`), `size_bytes > 0` y `sha256`
(hex minúsculas de 64 caracteres, o `None` cuando upstream no lo publica, p. ej.
archivos no LFS). El descriptor debe tener `source` y revisión de 40 hex; sin
ella `provenance_required`.

## `download(descriptor, files, *, base_url, progress, cancelled)`

- URL: `{base_url}/{source}/resolve/{revision}/{name}`; solo `http`/`https`.
- Staging determinista `models/<provider>/.download-<hash>/` con `name.part`.
  Un archivo completo y verificado se renombra a `name` dentro del staging.
- `progress(hechos, totales)`: bytes acumulados de todos los archivos (los que ya
  estaban en disco cuentan desde la primera llamada); `totales = sum(size_bytes)`.
- `cancelled()` se consulta entre bloques de 1 MiB (y mientras se calcula el
  SHA-256). Cancelar deja el `.part` intacto y lanza `cancelled`.
- Verificación por archivo: tamaño exacto y SHA-256 si existe. Discrepancia
  borra ese archivo y lanza `checksum_mismatch`.
- Publicación: manifest `.voz-model.json` (ahora con la lista `files` con nombre,
  tamaño y sha256), `fsync` y `rename` atómico, reutilizando la lógica de
  `install`. Si otro instalador ganó la carrera se conserva su instalación.

### Reanudación y recuperación (S8.15, S14.09)

Una segunda llamada reanuda cada `.part` con `Range: bytes=N-`:

| Situación | Resultado |
| --- | --- |
| Servidor responde 206 con `Content-Range` coherente | continúa desde N |
| Servidor responde 200 (sin soporte de Range) | reinicia ese archivo |
| 206 con inicio incoherente, o 416 | descarta el `.part` y reintenta una vez desde cero |
| `.part` mayor que `size_bytes` | se descarta y se vuelve a descargar |
| Archivo ya completo en staging pero corrupto | se descarta y se vuelve a descargar |
| Conexión cortada a mitad | `network_error`, el `.part` se conserva |

Un directorio publicado cuyo manifest lista `files` con algún archivo ausente,
enlace simbólico o de tamaño distinto se considera **no instalado**
(`is_installed`, `resolve_path` y `registered_descriptors` lo excluyen) y el
siguiente `download`/`import_local_snapshot` lo reemplaza. Los manifests
anteriores (sin `files`, de `install`) se validan como antes.

### Espacio previo (S14.04)

Antes de abrir la red se exige `bytes pendientes + margen` libres mediante
`require_free_space` (`DiskSpacePort` se inyecta en el constructor; sin él se
omite). Los bytes ya presentes en staging no cuentan como pendientes. El
puerto no tiene una ubicación `MODELS`; se usa `DiskLocation.DERIVATIVES`, que
vive bajo el mismo directorio de datos. Un `ENOSPC` durante la escritura se
traduce igual.

### Errores (`ModelInstallationFailureCode`)

`cancelled`, `checksum_mismatch`, `network_error` (timeout, conexión, corte),
`http_error` (con `error.status`), `disk_space_insufficient`, `not_installed`,
además de los existentes. Los mensajes no incluyen rutas ni URLs. El timeout de
red por lectura es `network_timeout_seconds` del constructor (30 s).

## `import_local_snapshot(descriptor, files, snapshot_dir, *, progress, cancelled)`

Adopta un snapshot ajeno (p. ej. la caché de Hugging Face de Buzz:
`snapshots/<rev>/x -> ../../blobs/<hash>`) **sin escribir jamás dentro de
`snapshot_dir`**. Resuelve los enlaces, comprueba existencia y tamaño de todos
los archivos antes de crear nada, y por archivo intenta `os.link` (mismo
sistema de archivos: sin duplicar espacio) y, si falla, `shutil.copyfile`
(comprobando espacio antes de copiar). Verifica SHA-256 cuando existe; el
progreso cuenta bytes verificados (tamaño completo si no hay digest). Cancelar o
fallar elimina el staging (`.import-*.tmp`); no hay reanudación porque enlazar
es barato.

## `remove` y `disk_usage`

`remove(descriptor) -> int` renombra el directorio canónico VOZ del descriptor a
`.remove-*.tmp` y lo borra; nunca toca otros modelos ni la caché de origen. Los
archivos con más de un enlace duro (adoptados desde otra caché) no liberan
espacio y no se cuentan en el valor devuelto. Lanza `not_installed` si no hay
manifest coincidente (un directorio dañado sí se puede borrar).
`disk_usage(descriptor)` suma los tamaños en disco o devuelve `None`.

## Límites conocidos

- No hay bloqueo entre dos `download` simultáneos del mismo modelo; el jobs layer
  debe serializarlos (el SHA-256 protege la integridad de los archivos LFS).
- Un archivo completo en staging se vuelve a hashear al reanudar.
