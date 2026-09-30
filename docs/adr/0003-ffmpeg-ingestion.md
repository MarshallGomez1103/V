# ADR-0003: Ingestión FFmpeg sobre originales inmutables

- Estado: Aceptada
- Fecha: 2026-09-03
- Responsables: mantenedores de VOZ
- Alcance: inspección, almacenamiento y normalización multimedia local
- Última revisión: 2026-09-30 (S16.14; añade cableado actual y evidencia)
- Diagramas: [componentes](../architecture/03-componentes.md)

## Contexto

VOZ debe aceptar audio o video según su contenido real, conservar exactamente
los bytes seleccionados por el usuario y producir un derivado apropiado para
ASR. Las grabaciones pueden ser largas, tener extensiones engañosas, contener
varios streams o fallar después de una inspección superficial. Además, una ruta
puede cambiar entre dos aperturas y los procesos FFmpeg pueden terminar, fallar
o ser cancelados en cualquier momento.

La UI no debe conocer rutas del host y el dominio no debe depender de FFmpeg ni
del filesystem. La frontera relevante no es una lista de extensiones, sino si
la instalación local de FFmpeg puede decodificar un stream de audio real.

## Decisión

La ingestión se coordina en `application` mediante puertos tipados y se ejecuta
en adapters de `infrastructure`:

1. `MediaStoragePort` copia el archivo seleccionado a un original cuyo destino
   se deriva solo de UUID, calcula SHA-256 durante la misma lectura y publica
   sin reemplazar contenido existente.
2. `MediaProbePort` inspecciona el descriptor ya abierto de esa copia inmutable.
   El adapter usa `ffprobe`, valida streams y codecs disponibles y devuelve solo
   metadata permitida, nunca una ruta.
3. `ImportMedia` persiste el hash, tamaño, duración y MIME conservador. Si el
   resultado de una escritura es ambiguo, reconcilia por identidad antes de
   ejecutar una compensación destructiva.
4. `MediaNormalizationPort` recibe el descriptor del original y las identidades
   del proyecto/medio. El adapter FFmpeg selecciona el índice absoluto del
   primer stream de audio decodificable y genera PCM signed 16-bit, mono, 16 kHz.
5. Los temporales se crean dentro de directorios confinados, permanecen abiertos
   durante el subprocess y se publican atómicamente sin reemplazo. La fuente y
   el temporal se entregan a FFmpeg mediante descriptors heredados en Linux.

La normalización reporta progreso monotónico y consulta cancelación antes,
durante y justo antes de publicar. Un fallo de decode se traduce a un error
tipado; stderr, rutas privadas y tracebacks no forman parte del mensaje normal
para el usuario.

## Invariantes de almacenamiento

- El original nunca se modifica ni se usa como salida de FFmpeg.
- Nombres visibles no se usan como identidades ni componentes de destino.
- Los directorios bajo el root confiable se abren con `dir_fd` y `O_NOFOLLOW`;
  se comparan `lstat` y `fstat` donde una carrera podría cambiar la identidad.
- Archivo y directorio se sincronizan con `fsync` antes de confirmar una
  publicación durable.
- Fallos de cleanup o rollback no se silencian como éxito; se reporta cuando el
  filesystem impide confirmar el estado final.
- Éxito, fallo y cancelación no dejan temporales conocidos ni procesos hijos.

## Consecuencias positivas

- Probe, hash y metadata corresponden a los mismos bytes inmutables.
- WAV, MP3, M4A, OGG, OPUS y WebM comparten el mismo contrato.
- La extensión del archivo no decide compatibilidad.
- La aplicación puede importar y normalizar sin entregar rutas a dominio o UI.
- Cancelar no publica un derivado parcial.

## Costes y límites

- El adapter seguro por descriptors usa capacidades POSIX/Linux disponibles en
  Bazzite. Un port a Windows necesitará otro mecanismo equivalente.
- La metadata técnica completa se conserva en el resultado del probe; el
  esquema inicial persiste hash, tamaño, duración y MIME.
- Un error persistente del filesystem puede impedir confirmar un rollback. Ese
  estado se expone como error explícito para reconciliación posterior.
- Esta ADR cubre el pipeline local invocable desde application. La importación
  HTTP y su contrato se documentan en [docs/api/jobs.md](../api/jobs.md); aquí
  solo se registra cómo se cablea (sección siguiente).
- FFmpeg y ffprobe son binarios del sistema, no vendorizados. Sin ellos la
  importación falla con un error tipado (`MediaProbeFailureCode.TOOL_UNAVAILABLE`, HTTP 503
  `media_probe_unavailable`) y `voz doctor` lo reporta como fallo. No se fija
  ni verifica una versión mínima; **planificado** si aparece una
  incompatibilidad concreta.
- Compatibilidad probada: fixtures sintéticos WAV, MP3, M4A, OGG, OPUS y WebM
  sobre Linux. Otras plataformas y contenedores son experimentales.

## Alternativas consideradas

### Validar por extensión

Rechazada. Una extensión puede ser incorrecta y no demuestra que exista un
stream de audio decodificable.

### Inspeccionar la ruta y copiar después

Rechazada. El archivo puede cambiar entre aperturas y mezclar metadata de un
contenido con el hash de otro.

### Escribir directamente al destino final

Rechazada. Un fallo o cancelación dejaría un derivado parcial que parecería
completo.

### Exponer rutas desde los casos de uso

Rechazada. Acoplaría application al layout del host y facilitaría fugas hacia la
API o el navegador.

## Cableado actual (2026-09-30)

```text
POST /api/projects/{id}/media        (interfaces/api/media.py)
  cuerpo crudo -> temporal en ~/.cache/voz/uploads (siempre borrado)
  -> ImportMedia (application/import_media.py)
       MediaStoragePort  = FileSystemMediaStorage   (copia inmutable + SHA-256)
       MediaProbePort    = FfprobeMediaProbe        (sobre la copia ya publicada)
       MediaAssetRepository (SQLite)

job en estado PREPROCESSING          (application/job_runner.py)
  -> PrepareInferenceAudio -> re-probe del original inmutable
  -> NormalizeImportedMedia -> MediaNormalizationPort = FfmpegMediaNormalizer
  -> projects/<p>/derivatives/<m>.inference.wav  (solo si el derivado no existe)
```

- La normalización ocurre dentro del job, no durante la subida (decisión de
  Sección 5). Un job reanudado reutiliza el derivado existente
  (`JobRunner._derivative_exists`).
- La subida rechaza cuerpos vacíos, nombres inseguros y tamaños por encima de
  `DEFAULT_MAX_UPLOAD_BYTES` (8 GiB). El nombre visible se guarda como
  `display_name`; nunca forma parte del destino en disco.
- `ffprobe` corre con `timeout_seconds=15` y sin shell (`FfprobeMediaProbe`).
- La cancelación de un job durante la normalización llega a FFmpeg mediante
  `MediaNormalizationCancellationToken`; no se publica un derivado parcial.

## Evidencia actual (2026-09-30)

| Requisito | Prueba |
| --- | --- |
| Extensión irrelevante o engañosa | `tests/integration/audio/test_ffprobe_media_probe.py` |
| Fixtures de seis formatos deterministas y decodificables | `tests/integration/media/test_media_fixtures.py`, licencias en [fixtures-licenses.md](../fixtures-licenses.md) |
| Contrato común del probe | `tests/contract/test_media_probe_port.py`, `tests/unit/infrastructure/audio/test_ffprobe.py` |
| Copia inmutable, hash, symlinks, traversal, `fsync`, cleanup | `tests/unit/infrastructure/test_media_storage.py` |
| Importación con compensación y reconciliación | `tests/unit/application/test_import_media.py`, `tests/integration/application/test_import_media_sqlite.py` |
| PCM mono 16 kHz, original intacto, primer stream de audio | `tests/integration/audio/test_ffmpeg_media_normalizer_integration.py` |
| Cancelación, callbacks que fallan, carreras de symlink y raíz, fallos de `fsync` sin artefactos parciales | mismo archivo |
| Normalización desde application | `tests/unit/application/test_normalize_media.py`, `tests/integration/application/test_normalize_imported_media.py` |
| Contrato HTTP de subida sin rutas | `tests/integration/test_media_upload_api.py` |
| Preparación del derivado dentro del job | `tests/integration/application/test_job_runner.py::test_missing_derivative_is_prepared_before_transcribing` |

## Alternativas adicionales consideradas

### Subida multipart

No adoptada. FastAPI necesitaría una dependencia adicional para multipart
(documentado en [docs/api/jobs.md](../api/jobs.md)); el cuerpo crudo con
cabecera `X-Voz-Filename` se transmite directamente a un temporal con límite de
tamaño (regla de dependencias de [AGENTS.md](../../AGENTS.md)).

### Normalizar durante la subida

No adoptada. Bloquearía la petición HTTP con un trabajo largo y cancelable. La
normalización es una etapa del job con progreso y cancelación.

### Bibliotecas Python de audio (PyAV, pydub, soundfile) en lugar de FFmpeg

No adoptadas por ahora. FFmpeg ya es requisito, decodifica los seis formatos
del contrato y permite pasar descriptors heredados sin rutas. Cada biblioteca
añadiría una dependencia y otro conjunto de códecs a verificar.

## Verificación

La decisión se considera aplicada cuando:

- un archivo con extensión irrelevante se acepta por sus streams/codecs;
- los fixtures licenciados de seis formatos se inspeccionan y decodifican;
- hash y metadata sobreviven la reapertura de SQLite;
- el recorrido importación -> normalización produce PCM mono de 16 kHz y deja
  el original byte-identical;
- cancelación, corrupción, errores de callback y carreras simuladas no publican
  artefactos parciales ni dejan procesos o descriptors abiertos;
- pruebas de traversal, symlinks y nombres inseguros no escriben fuera del root.
