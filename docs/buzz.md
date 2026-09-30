# Reutilizar modelos del cache de Buzz

Si ya usas [Buzz](https://github.com/chidiwilliams/buzz), VOZ puede adoptar
algunos de sus modelos para que no los descargues dos veces. Buzz **no** es una
dependencia de VOZ: solo se lee su cache, y solo cuando tú pides importar.

## Qué se detecta

Formato faster-whisper en layout HuggingFace hub:

```text
<raíz>/models--<org>--<repo>/snapshots/<revisión>/{model.bin,config.json,...}
```

(los archivos del snapshot son symlinks a `../../blobs/<hash>`). Raíces
buscadas, en este orden (la primera que tenga el modelo gana):

1. `$BUZZ_MODEL_ROOT`, si está definida y no vacía.
2. `~/.var/app/io.github.chidiwilliams.Buzz/cache/Buzz/models` (Flatpak).
3. `${XDG_CACHE_HOME:-~/.cache}/Buzz/models`.

Un modelo es candidato solo si TODO esto se cumple:

- `source` y `revision` (commit SHA de 40 caracteres) coinciden **exactamente**
  con una entrada del catálogo de VOZ (`faster_whisper_catalog()`); una
  revisión distinta se ignora aunque el modelo sea "el mismo".
- Existen todos los archivos del catálogo con el tamaño esperado.
- Cada symlink, ya resuelto, queda dentro del directorio HF de ese repositorio
  (los que apuntan fuera, o a otro repositorio, se rechazan) y es un archivo
  regular.

Se ignora: `whisper/*.pt` (formato openai-whisper, incompatible), modelos de
otras revisiones, snapshots incompletos, raíces ilegibles o inexistentes
(sin error). `.buzz_complete` no se exige.

## Qué no se toca

La detección solo usa `os.stat` y `os.path.realpath`: no abre archivos, no crea
directorios, no escribe. La importación (`FileSystemModelStore.import_local_snapshot`)
solo lee el origen: enlaza en duro (o copia si es otro sistema de archivos) a
un directorio de staging propio de VOZ, verifica tamaño y SHA-256 y publica de
forma atómica con su manifest. Buzz sigue funcionando igual; nunca se mueve ni
se borra nada de su cache. Un enlace duro añade un nombre más al mismo inodo
(cambia su contador de enlaces y su ctime, no su contenido ni su mtime).
Borrar el modelo desde VOZ solo elimina el enlace propio.

## Cómo desactivarlo

`BUZZ_MODEL_ROOT=` (definida pero **vacía**) desactiva por completo la
detección de Buzz. Para apuntar a una ubicación no estándar,
`BUZZ_MODEL_ROOT=/ruta/a/models`.

## Contrato interno

- Puerto `voz.application.ports.external_models`: `ExternalModelCandidate`,
  `ExternalModelSource.find_candidates()`, `ExternalModelError`.
- Adaptador `voz.infrastructure.buzz_cache.BuzzModelCache`.
- Caso de uso `voz.application.import_external_model.ImportExternalModel`:
  `available(origin="buzz")` y `execute(model_id, origin="buzz", progress=,
  cancelled=)`. Errores estables: `external_model_unknown_model`,
  `external_model_not_found`, más los `model_installation_*` del store.
- Las rutas del host (`snapshot_dir`) nunca deben llegar al navegador.
