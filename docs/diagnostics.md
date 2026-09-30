# Diagnóstico y respaldo de VOZ

Todo lo de este documento es local: sin red, sin cargar modelos, sin llamar a
proveedores cloud.

## `voz doctor`

Comprueba FFmpeg/ffprobe, puerto, rutas XDG, disco, modelos, runtime ASR, GPU y
claves API opcionales. Salida en texto (por defecto) o `--json`; `--redact` oculta
rutas absolutas. Código de salida `1` solo si hay algún `FALLO`; los avisos no
cambian el código.

| Check | Qué mide | Aviso cuando |
| --- | --- | --- |
| `disco` | espacio libre en `data` y en `cache` | menos de 5 GiB en cualquiera |
| `modelos` | modelos registrados por VOZ: `proveedor/id rev <12 hex> (tamaño GiB)`, leídos de los manifests (`FileSystemModelStore.registered_descriptors()`), sin cargar nada | ninguno registrado o error de lectura |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` | solo `set` / `unset` | nunca: son opcionales y "no se usan salvo selección explícita" |

Las claves nunca se imprimen: ni valor, ni prefijo, ni longitud.

## `voz doctor --bundle <archivo.zip>`

Genera un zip para adjuntar a un reporte. Implica `--redact`, imprime el
diagnóstico normal y no sobrescribe un archivo existente (sale con código `2`).

| Archivo | Contenido |
| --- | --- |
| `doctor.json` | resultado de doctor, con rutas redactadas |
| `versions.json` | Python, plataforma, VOZ, fastapi, sqlalchemy, alembic, faster-whisper, ctranslate2 (`null` si no está instalado) |
| `database.json` | revisión Alembic actual y head, nº de proyectos, nº de trabajos por estado, códigos de error de trabajos fallidos |
| `README.txt` | qué contiene el bundle |

Redacción: la carpeta personal pasa a `~` y las bases XDG a `$XDG_CONFIG_HOME`,
`$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, `$XDG_STATE_HOME` (se aplica a todo texto de
todos los archivos). Los códigos de error de trabajos que no tengan forma de
código estable (`[A-Za-z0-9_.-]{1,64}`) se agrupan como `other`.

Nunca incluye: la base de datos, medios, transcripciones, nombres de proyectos o
archivos, modelos, ni valores de variables de entorno. La base se abre en modo
solo lectura y solo se ejecutan `COUNT`/`GROUP BY` sobre `state` y `error_code`.
Regresión: `tests/unit/test_diagnostics_bundle.py` siembra nombres, texto y rutas
sensibles y verifica que ninguno aparece en ningún archivo del zip.

## Respaldo previo a migrar (`upgrade_to_head`)

Antes de migrar una base **existente** cuya revisión no sea head, VOZ crea una
copia consistente (API de backup de SQLite, respeta WAL, fsync del archivo y del
directorio) en:

```
$XDG_STATE_HOME/voz/backups/voz-<revisión_actual>-<UTC AAAAMMDDThhmmssffffffZ>.sqlite3
```

- Se conservan los 5 respaldos más recientes; los anteriores se borran.
- Base nueva o ya en head: sin respaldo.
- Si el respaldo falla se lanza `MigrationBackupError` (`code =
  "migration_backup_failed"`) y **no se migra**; la base queda intacta.
- Los archivos se crean con permisos `0600` en un directorio `0700`.
- Para restaurar: detén VOZ y copia el respaldo sobre
  `$XDG_DATA_HOME/voz/voz.sqlite3` (borra antes `voz.sqlite3-wal` y `-shm`).
