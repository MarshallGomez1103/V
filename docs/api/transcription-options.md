# Opciones de transcripción — Corte B1 / S5.18

`GET /api/transcription-options` devuelve HTTP 200 con `{ "options": [...] }`.
OpenAPI (`/openapi.json`, `/docs`) publica el schema real derivado de las
proyecciones de application. No requiere parámetros ni cambia estado.

## Semántica

| Campo | Significado y límite |
| --- | --- |
| `provider_id` | Identificador del adapter conocido, no prueba que su runtime esté instalado. |
| `model_id`, `source`, `revision` | Modelo y procedencia fijada. `source` y `revision` son null para la entrada conocida todavía sin revisión local. Nunca se inventa un SHA. |
| `profile` | `ProcessingProfile` completo: nombre, preferencia de dispositivo, precisiones GPU ordenadas y precisión CPU. No es el modelo ni la ejecución elegida. |
| `installation_status` | `registered` si un manifest VOZ válido coincide con identidad, ubicación canónica y timestamp con zona. `not_registered` si no se encuentra un registro válido para esa opción conocida. Un manifest inválido no equivale a ausencia física de pesos. |
| `files_available` | Comprobación superficial de `model.bin`, `config.json`, `tokenizer.json` y el vocabulario que corresponde al modelo (`vocabulary.txt` en tiny/base/small/medium, `vocabulary.json` en large-v3/turbo): archivos regulares no vacíos y sin symlinks. No valida contenido, checksums ni integridad. |
| `runtime_available` | La clase de engine se puede importar y el probe del runtime responde. No se construye un engine ni se ejecuta inferencia. |
| `execution` | `ExecutionDecision`: device, precision y fallback_reason, conservando la política existente. Null si no se puede seleccionar. |
| `device_name` | Nombre de la GPU medido con `nvidia-smi` (truncado, solo caracteres imprimibles) cuando la ejecución elegida es `cuda`; null en CPU o si no hay medición. Nunca se infiere VRAM por el nombre comercial. |
| `capabilities` | Intersección del descriptor y lo expuesto por el adapter VOZ. CPU/GPU son backends que soporta el adapter; la disponibilidad concreta se consulta en execution, no se deduce de esta lista. |
| `can_start` | Todos los prerrequisitos observables pasan: registro, revisión fijada, archivos mínimos, runtime, ejecución compatible y transcripción. Permite intentar cargar; **no garantiza** integridad, RAM/VRAM suficiente, éxito de inferencia ni validación real CUDA. No significa que exista ya un endpoint para iniciar jobs. |
| `recommendation` | `{ "recommended": bool, "reason": str }` o null. **Con hardware medido** se calcula por ajuste a VRAM/RAM (sección siguiente), sea cual sea el estado de instalación (solo si los únicos bloqueos son de instalación). **Sin medición**: `{ "recommended": true, "reason": "default_compatible_profile" }` para opciones `fast` que pueden iniciarse; null en los demás casos. Política declarativa, no benchmark. Puede haber varias revisiones locales elegibles: no se inventa cuál es más reciente/mejor. |
| `blocking_reasons` | Códigos estables; lista vacía si can_start es true. |

Los códigos de bloqueo son `model_not_registered`, `model_files_missing`,
`revision_unpinned`, `runtime_unavailable`, `execution_unavailable` y
`transcription_unavailable`. Pueden coexistir. Runtime ausente, falta de modelo
o imposibilidad de recomendar son respuestas válidas, no HTTP 500.

Si no se puede inspeccionar el almacenamiento por un fallo de acceso, se devuelve
HTTP 503 con `detail.code = transcription_options_unavailable` y un mensaje
seguro. No se devuelven paths, contenido de manifests ni tracebacks.

## Recomendación por hardware medido (S8.11)

El probe mide, sin cargar ningún modelo: nombre y VRAM total/libre de la primera
GPU (`nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits`,
sin shell, timeout de 5 s; solo si CUDA es utilizable) y RAM total/disponible
(`/proc/meminfo`, solo Linux). Cualquier fallo significa "no medido" (null), nunca
cero. La función pura `application/hardware_recommendation.recommend` aplica:

| Hardware medido | Opción recomendada (`reason`) |
| --- | --- |
| CUDA, VRAM >= 6 GiB | `turbo` recomendado (`gpu_fast_default`); `large-v3` con `recommended=false` (`gpu_quality_fits`) |
| CUDA, 5 GiB <= VRAM < 6 GiB | `medium` (`gpu_limited_medium`) |
| CUDA, VRAM < 5 GiB | `small` (`gpu_limited_small`) |
| Solo CPU, RAM >= 8 GiB | `small` (`cpu_default`) |
| Solo CPU, RAM < 8 GiB | `base` (`cpu_low_ram`) |

Los demás modelos reciben `recommendation = null`. Origen de la política: las
cifras de memoria publicadas de faster-whisper/CTranslate2 y los tiempos medidos
en la máquina objetivo (RTX 4060 Laptop, 8188 MiB: turbo fp16 carga en 1,0 s y
transcribe 25 s en 0,9 s; large-v3 en 2,1 s / 1,7 s). No es un benchmark
exhaustivo de VOZ. Sin medición se conserva el comportamiento anterior.

## Catálogo actual

Viene de `faster_whisper_catalog()` (S8.01): seis modelos Faster Whisper con
fuente y revisión fijadas, licencia MIT, multilingües.

| `model_id` | Perfil |
| --- | --- |
| `tiny`, `base`, `small` | `fast` |
| `medium` | `quality` |
| `large-v3` | `quality` |
| `turbo` (large-v3-turbo) | `fast`, la recomendación por defecto |

`/api/transcription-options` expone una opción por cada entrada, instalada o no.
Con registro local válido se exponen las revisiones registradas que coinciden con
la fuente conocida (puede haber una revisión distinta de la fijada). Sin registro
se expone la entrada con su revisión fijada y `not_registered`; ya no aparece
`revision_unpinned` para el catálogo actual, y `option_id` es estable porque
depende de la revisión fijada. No se consulta catálogo remoto ni caches externos.
Instalar, importar y borrar se documenta en [models.md](models.md).

Las capabilities actuales son `cpu`, `gpu`, `language_detection` y
`transcription`. Aunque el descriptor upstream menciona translation, el port
actual no permite solicitar esa tarea: B1 no la anuncia. Tampoco anuncia
diarization ni word_timestamps.

## Identidad y futura creación de jobs

`option_id` usa el prefijo `option-v1-` seguido de SHA-256 del JSON canónico de
`[provider_id, model_id, source, revision, profile_completo]`, con claves
ordenadas y separadores compactos. No depende de display_name, orden de listado,
registro ni hardware observado. Este hash identifica configuración; **no es un
checksum de los pesos**.

Una entrada sin revisión no puede enviarse como selección ejecutable (el catálogo
actual ya no produce ninguna). B2 deberá
resolver y revalidar el ID contra el catálogo actual y fijar en el job el
descriptor/perfil completo, la decisión de ejecución y opciones que afecten el
resultado (por ejemplo idioma). El ID solo no sustituye ese snapshot. B1 no
modifica checkpoints, migraciones ni persistencia de selección.

## Límites arquitectónicos y operativos

El router recibe `GetTranscriptionOptions` desde bootstrap, sin inspección de
disco ni imports de SDK. El caso de uso depende de dos ports read-only y aplica
la política con `HardwareCapabilities → ExecutionDecision`. Los adapters leen
registros y consultan runtime. No hay nuevo service locator ni singleton mutable.
La ruta síncrona se ejecuta en el thread pool de FastAPI, no en el event loop.

No se descargan modelos, se cargan engines ni se escriben manifests al consultar.
El resultado es una observación y puede quedar desactualizado; deberá revalidarse
al crear un job. El runtime conserva su calificación experimental. Model Manager,
reparación, benchmarks y verificación exhaustiva siguen en Sección 8.

No cambia ninguna decisión arquitectónica de ADR-0001/0004; este documento
describe el contrato de consulta, no introduce un nuevo ADR.
