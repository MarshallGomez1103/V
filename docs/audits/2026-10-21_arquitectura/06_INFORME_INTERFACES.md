### INFORME — interfaces

**Metadatos:** fecha 2026-10-21 · HEAD 96284c5 · rutas revisadas: `src/voz/interfaces/api/`, `src/voz/interfaces/cli/`, `src/voz/bootstrap.py`, `src/voz/__init__.py`, `src/voz/infrastructure/server_token.py`, `src/voz/infrastructure/desktop_shortcut.py`; `src/voz/static/` solo en cómo se sirve · alcance: inspección estática (grep, lectura) · límites: sin ejecución de tests, servidores ni peticiones; los comportamientos de tiempo de ejecución son hipótesis.

**Cobertura:** asignados 90 · superficial 57 · profunda 33 · omitidos 0 · ~líneas 6838 Python (+5677 en `static/`, minificado, no auditado) · dependencias principales: FastAPI 0.141.1, Starlette 1.6.0, uvicorn 0.52.4 (`uv.lock`), SQLAlchemy, Typer.

#### 1. Responsabilidades y dependencias

- `create_app()` (`src/voz/bootstrap.py:328-902`) es la única raíz de composición: construye repositorios desde un `Engine` (`bootstrap.py:361-375`), casos de uso (`:474-485`, `:608-683`), routers por fábricas `create_*_router(...)` (`:732-895`) y el ciclo de vida (`:685-717`). La inyección es manual por constructor; no hay contenedor.
- 21 routers HTTP (20 fábricas y `health.py`, que usa un `APIRouter` de módulo, `health.py:10`) y 3 middlewares ASGI (`bootstrap.py:727-731`).
- Excepciones a "routers contra puertos": `create_jobs_router` recibe `JobRunner` concreto (`jobs.py:249`); `create_media_stream_router` recibe `FileSystemMediaStorage` concreto (`media_stream.py:21`, `:30-31`).

#### 2. Arquitectura hexagonal

- Dependencias: el dominio no importa frameworks (búsqueda sin coincidencias en `src/voz/domain`). Verificado.
- Los routers delegan en casos de uso en la mayoría de rutas (`jobs.py:272-301`, `projects.py`, `speakers.py`).
- **Violaciones comprobadas (lógica de negocio en el router):**
  - `job_views.py:18-37` `eta_seconds`: modelo de extrapolación del tiempo restante.
  - `providers.py:177-180`: regla de consentimiento (solo URL no loopback) decidida antes del caso de uso.
  - `synthesis.py:234-286` `options()`: filtra qué modelos se ofrecen (registrados, instalados, runtime listo, voces).
  - `segments.py:51`: la vista retiene los tiempos de palabra si el segmento está editado.
  - `openai_compat.py:39` (`DEADLINE_SECONDS=300`) y `compatible_audio.py:75` (`timeout_seconds=300.0`): dos fuentes de la misma política.
  - `jobs.py:68` y `:107-138` (límite de hablantes); `jobs.py:322-334` ensambla checkpoints.
- **Violación comprobada (acoplamiento a infraestructura):** `media_stream.py:21` importa el adaptador y `:41` resuelve la ruta física dentro del router. La ruta no sale al navegador, pero el router conoce el adaptador.
- CLI: importa infraestructura directamente (`cli/main.py:24-30`, `cli/doctor.py:18-21`, `cli/diagnostics_bundle.py:24-25`). Es una entrada de primer nivel; se anota como baja (sospecha de bypass del composition root).

#### 3. Diseño y mantenibilidad

- `create_app` (`bootstrap.py:328-902`, ~570 líneas) mezcla cableado, selección de proveedores (`provider_for`, `:489-526`, cadena de `if` por id), ciclo de vida y closures. Cohesión baja; separar por dominio es una pregunta para arquitectura, no un cambio de este informe.
- Duplicación: la máquina de estados SSE aparece dos veces (`job_events.py:66-86`, `synthesis.py:406-430`); `_sse` duplicado (`synthesis.py:193-197`, con comentario `ponytail:`).
- Tres proyecciones del mismo job: `job_views.py:54-69`, `jobs.py:191-219` (misma firma de nombre, distinta) y el cierre `view` de `bootstrap.py:610-616`; riesgo de divergencia que `job_events.py:58-59` ya reconoce.
- Constante `X-VOZ-Action` repetida en 5 módulos (`shutdown.py:15`, `desktop_shortcut.py:14`, `projects.py:32`, `providers.py:49`, `synthesis.py:57`) y regex de token duplicada (`server_auth.py:14`, `server_token.py:9`).
- `openai_compat.py:93-195` implementa un parser multipart manual (~100 líneas) sobre `email`; decisión deliberada, pero es una superficie que requiere pruebas de borde.

#### 4. Concurrencia, errores y recursos

- **Estado mutable:** no hay estado global de módulo relevante (`LOOPBACK_HOSTS`, constantes `Final`, `_READINESS_OPEN` inmutables). Sí hay estado mutable en closures de `create_app`: `other_providers` (`bootstrap.py:487`, `:525`) y `diarization_engines` (`:547`, `:557`, `:572`, `:713-715`), mutados desde hilos de trabajo y del threadpool sin lock. `on_removed=drop_diarization_engine` (`:829`) se ejecuta desde una petición. (sospecha de carrera)
- **SSE (jobs):** `job_events.py:66-86` emite un `job` inicial, sondea cada 0.5 s en hilo (`anyio.to_thread`), emite `job` solo si cambia la huella y `: ping` cada 15 s (`:28`, `:83-85`); `end` al terminal. `is_disconnected()` se consulta solo al inicio de cada vuelta (`:71`).
- **Last-Event-ID y reconexión:** no hay `id:` ni `retry:` (`job_events.py:32-34`) y no existe `Last-Event-ID` en `src/` (búsqueda sin coincidencias). Cada conexión recibe un snapshot completo, así que la reconexión es idempotente por estado sin reproducir eventos. El cliente (`apps/web/src/api/jobEvents.ts:27`, `:60-67`) solo informa de error si `EventSource` queda `CLOSED`; un corte transitorio no tiene estado visible de "reconectando". Lo mismo en `synthesis.py:406-430`.
- **Cancelación:** `POST /api/jobs/{id}/cancel` → `runner.cancel` (`jobs.py:314-320`); compat usa `threading.Event` con sondeo de desconexión cada 20 ms y deadline de 300 s (`openai_compat.py:249-293`).
- **Errores:** códigos estables `{"detail":{"code","message"}}` (`errors.py:8-15`). Catch-all en importación de medios (`media.py:229-235`) y compat (`openai_compat.py:405-410`).
- **Recursos:** `media.py:188-199` escribe en disco con `os.fdopen`/`write` dentro de `async def` (bloquea el event loop). `ClientDisconnect` no se trata en `media.py:104-120` (hipótesis: 500 en log). `openai_compat.py:76-90` acumula el cuerpo completo en memoria (hasta 26 MiB). No hay límite global de tamaño de cuerpo para JSON; uvicorn se lanza sin `limit_concurrency` (`cli/main.py:264-273`, valor por defecto `None`, `uvicorn/config.py:225`).

#### 5. Seguridad y privacidad

- **Host:** `host_guard.py:52-61` (filtra por `Host`, cubre WebSocket, 400 `host_not_allowed`). Verificado por lectura; ADR-0006 y `docs/api/README.md`.
- **Origen y token:** `server_auth.py:77-147` solo está activo con token. Con token: Bearer, o Basic `v:token` que exige `Origin` igual al del servidor (`:137-147`) y `Sec-Fetch-Site` same-origin/none (`:131-135`); comparación con `hmac.compare_digest` (`:129`).
- **Sin token (defecto loopback):** no hay validación de `Origin` ni de `Sec-Fetch-Site` en ningún método (`server_auth.py:77-80` no actúa). No hay CORS (búsqueda), así que el navegador no lee respuestas cruzadas, pero sí envía peticiones "simples". Véase INTERFACES-01.
- **Protección de rutas y archivos:** identificadores UUID; no se devuelven rutas físicas (`synthesis.py:117-120`, `media_stream.py:59-67`). Descargas con nombres saneados (`synthesis.py:153-156`, `export.py:47-49`). Subidas: nombre sin separadores (`media.py:132-156`), staging `0700` con UUID y `rmtree` en `finally` (`media.py:104-119`, `:181-185`), límite de 8 GiB (`:37`) con control de `Content-Length` (`:159-164`) y en streaming (`:196-198`).
- **Cabeceras:** CSP estricta (`security_headers.py:8-13`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `CORP: same-origin`, `Permissions-Policy: microphone=(self)` (`:18`). Sin CORS ni HSTS, correcto para HTTP local.
- **Red:** bind por defecto `127.0.0.1:8765` (`cli/main.py:37-38`); no loopback exige `--auth-token-file` (`:228-231`); aviso de HTTP sin cifrar (`:124-131`); el wildcard añade nombres e IPs locales a la lista de hosts (`:134-139`).
- **Token:** 256 bits (`server_token.py:26`), archivo `0600` con `O_EXCL`, sin seguir enlaces y con verificación de modo (`:19-57`); el modo no se verifica en Windows (`:46`, `os.name != "nt"`). `voz auth-token --output` acepta cualquier ruta sin comprobar que esté fuera del repo (`cli/main.py:368-375`; `cli/lab.py:26` sí usa `outside_checkout`).
- **Ruta absoluta al navegador:** `api/desktop_shortcut.py:27` devuelve `location()`, que abrevia con `~/` solo bajo HOME; fuera de HOME devuelve la ruta absoluta (`infrastructure/desktop_shortcut.py:68-69`). Contradice la regla de AGENTS ("no devolver rutas absolutas"). Baja.
- **Efectos de red en diagnóstico:** `cli/main.py:335` llama `prepare_ffmpeg()` en el callback raíz, antes de cada subcomando, incluidos `doctor` y `auth-token`. Puede descargar FFmpeg (`infrastructure/audio/ffmpeg_tools.py:108-110`), con sha256 fijado (`:184-190`). Baja.
- **Subprocesos sin timeout:** `infrastructure/desktop_shortcut.py:56-58`, `:269-275` (gio), `:332` (mac), `:378-389` (PowerShell) no pasan `timeout=`; `refresh()` corre en el lifespan (`bootstrap.py:698`). Baja/media (hipótesis de arranque bloqueado).
- **Borrado guiado por marcador:** `infrastructure/desktop_shortcut.py:238-241` acepta `path == recorded` leído del marcador de estado del usuario. Baja.

#### 6. Pruebas y evidencias

- Hay pruebas por módulo, no ejecutadas: host (`tests/integration/test_host_guard.py`), auth ASGI (`tests/unit/test_server_auth.py`, `tests/integration/test_server_auth_wiring.py`), SSE (`tests/integration/test_job_events_api.py:270`, `:300`), apagado (`tests/integration/test_shutdown_api.py`, `tests/e2e/test_cli_shutdown.py`), subida y stream (`test_media_upload_api.py`, `test_media_stream_api.py`), compat (`tests/unit/test_openai_compat_api.py`), token (`tests/unit/infrastructure/test_server_token.py`), escritorio (`tests/unit/infrastructure/test_desktop_shortcut.py`).
- Huecos aparentes (por búsqueda): WebSocket solo se prueba a nivel ASGI directo (`tests/unit/test_server_auth.py:301`, `:390`); sin prueba de apagado con SSE o descarga abiertos; sin prueba de petición cruzada sin token; sin prueba de `ClientDisconnect` en subida.

#### 7. Preparación para STT en tiempo real

- Hoy: SSE solo para progreso (`docs/architecture/02-contenedores.md:77`, "no WebSocket"); el audio entra como cuerpo completo (`media.py`) o multipart completo (`openai_compat.py`). No hay entrada incremental.
- WebSocket: `host_guard.py:52-61` y `server_auth.py:77-86` ya tratan el scope `websocket`, pero no hay rutas WebSocket y falta la librería. `uv.lock` y `.venv` no tienen `websockets` ni `wsproto`; uvicorn rechaza el upgrade con "No supported WebSocket library" (`.venv/.../uvicorn/protocols/http/h11_impl.py:157-161`). Añadirla es una dependencia nueva que requiere aprobación.
- Preguntas abiertas (sin decidir):
  - Q1. WebSocket con PCM binario y control JSON: bidireccional y con resultados parciales en el mismo canal. Exige validar `Origin` en el handshake, porque no está sujeto a CORS y una página ajena podría leer transcripciones (hoy no hay lectura cruzada).
  - Q2. Subida en streaming (`request.stream()` ya existe en `media.py:193`) con resultados por SSE: el navegador necesita cuerpos en streaming, que en Chromium parecen requerir HTTP/2 (hipótesis, no verificado) y uvicorn sirve HTTP/1.1.
  - Q3. Segmentos cortos idempotentes (`seq`) con resultados por SSE: tolera reconexión y conserva el preflight; coste de latencia por petición a medir.
  - Q4. WebRTC DataChannel: sobrecoste grande para un modelo loopback; se lista sin recomendar.
  - Q5. Presupuesto de latencia y tamaño de bloque: `ROADMAP.md:608-621` (S17.05) no los define.
  - Q6. Reanudación tras corte: requiere número de secuencia y ventana de retención de audio, que choca con la regla de privacidad de AGENTS.
  - Q7. Nube en streaming: consentimiento explícito por sesión (regla de AGENTS).

#### 8. Top 5 hallazgos

| ID | Severidad | Hallazgo | Evidencia | Impacto | Recomendación |
|---|---|---|---|---|---|
| INTERFACES-01 | media | Sin token, peticiones simples de origen cruzado alcanzan rutas con efectos; `/v1/audio/transcriptions` crea proyecto, medio y trabajo persistentes | `server_auth.py:77-80`; `openai_compat.py:439`; `jobs.py:384-386`; `providers.py:264`; `model_tasks.py:104`; `synthesis.py:451`; `compatible_audio.py:224` | CSRF ciego: contamina la biblioteca y consume CPU; no lee datos | Decidir si métodos no seguros exigen `Origin`/`Sec-Fetch-Site` también sin token (ADR-0006) |
| INTERFACES-02 | media | Lógica de negocio en routers: ETA, consentimiento, filtro de modelos, retención de tiempos, deadline duplicado | `job_views.py:18-37`; `providers.py:177-180`; `synthesis.py:234-286`; `segments.py:51`; `openai_compat.py:39` vs `compatible_audio.py:75` | Reglas duplicadas o fuera de los casos de uso; riesgo de divergencia | Investigar qué reglas pasan a application/domain; el router solo traduce |
| INTERFACES-03 | media | Apagado bloqueable: uvicorn espera conexiones y tareas sin límite; `ModelTaskRunner.stop()` hace `join()` sin timeout; el lifespan corre después del drenaje | `.venv/.../uvicorn/server.py:282-317`; `cli/main.py:264-273`; `application/model_tasks.py:182-196`; `bootstrap.py:707-711` | (hipótesis) Ctrl+C o `POST /api/shutdown` no termina con SSE abierto o descarga en curso | Medir con prueba manual de SSE abierto más descarga; decidir `timeout_graceful_shutdown` y el límite de `join` |
| INTERFACES-04 | media | WebSocket no operativo: los middlewares tratan el scope, pero falta librería WS y no hay rutas; las pruebas son ASGI | `uv.lock` (sin `websockets`/`wsproto`); `h11_impl.py:157-161`; `tests/unit/test_server_auth.py:301` | Bloquea la opción WebSocket de S17.02; añadirla requiere aprobación | Decidir el transporte de S17 en un ADR antes de añadir dependencias |
| INTERFACES-05 | baja | Acoplamiento a infraestructura en router y subprocesos sin timeout en el arranque | `media_stream.py:21`, `:41`; `infrastructure/desktop_shortcut.py:269-275`, `:378-389`; `bootstrap.py:698`; `api/desktop_shortcut.py:27` y `infrastructure/desktop_shortcut.py:68-69` | Acoplamiento; posible bloqueo del arranque; ruta absoluta fuera de HOME | Puerto de lectura para medios; `timeout=` en subprocesos; abreviar también fuera de HOME |

#### 9. No verificado

- No se ejecutó ningún test, servidor ni petición. Son hipótesis: CSRF simple (INTERFACES-01), bloqueo del apagado (03), reconexión SSE, `ClientDisconnect` en subida, bloqueo de arranque por subprocesos.
- `StaticFiles` (`bootstrap.py:896-901`): la protección contra recorrido de rutas se atribuye al diseño de Starlette; no se revisó su fuente.
- Comportamiento de navegadores (Basic cacheado con WebSocket o EventSource; streaming de cuerpos sobre HTTP/1.1): no verificado y sin red.
- Permisos del token en Windows (`server_token.py:46` omite la comprobación de modo).
- Bloques `_linux`, `_mac` y `_windows` de `infrastructure/desktop_shortcut.py`: revisadas solo sus llamadas a `subprocess`.
- Frontend: solo se leyó `apps/web/src/api/jobEvents.ts` para la reconexión; no auditado. `src/voz/static/`: no auditado, solo cómo se sirve.
- Si FastAPI 0.141.1 lee un cuerpo JSON completo antes de validar: no comprobado.
