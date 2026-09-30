# ADR-0004: ASR local con modelos explícitos y chunks recuperables

- Estado: Aceptada
- Fecha: 2026-09-05
- Responsables: mantenedores de VOZ
- Alcance: primer provider ASR local y recuperación de trabajos largos
- Última revisión: 2026-09-30 (S16.15/S16.16: nota de cableado y evidencia; la
  decisión no cambia)
- Relacionadas: [ADR-0005](0005-transcription-providers.md) (port y registry),
  [ADR-0006](0006-local-first-privacy.md) (offline y sin cloud implícito)

## Contexto

VOZ necesita integrar Faster Whisper sin convertir Internet, CUDA o una cache
externa en requisitos implícitos. También debe procesar grabaciones largas sin
perder los chunks ya confirmados tras cancelar o cerrar la aplicación. El
contrato común no puede exponer tipos de Faster Whisper, CTranslate2, paths del
host ni flags propios del motor.

## Decisión

Faster Whisper es un adapter de infraestructura bajo `TranscriptionProvider`.
El adapter recibe un descriptor abierto de audio y resuelve exclusivamente una
instalación local exacta; nunca entrega un nombre remoto al runtime. Se instancia
con `local_files_only=True` y traduce salida, idioma, cancelación y fallos a tipos
canónicos de application.

Los modelos se representan mediante `ModelDescriptor`, cuya procedencia
instalable contiene tanto repositorio fuente como revisión fijada. La instalación
es una operación separada que exige confirmación explícita, usa
`huggingface_hub.snapshot_download` con esa revisión y publica una copia con
manifest bajo el directorio XDG de datos. Los metadatos de descarga viven bajo
el directorio XDG de cache. Importar VOZ, construir el provider o transcribir no
inicia descargas.

La revisión instalable debe ser un SHA de commit Git completo, hexadecimal y de
40 caracteres; ramas y tags mutables no forman una identidad recuperable. La
identidad de almacenamiento y caché incluye provider, model, source y revision.
El provider conserva como máximo un engine activo para no retener a la vez los
perfiles `fast` y `quality` en VRAM, y serializa su inicialización concurrente.
El composition root fija el provider al descriptor exacto con el que resolvió
device y compute; no puede reutilizar esa decisión con otro modelo o perfil.

`faster-whisper` se distribuye como el extra opcional `asr-local`; el arranque
básico no carga su runtime ni CUDA. La revisión fijada y el manifest son la
evidencia inicial de procedencia. Checksums adicionales y administración
avanzada del catálogo pertenecen a la Sección 8.

Los perfiles `fast` y `quality` serán descriptores canónicos resueltos a una
decisión observable de device/compute. Un fallback de CUDA a CPU nunca será
silencioso.

El orquestador divide la duración normalizada en chunks ordenados con offsets
globales y overlap pequeño. El adapter de audio abre un WAV PCM físico acotado a
cada chunk para no decodificar la grabación completa repetidamente. El provider
produce offsets locales y application los convierte una sola vez al timeline
global. Cada chunk se convierte en unidad recuperable. La confirmación de sus
segmentos, idioma solicitado y detectado, checkpoint y progreso del job ocurre
en una única transacción SQLite. Al reanudar, solo se omiten chunks cuya
confirmación completa existe para el mismo job, plan, provider, model, source,
revision e idioma solicitado.

El checkpoint conserva por separado la fracción completada de ASR y el progreso
global monotónico del job. Así, una etapa ASR que comienza con progreso previo
puede reanudarse sin confundir ambos espacios de progreso.

## Corrección de lifecycle y cancelación — 2026-09-07 (Corte A)

La auditoría S4 → S5 reprodujo dos defectos: la asignación del nuevo engine
evaluaba su carga mientras todavía retenía el anterior, y un iterable vacío
podía devolver éxito pese a una cancelación. Esta corrección corresponde a
S4.04/S4.13; no inicia la Sección 5 ni un Model Manager.

- Una sustitución resuelve primero la instalación y comprueba cancelación.
  Después vacía la clave y la referencia al engine anterior **antes** de llamar
  a la nueva factory. Si esa carga falla, la caché queda vacía y se puede
  reintentar tanto el modelo nuevo como el anterior. Si falla la resolución,
  la caché anterior permanece válida; no se ha iniciado otra carga.
- `FasterWhisperProvider.close()` es explícito, idempotente y definitivo.
  Usa el mismo lock que protege carga e inferencia, incluida la iteración lazy:
  espera a la llamada activa, vacía la caché y rechaza futuras transcripciones
  con `PROVIDER_FAILED` no reintentable. Un nuevo ciclo requiere otro adapter.
- El dueño del runtime debe llamar a `LocalAsrRuntime.close()` en su `finally`
  de shutdown (también permite `contextlib.closing(runtime)`). Este método
  delega al adapter concreto. No se añade `close()` a `TranscriptionProvider`:
  adquirir/liberar el engine pertenece a infraestructura/composition root, no
  al contrato de transcripción que consume application. La aplicación HTTP
  actual no crea un runtime ASR; no se añade un lifespan ni un ejecutor ficticio.
- El adapter comprueba cancelación antes de cargar, tras resolver/cargar, tras
  `engine.transcribe()`, durante la iteración y antes de devolver éxito. También
  cubre iterables vacíos y cancelación al agotarlos, sin depender del chequeo
  adicional de `RecoverableTranscription`. Se conserva el código `CANCELLED`.
- Los generadores de segmentos se cierran en `finally`; las referencias locales
  a engine/iterable se limpian para que los tracebacks de cancelación no las
  retengan. Los fallos del SDK también limpian los locales de frames terminados
  en sus cadenas cause/context, incluidos engines parcialmente construidos.
  Se conservan tipo, mensaje y stack, pero no los locales para depuración
  post-mortem. La propiedad liberada es la del adapter: no se fuerza un GC global,
  no se manipula el allocator CUDA ni se implementa un framework de recursos.

La cancelación es cooperativa: no interrumpe una llamada nativa bloqueada y el
cierre espera su retorno. La liberación de referencias está probada con engines
deterministas y weakrefs, sin `gc.collect()` ni GPU; no acredita liberación de
VRAM ni transcripción real CUDA. Se mantiene la calificación experimental de S4.

Evidencia de regresión: `test_faster_whisper_lifecycle.py` cubre reemplazo sin
solapamiento, carga fallida/reintento, cierre antes/después de cargar o fallar,
cierre concurrente mediante events y un lock observable, cancelación por fase,
cleanup con excepción retenida (incluidos fallos SDK encadenados y construcción
parcial) y éxito vacío. La suite existente conserva
reutilización del engine, serialización y resultados canónicos; el test de
bootstrap verifica que el cierre del runtime alcanza al provider registrado.

## Actualización de cableado — 2026-09-30

La nota del Corte A según la cual la aplicación HTTP no crea un runtime ASR
quedó desactualizada por la Sección 5 y no altera la decisión:

- `create_app()` (`src/voz/bootstrap.py`) construye un `LocalAsrRuntime` por
  descriptor bajo demanda mediante `provider_for(selection)`, usando el
  `ModelDescriptor` guardado en el snapshot del job. El `lifespan` llama a
  `runtime.close()` para cada uno al apagar y antes cierra el `JobRunner`.
- El `JobRunner` ejecuta `RecoverableTranscription` en un hilo; al arrancar,
  `runner.recover()` reencola los jobs no terminales y los checkpoints
  confirmados evitan repetir chunks (`tests/integration/application/test_job_runner.py::test_recover_resumes_transcribing_job_without_repeating_chunk`).
- La instalación de modelos (`FileSystemModelStore.install`) **no** está
  expuesta por HTTP ni CLI: ningún código de `src/voz/` la invoca. Un modelo
  debe estar ya instalado para que una opción sea iniciable
  (`can_start` en `/api/transcription-options`). Un Model Manager con
  interfaz de usuario es Sección 8, **planificado**.
- Solo Faster Whisper está implementado. El resto de providers y su registry
  se tratan en [ADR-0005](0005-transcription-providers.md).

## Consecuencias positivas

- El modo offline no depende de resolución remota durante la transcripción.
- Una instalación identifica exactamente fuente y revisión.
- Faster Whisper y futuros providers comparten resultado, errores y cancelación.
- El cierre de VOZ no invalida chunks ya confirmados.
- Memoria y decodificación quedan acotadas por el tamaño del chunk.
- Dominio y application no importan SDKs de ASR.

## Costes y límites

- Instalar el extra y un modelo sigue siendo una acción separada del bootstrap.
- La disponibilidad real de CUDA depende del driver y runtime del equipo; hasta
  ejecutar una prueba opt-in, el camino GPU se rotula experimental.
- Una revisión fijada aporta reproducibilidad de procedencia, pero no sustituye
  un checksum publicado; la verificación ampliada queda para Model Manager.
- El overlap requiere una política determinista para no duplicar segmentos.

## Fuentes upstream

- Faster Whisper permite cargar un directorio local y ofrece
  `local_files_only`: <https://github.com/SYSTRAN/faster-whisper>
- Hugging Face documenta `snapshot_download` con `revision` y `cache_dir`:
  <https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download>
- CTranslate2 expone los compute types soportados por device:
  <https://opennmt.net/CTranslate2/python/ctranslate2.get_supported_compute_types.html>

## Evidencia actual (2026-09-30)

| Requisito | Prueba |
| --- | --- |
| Adapter, timestamps, idioma y errores canónicos | `tests/unit/infrastructure/asr/test_faster_whisper.py`, `tests/contract/test_transcription_provider.py` |
| Lifecycle: reemplazo, `close()`, cancelación por fase | `tests/unit/infrastructure/asr/test_faster_whisper_lifecycle.py` |
| Catálogo de descriptores, hardware y opciones | `tests/unit/infrastructure/asr/test_catalog.py`, `test_hardware.py`, `test_options.py`, `tests/unit/application/test_asr_device_selection.py` |
| Instalación explícita, revisión fijada, manifest | `tests/unit/infrastructure/test_model_storage.py` |
| Composición sin descargas y cierre del runtime | `tests/unit/test_asr_bootstrap.py` |
| Chunks recuperables y reanudación | `tests/unit/application/test_chunked_transcription.py`, `tests/integration/application/test_recoverable_transcription.py`, `tests/integration/application/test_local_asr_pipeline.py` |
| Smoke real opt-in con modelo instalado por el usuario | `tests/integration/application/test_faster_whisper_real_opt_in.py` (variables `VOZ_FASTER_WHISPER_MODEL_*`) |

## Verificación

Esta decisión se considera aplicada cuando:

- construir/usar el adapter sin modelo no produce red ni descarga;
- una instalación no confirmada falla antes de construir el downloader;
- el manifest conserva provider, modelo, source y revision exactos;
- el adapter transforma timestamps a milisegundos y preserva texto e idioma;
- fallos y cancelación se traducen a códigos estables sin paths privados;
- los perfiles y fallback son observables mediante pruebas deterministas;
- reabrir SQLite recupera chunks confirmados sin repetirlos.
- la suite contractual se ejecuta sobre el adapter y existe un smoke real
  opt-in que nunca selecciona ni descarga modelos por sí mismo.
