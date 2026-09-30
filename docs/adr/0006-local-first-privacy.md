# ADR-0006: Local-first, loopback por defecto y sin cloud implícito

- Estado: Aceptada
- Fecha: 2026-09-30
- Responsables: mantenedores de VOZ
- Alcance: privacidad y superficie de red del producto (S16.16)
- Relacionadas: [ADR-0001](0001-modular-monolith.md),
  [ADR-0002](0002-sqlite-persistence.md) (XDG),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (offline),
  [ADR-0005](0005-transcription-providers.md) (providers)
- Diagramas: [contexto](../architecture/01-contexto.md),
  [contenedores](../architecture/02-contenedores.md)

## Contexto

VOZ procesa grabaciones que pueden contener clases, reuniones o conversaciones
privadas. La confianza del usuario depende de que el audio, las transcripciones
y las rutas de su equipo no salgan de su máquina salvo por una decisión
explícita. El plan maestro (sección 17) y [AGENTS.md](../../AGENTS.md) ya fijan
estas invariantes; esta ADR las registra como decisión arquitectónica con su
evidencia y sus límites reales.

## Decisión

1. **Procesamiento local por defecto.** Importación, normalización, ASR,
   persistencia y edición se ejecutan en el proceso local y sin Internet una vez
   instalado el modelo. Ningún flujo requiere una cuenta ni un servicio remoto.
2. **Loopback por defecto.** El servidor escucha en `127.0.0.1`, puerto `8765`
   (`DEFAULT_HOST`, `DEFAULT_PORT` en `src/voz/interfaces/cli/main.py`). Exponer
   la API en otra interfaz requiere pasar `--host` de forma explícita. Al abrir
   el navegador, una dirección comodín (`0.0.0.0`, `::`) se traduce a una
   dirección de loopback conectable (`browser_host`). El servidor de desarrollo
   de Vite también escucha en `127.0.0.1` y hace proxy de `/api`
   (`apps/web/vite.config.ts`); no hay CORS configurado.
3. **Sin cloud implícito.** Ningún cliente cloud existe en el código ni en las
   dependencias (`pyproject.toml`: Alembic, FastAPI, SQLAlchemy, Typer, Uvicorn
   y el extra opcional `faster-whisper`). Un provider cloud futuro solo puede
   ejecutarse si el usuario lo eligió para ese job, sin fallback automático
   desde un fallo local, con aviso visible de que el audio saldrá del equipo y
   con claves fuera de SQLite y de los logs. Todo eso es **planificado**
   (Secciones 11 y 12 del [ROADMAP](../../ROADMAP.md)).
4. **La red solo se toca de dos formas.**
   - Instalar un modelo: `FileSystemModelStore.install` exige
     `confirmed=True` y una revisión Git de 40 caracteres, y es la única ruta
     que usa `huggingface_hub`. Hoy ningún endpoint ni comando la invoca.
   - El arranque de la CLI sondea `GET /api/health` en la URL de su propio
     servidor para abrir el navegador.
   Transcribir resuelve solo instalaciones locales
   (`local_files_only=True`); construir el provider, importar VOZ o listar
   opciones no descarga nada.
5. **Sin telemetría.** No hay envío de métricas, informes de error ni
   comprobación de actualizaciones. El bundle web no carga fuentes, scripts ni
   imágenes de terceros.
6. **Datos bajo XDG, fuera del checkout.** Base de datos, originales,
   derivados, modelos y temporales se escriben bajo los directorios XDG
   ([ADR-0002](0002-sqlite-persistence.md)); los patrones de `.gitignore` y la
   regla de no versionar `.ai/` impiden subir grabaciones, transcripciones o
   modelos.
7. **Nada de rutas del host hacia el navegador.** Las respuestas usan
   identidades (UUID) y nombres visibles; los archivos se sirven por
   `/api/media/{id}/original`, no por ruta. `voz doctor --redact` oculta las
   rutas absolutas del informe.
8. **Errores y logs seguros.** Las respuestas son `{"detail": {"code",
   "message"}}` con códigos estables; los tracebacks y stderr de FFmpeg no se
   exponen. No se registran secretos (hoy no se manejan claves).
9. **Un transcript literal no se reemplaza en silencio.** VOZ no llama a
   ningún LLM hoy; cualquier corrección asistida futura deberá conservar el
   texto literal y presentarse como derivado.

## Consecuencias positivas

- Un usuario puede auditar la superficie de red: un puerto de loopback y, solo
  bajo confirmación, la descarga de un modelo.
- El comportamiento offline es la norma, no un modo especial.
- Los datos del usuario nunca se mezclan con el repositorio.
- Los providers cloud, cuando existan, parten de un contrato de consentimiento
  ya definido.

## Costes y límites

- **No hay autenticación.** Loopback es el control de acceso. Quien pase
  `--host` con una dirección de red expone a toda esa red la API, los medios y
  los transcripts sin credenciales. Hoy la CLI no emite una advertencia en ese
  caso; una advertencia y un modo de autenticación local son **planificados**
  (el plan maestro menciona `auth-local`).
- Otros procesos y usuarios del mismo equipo pueden conectar a `127.0.0.1:8765`.
  El alcance de seguridad está en [SECURITY.md](../../SECURITY.md).
- No hay `Content-Security-Policy` ni cabeceras de endurecimiento en el servidor
  estático (plan maestro sección 17): **planificado**.
- Sin instalador de modelos expuesto, el usuario debe dejar el modelo instalado
  por su cuenta; no hay experiencia de primera ejecución completa hasta el
  Model Manager (Sección 8).
- La verificación de privacidad de logs es puntual (tests de errores sin rutas),
  no una auditoría automática de todos los mensajes.
- La calificación de plataformas es la de las invariantes de AGENTS.md: lo no
  ejercitado es experimental (por ejemplo, CUDA real).

## Alternativas consideradas

### ASR cloud por defecto

Rechazada. Envía audio privado a terceros por defecto, exige claves y red, y
contradice el producto.

### Escuchar en `0.0.0.0` por defecto

Rechazada. Sin autenticación expondría los datos a la red local.

### Telemetría opt-out o comprobación automática de actualizaciones

Rechazadas. Cualquier señal saliente rompe la propiedad «solo la red que el
usuario confirmó».

### Token de acceso local obligatorio desde el inicio

Pospuesta. Añade fricción y una superficie de gestión de secretos sin
resolver aún el uso multiusuario. Se reevaluará junto con una futura exposición
LAN.

### Wrapper de escritorio (Electron/Tauri)

Pospuesto; ver [ADR-0001](0001-modular-monolith.md).

## Evidencia actual (2026-09-30)

| Requisito | Código o prueba |
| --- | --- |
| Host y puerto por defecto, `--host` explícito | `src/voz/interfaces/cli/main.py`; `tests/unit/test_cli.py` (reenvío de argumentos y traducción de comodines). No hay un test dedicado al valor por defecto de `--host`. |
| Sin descargas al construir/usar el provider | `tests/unit/test_asr_bootstrap.py::test_local_asr_composition_is_explicit_and_does_not_download`, `tests/unit/infrastructure/test_model_storage.py::test_resolve_never_downloads_and_rejects_missing_model` |
| Instalación con confirmación y revisión fijada | `test_install_requires_confirmation_before_constructing_downloader`, `test_install_rejects_unpinned_descriptor` |
| `local_files_only=True` al cargar el engine | `tests/unit/infrastructure/asr/test_faster_whisper.py`, `tests/contract/test_transcription_provider.py` |
| Rutas XDG, fuera del checkout | `tests/unit/test_xdg_paths.py`, `tests/unit/test_doctor.py::test_unwritable_path_fails` |
| Sin rutas del host en respuestas | `tests/integration/test_health_api.py`, `tests/integration/test_media_upload_api.py`, `tests/integration/test_media_stream_api.py`, `test_schema_and_adapters_never_persist_host_paths` |
| Diagnóstico sin rutas y sin cargar modelos | `tests/unit/test_doctor.py::test_redact_hides_absolute_paths` |
| Errores genéricos sin traceback | `tests/integration/test_media_upload_api.py::test_unexpected_failure_is_generic_without_traceback` |
| Búsqueda de clientes cloud o telemetría en `src/voz`, `apps/web/src` y el bundle | Revisión manual con `grep` el 2026-09-30: sin resultados; solo URLs de espacios de nombres XML y del texto de error de React en el bundle. No es un test automático. |

## Verificación

Esta decisión se considera respetada cuando:

- `voz` sin opciones escucha solo en `127.0.0.1`;
- ninguna ruta de ejecución normal abre una conexión a Internet, salvo la
  instalación de modelo confirmada explícitamente;
- ningún provider cloud existe sin selección explícita, aviso y gestión de
  claves fuera de SQLite y logs;
- ninguna respuesta HTTP contiene rutas absolutas del host;
- la base de datos, los medios y los modelos residen bajo XDG;
- cualquier cambio que amplíe la superficie de red actualiza esta ADR.

**Pendiente para reforzar la verificación (planificado):** test del valor por
defecto de `--host`, advertencia al enlazar fuera de loopback y un test que
falle si un módulo de `src/voz` importa un cliente HTTP o SDK cloud sin ADR
aprobada.
