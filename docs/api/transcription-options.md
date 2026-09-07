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
| `files_available` | Comprobación superficial de `model.bin`, `config.json` y `tokenizer.json`: archivos regulares no vacíos y sin symlinks. No valida contenido, checksums ni integridad. |
| `runtime_available` | La clase de engine se puede importar y el probe del runtime responde. No se construye un engine ni se ejecuta inferencia. |
| `execution` | `ExecutionDecision`: device, precision y fallback_reason, conservando la política existente. Null si no se puede seleccionar. |
| `device_name` | Null actualmente: el probe no ofrece un nombre fiable. No se infiere VRAM por nombre comercial. |
| `capabilities` | Intersección del descriptor y lo expuesto por el adapter VOZ. CPU/GPU son backends que soporta el adapter; la disponibilidad concreta se consulta en execution, no se deduce de esta lista. |
| `can_start` | Todos los prerrequisitos observables pasan: registro, revisión fijada, archivos mínimos, runtime, ejecución compatible y transcripción. Permite intentar cargar; **no garantiza** integridad, RAM/VRAM suficiente, éxito de inferencia ni validación real CUDA. No significa que exista ya un endpoint para iniciar jobs. |
| `recommendation` | `{ "recommended": true, "reason": "default_compatible_profile" }` para opciones `fast` que pueden iniciarse; null en los demás casos. Política declarativa, no benchmark. Puede haber varias revisiones locales elegibles: no se inventa cuál es más reciente/mejor. |
| `blocking_reasons` | Códigos estables; lista vacía si can_start es true. |

Los códigos de bloqueo son `model_not_registered`, `model_files_missing`,
`revision_unpinned`, `runtime_unavailable`, `execution_unavailable` y
`transcription_unavailable`. Pueden coexistir. Runtime ausente, falta de modelo
o imposibilidad de recomendar son respuestas válidas, no HTTP 500.

Si no se puede inspeccionar el almacenamiento por un fallo de acceso, se devuelve
HTTP 503 con `detail.code = transcription_options_unavailable` y un mensaje
seguro. No se devuelven paths, contenido de manifests ni tracebacks.

## Catálogo actual

- Faster Whisper `turbo` (large-v3-turbo), perfil `fast`.
- Faster Whisper `large-v3`, perfil `quality`.

Se reutilizan los dos constructores existentes. Admiten ahora revisión ausente
para describir una opción conocida pero no instalable/ejecutable todavía.
Por cada modelo se exponen las revisiones registradas que coinciden con su
procedencia conocida. Sin registros se expone una entrada con revisión null.
No se consulta catálogo remoto ni caches externos; no hay `medium` añadido.

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

Al registrar una revisión cambia la identidad de la entrada antes no fijada.
Una entrada sin revisión no puede enviarse como selección ejecutable. B2 deberá
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
