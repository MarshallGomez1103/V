# 02 · Inventario del repositorio y matriz de funcionalidades

## Estado Git (verificado)

| Campo | Valor | Comando |
|---|---|---|
| Rama | `main` | `git status --short --branch` |
| HEAD | `1186908` 2026-10-03 "feat(ui): Material 3 como sistema de diseño alternativo en Ajustes" | `git log -1` |
| Remoto | `origin` (repositorio de GitHub) | `git remote -v` |
| Sincronía | `main...origin/main` sin ahead/behind | `git status` |
| Commits | 42 | `git rev-list --count HEAD` |
| Árbol | limpio (0 cambios) antes y después | `git status --porcelain \| wc -l` → 0 |
| Autores | 84 entradas con el correo `noreply` de GitHub; ninguna con correo institucional | `scripts/audit-secrets.sh` (sección INFO) |
| Directorio de notas internas | ignorado (`.gitignore:1`), sin archivos trackeados | `git ls-files <directorio> \| wc -l` → 0 |

Historial reciente relevante: `1186908`, `3f4b03f`, `c0c0160`, `d0399e0` (2026-10-03, v3); `3b24eac` (PWA, fase 0 de Tauri); `d34123e` y `c8511ca` (UI v2 y progreso por etapa); `57c52de` (Carbon). Dos runs de CI en `main` fallaron (commits `3b24eac` y `050642a`); el arreglo posterior es `9efd236` (health con 30 s en runners Windows lentos).

## Estructura (verificado con `find` y `wc`)

| Zona | Contenido | Tamaño |
|---|---|---|
| `src/voz/` | Backend Python: `domain`, `application` (+ `ports`, `export`), `infrastructure`, `interfaces` (api, cli), `bootstrap.py`, `static/` (bundle compilado) | 160 módulos, 23 797 líneas |
| `tests/` | unit, integration, contract, e2e, packaging, fixtures | 31 470 líneas Python |
| `apps/web/` | Frontend React 19 + Carbon 1.117 + Vite 8 | 24 239 líneas TS/TSX |
| `migrations/` | Alembic, 8 versiones (0001–0008) | — |
| `docs/` | ADR 0001–0008, arquitectura C4, API (9 archivos), instalación, privacidad, packaging, design | — |
| `packaging/` | AppImage, Flatpak (prototipos), icono, `voz.desktop` plantilla | — |
| `scripts/` | auditoría de secretos, checksums, reproducible build, install check, capturas | — |
| `.github/workflows/` | `ci.yml` (backend, backend portable Windows/macOS, frontend, package), `release-dry-run.yml` | — |
| Raíz | `Iniciar-Windows.bat`, `Iniciar-Mac.command`, `Iniciar-Linux.sh`, `pyproject.toml`, `uv.lock`, `ROADMAP.md`, `AGENTS.md`, `VOZ_PLAN_MAESTRO.md` | — |
| Directorio de notas internas (ignorado) | Estado (HANDOFF), lista de control, plan de la versión 3 y asignaciones | — |

Archivos mayores (verificado): `test_media_storage.py` 1006 líneas; `persistence/repositories.py` 923; `model_storage.py` 893; `job_runner.py` 731; `cli/bench.py` 679; `bootstrap.py` 601; `ffmpeg.py` 587. Frontend: `App.flows.test.tsx` 864; `SegmentList.tsx` 703; `ModelManager.tsx` 702; `SpeakersPanel.tsx` 509; `Library.tsx` 462; `Workspace.tsx` 420.

## Dependencias (verificado en `pyproject.toml` y `apps/web/package.json`)

Backend, dependencias base: `alembic>=1.14`, `fastapi>=0.115`, `sqlalchemy>=2.0`, `typer>=0.12`, `uvicorn>=0.30`. Extras: `asr-local` (faster-whisper ≥1.2.1, nvidia-cublas/cudnn cu12 en Linux y Windows), `diarization` (numpy, sherpa-onnx 1.13.8). Dev: httpx, pyright, pytest, ruff. Python `>=3.12` (`.python-version` 3.12). **Sin torch**, decisión consciente de ADR-0007.

Frontend: `@carbon/react 1.117.0`, `react 19.2.7`, `@material/material-color-utilities 0.4.0`, `@fontsource-variable/roboto-flex 5.3.0`. Dev: vite 8.2.0, vitest 4.1.10, eslint 10.8.0, typescript 5.9.3.

## Funcionalidades añadidas después del plan original

El plan maestro (`VOZ_PLAN_MAESTRO.md`) no menciona por palabra clave: **Material** (0), **Carbon** (0), **biblioteca** (0), **icono/escritorio** (0). Por tanto, son añadidas:

1. Piel Material 3 seleccionable en Ajustes (`apps/web/src/styles/m3/`, `theme/m3.ts`, `docs/design/material3.md`).
2. Home con biblioteca de transcripciones, renombrar y eliminar proyectos (`interfaces/api/library.py`, `application/library.py`).
3. Rutas por hash (`#/t/<id>`) y atrás/adelante (`apps/web/src/lib/navigation.ts`).
4. Recalcular hablantes sin re-transcribir (`application/rediarize.py`, `POST` de rediarize).
5. Acceso directo de escritorio creado desde Ajustes (`infrastructure/desktop_shortcut.py`, `interfaces/api/desktop_shortcut.py`).
6. Lanzadores de doble clic para Windows, macOS y Linux (`Iniciar-*`).
7. Botón de apagado desde la UI con cabecera `X-VOZ-Action` (`interfaces/api/shutdown.py`).
8. Volumen hasta 300 % con `GainNode` (`AudioPlayer.tsx:32,203`).
9. Exportación con vista previa en modal (`ExportDialog.tsx`).
10. Progreso por etapa con ETA y SSE (`job_events.py`, `useJobEvents.ts`).
11. Editor de transcripción con autosave y resolución de conflictos 409.
12. Interfaz IBM Carbon y español/inglés (`i18n/messages/*.ts`).
13. PWA instalable (manifest y iconos; `3b24eac`).
14. Prototipos AppImage y Flatpak (no en CI).
15. `voz doctor`, bundle de diagnóstico redactado, `voz bench` con WER/CER.
16. Glosario por proyecto con `hotwords` y keyterms cloud.
17. Perfiles de calidad `default` y `academic`, cola de revisión con flags.

Dentro del plan (no cuentan como añadidas): Buzz, whisper.cpp, OpenAI, ElevenLabs, sherpa-onnx, WhisperX (evaluado y descartado en ADR-0008), Model Manager, VAD, exportación TXT/MD/SRT/VTT/JSON.

## Matriz de funcionalidades

Leyenda — **Implementada**: hay código. **Probada**: hay tests y pasaron en esta auditoría (backend 1612 y frontend 543) o figuran en ROADMAP. **Operativa**: uso real verificado; se indica si fue en esta auditoría (A) o solo consta en ROADMAP/HANDOFF (R). Ningún "operativa" se marca sin evidencia.

| Funcionalidad | Implementada | Probada | Operativa | Evidencia | Problemas |
|---|---|---|---|---|---|
| Importar medio (subida en stream, SHA-256, ffprobe) | Sí | Sí | R (INGEST-*, E2E-001) | `interfaces/api/media.py`, `application/import_media.py`, tests `test_media_upload_api.py` | Límite 8 GiB (`media.py:36`) |
| Normalización FFmpeg a PCM 16 kHz mono | Sí | Sí | R (INGEST-NORM-001) | `infrastructure/audio/ffmpeg.py:64`, tests integration audio | — |
| ASR local faster-whisper (CPU) | Sí | Sí (con motor falso) | R | `infrastructure/asr/faster_whisper.py` | Smoke real opt-in omitido en esta auditoría |
| ASR local faster-whisper (CUDA) | Sí | Parcial | R (RTX 4060, BENCH-002) | `_preload_cuda_libraries` (faster_whisper.py:111) | Declarado "experimental" en README |
| ASR por chunks recuperable | Sí | Sí | R | `application/recoverable_transcription.py`, `chunked_transcription.py`, test e2e `test_restart_during_job` | — |
| Checkpoints en SQLite | Sí | Sí | R | `persistence/transcription_checkpoints.py`, migración 0002 | — |
| Cancelación de job | Sí | Sí | R | `job_runner.py:273`, `faster_whisper.py:329,336,353,375,431,434` | Granularidad por segmento dentro de un chunk |
| Progreso por etapa con ETA (SSE) | Sí | Sí | No re-verificado en navegador | `interfaces/api/job_events.py`, `JobScreen.tsx` | — |
| Model Manager (catálogo, descarga con SHA, borrado) | Sí | Sí | R (MODELS-*) | `model_storage.py`, `application/model_manager.py` | — |
| Importar modelos desde caché de Buzz (hardlink) | Sí | Sí | R (MODELS-BUZZ-001) | `infrastructure/buzz_cache.py` | — |
| whisper.cpp (CLI externo) | Sí | Sí (binario falso y fixture real JSON) | Parcial: CPU R; CUDA/Vulkan no verificados | `infrastructure/asr/whisper_cpp.py` | HANDOFF: CUDA/Vulkan sin verificar |
| Diarización local sherpa-onnx | Sí | Sí | R (DIAR-SHERPA-002) | `infrastructure/diarization/sherpa.py`, `worker.py` | Umbral 0.4 medido en un audio privado |
| Hablantes desde proveedor cloud | Sí | Sí (fakes) | No | `application/integrity`, `job_runner.py:528` | Nunca probado contra servicio real |
| Palabras con timestamps nativos | Sí | Sí | R (WORDS-001/002) | `infrastructure/asr/faster_whisper.py:529` | WhisperX no evaluado (ADR-0008) |
| Editar segmentos (autosave, 409) | Sí | Sí | R (SEGMENT-EDITOR-001, E2E-001) | `api/segments.py`, `useSegmentDrafts.ts` | HANDOFF: filas en blanco tras seek+autoscroll (no verificado aquí) |
| Hablantes: renombrar, fusionar, asignar | Sí | Sí | R (SPEAKERS-001/002) | `api/speakers.py`, `SpeakersPanel.tsx` | — |
| Hablantes: recalcular (rediarize) | Sí | Sí (`test_rediarize.py`, 457 líneas) | No en navegador | `application/rediarize.py` | Pendiente prueba real según el plan de la versión 3 |
| Biblioteca Home y renombrar/eliminar proyecto | Sí | Sí (`test_library_projects_api.py`, `Library.test.tsx`) | A (Home vacía renderiza) · flujo de borrado solo por tests | `components/Library.tsx`, `application/library.py` | Sin entradas reales en la auditoría |
| Exportar TXT/MD/SRT/VTT/JSON + vista previa | Sí | Sí (goldens) | Tests | `application/export/*`, `ExportDialog.tsx` | — |
| Forma de onda con zoom y reproductor | Sí | Sí (`Waveform.test`, `AudioPlayer.test`) | R (WAVEFORM-001) | `Waveform.tsx`, `AudioPlayer.tsx` | Volumen 300 % no verificado en navegador |
| Glosario por proyecto | Sí | Sí | R (smoke real "VOZ"/"presupuesto") | `project_glossary.py`, migración 0007 | HANDOFF: "Lo usan" muestra ids crudos |
| Perfiles de calidad default/academic | Sí | Sí | R (academic + VAD) | `quality_profiles.py` | Perfil academic sin medición (HANDOFF) |
| Flags de calidad y cola de revisión | Sí | Sí | R (QUALITY-*) | `quality_flags.py`, `ReviewQueue.tsx` | — |
| `voz bench` (RTF, RAM, VRAM, WER/CER) | Sí | Sí (`test_bench_cli.py`) | R (BENCH-002) | `interfaces/cli/bench.py` | No ejecutado (GPU pesada) |
| OpenAI y ElevenLabs | Sí | Sí (transporte falso) | No | `infrastructure/cloud/*` | Experimental; nunca contra servicio real |
| Estimación de coste cloud | Sí | Sí | No | `estimate_cloud_cost.py` | Precios fechados; sin verificar vigencia |
| Secretos de proveedor (env o `secrets.toml` 0600) | Sí | Sí (`test_secrets.py`) | No | `infrastructure/secrets.py` | — |
| CLI `voz`, `--no-browser`, `--host`, `--port` | Sí | Sí (`test_cli.py`, e2e smoke) | A (arranque con XDG aislado, health 200) | `interfaces/cli/main.py` | `--host 0.0.0.0` sin advertencia |
| `voz doctor` y bundle de diagnóstico | Sí | Sí (`test_doctor.py`, `test_diagnostics_bundle.py`) | R (DOCTOR-CLI-001) | `interfaces/cli/doctor.py`, `diagnostics_bundle.py` | No ejecutado en esta auditoría |
| Acceso directo de escritorio desde Ajustes | Sí | Sí (tests unit e integration) | Existe en el equipo del propietario con rutas absolutas | `infrastructure/desktop_shortcut.py` | AV-P1-01; sin función de eliminar |
| Lanzadores doble clic (Win, Mac, Linux) | Sí | Parcial (CI portable Windows/macOS) | No en hardware real | `Iniciar-*`, `ci.yml` | Documentado como no usado a mano |
| Apagado desde la UI | Sí | Sí (`test_shutdown_api.py`, e2e) | A (código; no pulsado) | `interfaces/api/shutdown.py` | — |
| PWA instalable | Sí | Parcial | No verificada en esta auditoría | `public/manifest.webmanifest`, iconos | — |
| Piel Material 3 y temas/acentos | Sí | Sí (`m3.test.ts`, `appearance.test.ts`) | Capturas del repo (no re-verificadas) | `styles/m3/`, `theme/*.ts` | — |
| i18n es/en | Sí | Sí (`i18n.test.ts`) | A (Home en inglés con el navegador en inglés) | `i18n/*` | — |
| Build reproducible y paquete wheel/sdist | Sí | Sí (CI `package`) | CI verde; no reejecutado aquí | `scripts/check-reproducible-build.sh` | — |
| AppImage / Flatpak | Prototipo | No en CI | Medido según PKG-006 | `packaging/appimage`, `packaging/flatpak` | Sin release |

## Verificación de este inventario

- Conteo de módulos y aristas: `evidencia/import_graph.py` (salida: 160 módulos, 488 aristas).
- Conteo de tests: `evidencia/pytest-isolated.log` (1612 passed, 3 skipped).
- Conteo de frontend: `evidencia/vitest.log` (59 archivos, 543 tests).
