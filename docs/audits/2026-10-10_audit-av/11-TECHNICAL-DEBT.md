# 11 · Deuda técnica clasificada

Clasificación: **P0** bloqueo crítico · **P1** corregir antes de ampliar · **P2** mejora planificada · **P3** opcional.

Estado de verificación: **verificado** (reproducido o confirmado por herramienta) · **parcial** (lectura de código o fuente secundaria, no reproducido) · **no verificado**.

Rutas relativas a la raíz del repositorio. Líneas según `git` en `1186908`.

**P0: ningún elemento verificado.** No hay defecto que impida usar el producto con los datos del propietario.

---

## P1 — corregir antes de ampliar

### AV-P1-01 · Acceso directo de escritorio con rutas absolutas no portables
- **Severidad**: P1. **Estado**: verificado (archivo real y código).
- **Archivo y línea**: `src/voz/infrastructure/desktop_shortcut.py:126-137` (`_linux`), `96-98` (`exists`).
- **Evidencia**: `~/.local/share/applications/voz.desktop` contiene `Exec="<repo-V>/Iniciar-Linux.sh"`, `Path=…/Voz`, `Icon=…/packaging/icons/voz.png`. Comando: `cat ~/.local/share/applications/voz.desktop`.
- **Impacto**: al mover o reinstalar el checkout, el icono y el lanzamiento fallan. `exists()` sigue devolviendo `True` porque solo comprueba el archivo `.desktop`, así que la UI miente.
- **Recomendación**: usar `Exec=voz` cuando VOZ esté instalado como herramienta; en modo checkout, regenerar el archivo al arrancar si la ruta registrada no coincide; `exists()` debe validar que el ejecutable de `Exec` existe.
- **Dependencias**: AV-P2-12 (desinstalación) se resuelve en el mismo corte.
- **Prueba de aceptación**: test que crea el acceso directo, mueve el `root` simulado y comprueba que `exists()` devuelve `False` y que tras arrancar se regenera; `desktop-file-validate` sin errores.

### AV-P1-02 · API local sin validación de cabecera `Host`
- **Severidad**: P1. **Estado**: parcial (lectura de código; no explotado).
- **Archivo y línea**: `src/voz/bootstrap.py:238` (`create_app`): no añade middleware. `docs/adr/0006-local-first-privacy.md:81-86`: "No hay autenticación. Loopback es el control de acceso."
- **Evidencia**: `git grep add_middleware -- src` sin resultados; el ADR no menciona DNS rebinding.
- **Impacto**: una página web maliciosa podría, si el usuario la visita mientras VOZ corre, hacer que su navegador resuelva un dominio controlado a `127.0.0.1` y leer la biblioteca, las transcripciones y los medios. Es el ataque clásico contra servicios locales sin validación de `Host`.
- **Recomendación**: `TrustedHostMiddleware` con `127.0.0.1`, `localhost` y `[::1]` más el puerto activo; rechazar otros `Host` con 400. Opcional: token efímero para operaciones de escritura.
- **Dependencias**: AV-P2-01 (LAN).
- **Prueba de aceptación**: `GET /api/health` con `Host: evil.example` → 400; con `Host: 127.0.0.1:8765` → 200.

### AV-P1-03 · El worker de jobs descarta excepciones sin registrarlas
- **Severidad**: P1. **Estado**: verificado (lectura).
- **Archivo y línea**: `src/voz/application/job_runner.py:312-324` (`_loop`), en concreto `except Exception:` y `pass` en la línea 319.
- **Evidencia**: el bloque captura cualquier `Exception` del `run_job` y no hace nada. El comentario dice "a persistence outage must not kill the only worker", que es correcto como objetivo, pero no deja rastro.
- **Impacto**: si falla la persistencia al terminar un job, el job puede quedar en estado no terminal sin que se vea en logs ni en la UI hasta el siguiente arranque.
- **Recomendación**: registrar con `logging.exception` (o equivalente) y, si es posible, marcar el job como `FAILED` con un código estable antes de seguir.
- **Dependencias**: AV-P2-13 (observabilidad).
- **Prueba de aceptación**: test que hace fallar `jobs.save` durante `run_job` y comprueba que queda un registro de log con el `job_id` y que el worker sigue procesando el siguiente job.

### AV-P1-04 · Documentación de estado desfasada respecto al código
- **Severidad**: P1. **Estado**: verificado.
- **Archivos**: `.ai/HANDOFF.md` (gitignored), `ROADMAP.md`, `CHANGELOG.md`.
- **Evidencia**:
  - `HANDOFF.md` dice "871d303", "1424 backend + 3 opt-in", "297 frontend" y "`main` va 10 commits por delante de `origin/main` (SIN push)". Realidad: `1186908`, 1612 + 3 opt-in, 543 frontend, sincronizado con origin.
  - `ROADMAP.md` tiene su última edición en `fb5b0cc` (2026-09-30). Sin filas ni IDs para biblioteca, renombrar/eliminar, `rediarize` ni Material 3: `grep -c -i 'rediarize\|/api/library' ROADMAP.md` → 0.
  - `CHANGELOG.md` `[Unreleased]`: 0 coincidencias con biblioteca, renombrar, Material, PWA, recalcular.
- **Impacto**: un arquitecto o agente que lea estos archivos tomará decisiones sobre datos incorrectos (por ejemplo, creerá que faltan tests o que el push está pendiente).
- **Recomendación**: actualizar en un solo corte documental: `HANDOFF.md` con HEAD actual, filas v3 en `ROADMAP.md` con IDs nuevos (sin renumerar), entrada en `CHANGELOG.md`. AGENTS.md exige que ROADMAP se actualice en la misma edición que la verificación.
- **Dependencias**: ninguna.
- **Prueba de aceptación**: `grep` de los IDs v3 en `ROADMAP.md`; HANDOFF cita el HEAD real; `CHANGELOG.md` lista la biblioteca y la piel Material 3.

### AV-P1-05 · Filas de segmento en blanco tras seek y autoscroll (pendiente de verificación)
- **Severidad**: P1 si se confirma. **Estado**: no verificado.
- **Archivo**: `apps/web/src/components/SegmentList.tsx` (`SegmentRow` memo en la línea 163; `content-visibility` según ROADMAP TRANSCRIPT-VIEW-001).
- **Evidencia**: `.ai/HANDOFF.md`: "Verificar a mano en navegador real: filas de segmento en blanco tras seek+autoscroll (visto solo en Chrome headless; content-visibility)". No reproducido en esta auditoría porque no se cargó una transcripción.
- **Impacto**: el flujo de revisión (saltar a un segmento y leerlo) puede mostrar filas vacías.
- **Recomendación**: reproducir con una transcripción de prueba sintética (no la del propietario) en Chrome real; si se confirma, revisar `content-visibility` en el contenedor virtualizado.
- **Prueba de aceptación**: test de navegador (Playwright) que hace seek a 50 % de una lista de 2000 segmentos y comprueba que el texto del segmento activo es visible y no vacío.

---

## P2 — mejora planificada

### AV-P2-01 · Exposición LAN sin autenticación ni advertencia
- **Estado**: verificado. **Archivo**: `src/voz/interfaces/cli/main.py:148` (`uvicorn.Config(host=host)`), `156-161` (ayuda del `--host`, sin advertencia).
- **Impacto**: `voz --host 0.0.0.0` expone la API, los medios y las transcripciones a cualquier equipo de la red.
- **Recomendación**: mostrar advertencia clara al enlazar fuera de loopback; exigir confirmación o token antes de exponer (ADR-0006 lo tiene como planificado).
- **Prueba**: test que comprueba que el arranque con host no loopback imprime advertencia y que `--host 127.0.0.1` no la imprime.

### AV-P2-02 · Instalador de uv descargado con `curl | sh` sin versión ni checksum
- **Estado**: verificado. **Archivo**: `Iniciar-Mac.command:15`.
- **Recomendación**: fijar la versión de uv y comprobar SHA-256 antes de ejecutar; o pedir al usuario que instale uv una vez.
- **Prueba**: el lanzador falla si el hash no coincide (script de prueba con un servidor local).

### AV-P2-03 · Helper `_error` duplicado en siete módulos de API
- **Estado**: verificado. **Archivos**: `interfaces/api/desktop_shortcut.py:17`, `providers.py:133`, `segments.py:66`, `jobs.py:97`, `speakers.py:55`, `media_stream.py:78`, `media.py:134`.
- **Recomendación**: mover a `interfaces/api/errors.py` sin cambiar firmas ni códigos.
- **Prueba**: tests de API existentes siguen pasando; un test comprueba que la forma `{"detail": {"code","message"}}` se mantiene.

### AV-P2-04 · Constante `_UNSAFE_BIDI_CLASSES` duplicada
- **Estado**: verificado. **Archivos**: `infrastructure/media_storage.py:32` y `interfaces/api/media.py:39`.
- **Riesgo**: divergencia silenciosa entre validación de nombre y de almacenamiento.
- **Recomendación**: una sola definición (en un módulo compartido de texto).

### AV-P2-05 · Validadores de payload duplicados
- **Estado**: verificado (nombres repetidos en 2–7 módulos: `_error` aparte; `_text` ×4, `_optional_text` ×4, `_validate_offsets` ×3, `_invalid_audio` ×3, `_integer` ×3, `_validate_uuid` ×2, `_validate_text` ×2, `_uuid` ×2, `_require_uuid` ×2, `_real` ×2, `_object` ×2, `_mapping` ×2).
- **Recomendación**: consolidar en `application/validation.py` o similar, en un corte separado.

### AV-P2-06 · Cuatro enlaces de imagen rotos en el README
- **Estado**: verificado. **Archivo**: `README.md:85` (`04-job-terminado.png`, `05-forma-de-onda.png`) y `README.md:89` (`06-transcripcion.png`, `07-gestor-modelos.png`).
- **Evidencia**: `docs/assets/screenshots/` contiene `04-job-en-curso.png`, `05-job-terminado.png`, `06-reproduccion.png`, `07-transcripcion.png`, `11-gestor-modelos.png`. Ningún archivo `05-forma-de-onda.png`; no existe `07-gestor-modelos.png`.
- **Recomendación**: corregir las rutas. Comando de comprobación: script de enlaces relativos (ejecutado en esta auditoría: 4 rotos).

### AV-P2-07 · Bundle principal de 752 KB en un único chunk
- **Estado**: verificado. **Archivo**: `src/voz/static/assets/index-D57cQAlz.js`, 752 423 bytes; aviso de Vite > 500 kB.
- **Recomendación**: `lazy()` para Modelos, Proveedores, Exportar y Ajustes.
- **Prueba**: build muestra al menos dos chunks y el inicial baja por debajo de 500 kB.

### AV-P2-08 · Vulnerabilidad alta en dependencia transitiva de producción
- **Estado**: verificado con npm audit. **Paquete**: `source-map-js` 1.0.0–1.2.1, GHSA-68fv-2mgg-jv7q, CVSS 7.5, corrección disponible.
- **Recomendación**: actualizar la dependencia dentro del lock en un corte separado. **No se modificaron dependencias en esta auditoría.**
- **Prueba**: `npm audit --omit=dev` sin HIGH.

### AV-P2-09 · Responsividad limitada fuera de Home
- **Estado**: verificado por conteo; Home verificada a 390 px. **Evidencia**: 4 reglas `@media` en `src`.
- **Recomendación**: verificar Workspace, Modelos, Exportar y Hablantes a 390 px; añadir reglas donde falle.

### AV-P2-10 · Tests sin aislamiento global de XDG y `HOME`
- **Estado**: parcial. **Archivo**: `tests/conftest.py` (solo fija `VOZ_FFMPEG_AUTO_DOWNLOAD=0`).
- **Evidencia**: la suite pasó aislada, pero no se comprobó que sin aislamiento escriba en los datos reales; no se ejecutó en el entorno real a propósito.
- **Recomendación**: fixture `autouse` que apunte XDG y `HOME` a `tmp_path`.
- **Prueba**: ejecutar la suite con `HOME` a un directorio vacío y comprobar que no aparece nada fuera de `tmp`.

### AV-P2-11 · Excepciones amplias sin revisión
- **Estado**: verificado (conteo). **Evidencia**: 19 `except Exception` y 6 `except BaseException`. Los 4 `BaseException` revisados re-lanzan (correcto). Los `except Exception` de `job_runner.py` (319, 460, 502, 524, 547) y de `sherpa.py` (379, 407) no se revisaron uno a uno.
- **Recomendación**: revisar cada uno: capturar tipos concretos o registrar y re-lanzar.

### AV-P2-12 · Acceso directo sin función de desinstalación
- **Estado**: verificado. `desktop_shortcut.py` no tiene borrado; el único `unlink` es del PNG del `.app` de macOS (línea 192).
- **Recomendación**: `remove()` que borre el `.desktop` en ambas ubicaciones y el marcador.

### AV-P2-13 · Observabilidad limitada
- **Estado**: verificado. `logging` aparece en 4 archivos de `src/voz`; `print` a stderr en `infrastructure/audio/ffmpeg_tools.py:105`.
- **Recomendación**: log a archivo en el directorio de estado XDG con rotación; usar `logging` en el worker y en el puerto de descarga.

### AV-P2-14 · Plan Tauri sin ADR, con regla de AGENTS.md que lo prohíbe sin ADR
- **Estado**: verificado. `docs/packaging/tauri-plan.md:3` "plan, nada implementado". `AGENTS.md:62` "Do not introduce … Tauri unless a later accepted ADR explicitly authorizes it."
- **Impacto**: no hay violación (nada implementado), pero el plan avanza sin la decisión formal.
- **Recomendación**: redactar ADR de decisión antes de la fase 1 del plan.

### AV-P2-15 · Umbral de diarización medido con un único audio privado
- **Estado**: verificado en el repo; el audio no es público. **Archivo**: `src/voz/infrastructure/diarization/sherpa.py:50` (`DEFAULT_THRESHOLD = 0.4`).
- **Impacto**: el 0.4 puede no generalizar a otras grabaciones.
- **Recomendación**: medir con un corpus público o con sintéticos licenciados y documentar la metodología en `docs/benchmarks.md`.

### AV-P2-16 · Cloud sin verificación contra servicio real
- **Estado**: verificado en ROADMAP y HANDOFF. OpenAI y ElevenLabs solo tienen transporte falso. Riesgo, no defecto de código.
- **Recomendación**: una prueba manual con clave del propietario y un audio sintético, con aprobación explícita de gasto.

---

## P3 — opcional

### AV-P3-01 · Marcadores `ponytail:` deliberados
- **Estado**: verificado (conteo). 56 en `src/voz`, 2 en `tests`, 8 en `apps/web/src`.
- **Recomendación**: registrarlos con la skill `ponytail-debt` en un corte de documentación; no se ejecutó.

### AV-P3-02 · Lista global de handles de DLL
- **Estado**: verificado. `infrastructure/asr/faster_whisper.py:97` `_dll_directory_handles`.
- **Recomendación**: documentar como estado de proceso deliberado. Sin cambio funcional.

### AV-P3-03 · `bootstrap.py` grande (601 líneas)
- **Estado**: verificado. Composition root; `create_app` tiene ≈360 líneas de cableado.
- **Recomendación**: dividir por contexto solo si crece más.

### AV-P3-04 · Creación perezosa de `app` con `__getattr__`
- **Estado**: verificado. `bootstrap.py:596`.
- **Recomendación**: documentar la razón (uvicorn importa `voz.bootstrap:app` sin abrir la base).

### AV-P3-05 · Warning de dependencia en tests
- **Estado**: verificado. `StarletteDeprecationWarning`: TestClient usa httpx, ahora deprecado a favor de `httpx2`.
- **Recomendación**: revisar al actualizar dependencias de dev.

### AV-P3-06 · Componentes frontend grandes
- **Estado**: verificado (conteo). `SegmentList.tsx` 703, `ModelManager.tsx` 702, `SpeakersPanel.tsx` 509, `Library.tsx` 462, `Workspace.tsx` 420.
- **Recomendación**: dividir cuando se toquen; sin urgencia.

### AV-P3-07 · Descriptor de modelo sin revisión por defecto
- **Estado**: verificado. `infrastructure/asr/catalog.py:26` `faster_whisper_fast_descriptor(revision=None)` permite construir un descriptor sin revisión.
- **Recomendación**: quitar el valor por defecto o rechazar `None` en el constructor.

### AV-P3-08 · Glosario muestra ids crudos en "Lo usan"
- **Estado**: consta en HANDOFF. No verificado en navegador.
- **Recomendación**: mostrar el nombre del proyecto.

---

## Resumen de conteos

| Prioridad | Cantidad | Verificados | Parciales o no verificados |
|---|---|---|---|
| P0 | 0 | — | — |
| P1 | 5 | 3 (AV-P1-01, 03, 04) | 2 (AV-P1-02 parcial por lectura; AV-P1-05 no verificado) |
| P2 | 16 | 15 | 1 (AV-P2-10 parcial). AV-P2-16 es riesgo verificado en ROADMAP/HANDOFF, no defecto de código |
| P3 | 8 | 7 | 1 (AV-P3-08, consta en HANDOFF) |

Los 5 P1 están abiertos. Los dos que no están verificados de forma completa deben confirmarse antes de planificar el corte que los corrige.
