# 09 · Impacto y alternativas de la migración VOZ → AV

No se ejecutó ningún cambio de nombre. Todas las cifras son de `git grep` sobre el árbol trackeado (sin `static/`, que es un bundle compilado).

## Inventario del nombre actual (verificado)

| Medida | Resultado | Comando |
|---|---|---|
| Líneas con la palabra "voz" (sin distinguir mayúsculas) | 2 859 | `git grep -ciw voz -- . ':!src/voz/static'` (sumado) |
| Ocurrencias incluyendo identificadores, rutas y URLs | 3 001 | `git grep -ci voz` (sumado) |
| Líneas con import o ruta del paquete (`from voz`, `import voz`, `src/voz`, `voz-transcriber`) | 1 401 | `git grep -n 'voz-transcriber\|from voz\|import voz\|"voz"\|src/voz'` |
| Variables de entorno `VOZ_*` distintas | 27 (lista abajo) | `git grep -ohE 'VOZ_[A-Z0-9_]+' \| sort \| uniq -c` |
| URLs con "voz" | 3, todas en `<propietario>/voz` (README/CONTRIBUTING/SECURITY) | `git grep -ohE 'https?://[^ )"]*voz[^ )"]*'` |

Distribución por zona (líneas con "voz"): `tests/` 1 020; `apps/web/` 660; `src/voz/` 612; `docs/adr` 78; `docs/architecture` 55; `docs/install` 51; `VOZ_PLAN_MAESTRO.md` 47; `scripts/` 42; `packaging/` 38; `docs/api` 31; `docs/packaging` 24; `docs/development` 20; `README.md` 19; `ROADMAP.md` 18; `docs/design` 16; `docs/privacy` 11; `.github/` 9; `SECURITY.md` 8; `pyproject.toml` 7; `CHANGELOG.md` 6; `CONTRIBUTING.md` 5; `Iniciar-Windows.bat` 4.

## Superficies afectadas

| Superficie | Ejemplo actual | Coste de cambiar | Riesgo |
|---|---|---|---|
| Nombre de proyecto y distribución | `name = "voz-transcriber"` en `pyproject.toml` | Bajo | Ruptura de `uv tool install` ya documentado |
| Paquete Python | `src/voz/`, `from voz...` (≈1 400 líneas) | **Alto** | Tests, imports, `pyproject` (`packages = ["src/voz"]`), migraciones |
| Comando CLI | `voz` (`[project.scripts]`) | Medio | Usuarios y lanzadores |
| Variables de entorno | 27 `VOZ_*` | Medio | Scripts, CI, docs |
| Rutas XDG | `~/.local/share/voz/`, `~/.cache/voz/`, `~/.config/voz/` | **Alto** | Pérdida de datos del usuario si no hay migración |
| Base de datos | `voz.sqlite3` (9,5 MB en el equipo del propietario) | Alto | Requiere migración de archivo y de rutas guardadas |
| Formato JSON | `"format": "voz.transcript"` (`export/json_canonical.py:21`) | Alto | Archivos ya exportados dejarían de validar |
| Acceso directo de escritorio | `Name=VOZ`, `Exec=…/Iniciar-Linux.sh` | Medio | Ya roto al mover el checkout (AV-P1-01) |
| Identificador Flatpak | `dev.voz.Voz` (provisional, sin registrar) | Bajo ahora | Ninguno hasta publicar |
| Repositorio y URLs | `github.com/<propietario>/voz` | Medio | Redirecciones de GitHub, enlaces en CHANGELOG |
| Lanzadores | `Iniciar-Windows.bat`, `Iniciar-Mac.command` | Bajo | Usuarios que ya los tienen |
| Documentación y ADR | 78 líneas solo en ADR | Medio | Historial; los ADR no se reescriben |
| Textos de UI | "VOZ" en cabecera, i18n | Bajo | Ninguno |
| Tests | 1 020 líneas | Medio | Regresiones por reemplazo masivo |

## Estrategias

### A. Renombrar solo marca y repositorio

Cambiar textos visibles, README, cabecera de la UI y nombre del repositorio. Mantener `voz` como paquete, comando, variables, rutas y formato.

- **Ventajas**: cambio pequeño, sin riesgo para datos ni para código. Se revierte fácil.
- **Desventajas**: el paquete seguiría llamándose `voz` y los usuarios verían "AV" con comandos "voz". Confusión de marca a medio plazo.

### B. Renombrar marca y comando, manteniendo compatibilidad con `voz`

Nueva marca "AV" en UI, README y documentación. Nuevo comando `av`, con `voz` como alias que se mantiene al menos una versión mayor. Paquete Python: sin cambio en esta fase. Rutas XDG y `voz.sqlite3`: sin cambio, o migración solo de lectura (si `av` existe, leer ambas). Variables: aceptar `AV_*` además de `VOZ_*` y preferir `AV_*`. Formato JSON: sin cambio; añadir el nuevo nombre solo en documentación.

- **Ventajas**: la marca cambia sin tocar datos del usuario ni los archivos exportados. El comando nuevo llega sin romper scripts. Permite decidir la fase siguiente con uso real.
- **Desventajas**: dos nombres conviven durante una temporada. Hay que documentar el alias.

### C. Migración completa de nombres internos

Renombrar paquete Python, rutas XDG, base de datos, formato JSON, variables, comando y URLs de una vez, con migración automática de datos.

- **Ventajas**: coherencia total.
- **Desventajas**: coste alto (≈1 400 líneas de imports, pyproject, migraciones Alembic para renombrar la ruta del archivo de datos, backup y prueba de migración), riesgo de pérdida de datos del propietario, rompe archivos JSON ya exportados y no aporta nada que el usuario final note.

## Recomendación

**Estrategia B.** Motivos técnicos: cambia lo que el usuario ve (marca y comando) sin mover datos ni romper el formato canónico, y la migración de datos (C) no compensa su coste. El paquete `voz` y las rutas XDG se pueden renombrar en un corte posterior, cuando haya migración probada.

Condiciones previas:

1. Corregir AV-P1-01 antes del rename: el acceso directo ya usa rutas absolutas y el rename lo rompería en otro sitio.
2. Antes de elegir "AV" como nombre público, comprobar que no choque con otro producto ni marca en la misma categoría. "AV" es una sigla muy usada (audio-vídeo, antivirus), lo que dificulta la búsqueda y el posicionamiento. Esta es una consideración de nombre, no un dato verificado de marcas; requiere búsqueda propia del propietario.
3. Mantener `voz` como alias de `av` al menos hasta la primera release pública (S15.14 sigue pendiente de autorización).
4. Hacer el cambio en un solo commit de marca, con tests de compatibilidad: `voz` y `av` ejecutan lo mismo; `VOZ_*` y `AV_*` se leen ambos.

## Lista de variables `VOZ_*` (27)

`VOZ_WHISPER_CPP_BIN`, `VOZ_WORK`, `VOZ_FFMPEG_AUTO_DOWNLOAD`, `VOZ_FFMPEG_DIR`, `VOZ_EXTRAS`, `VOZ_PLAN_MAESTRO`, `VOZ_DIARIZATION_E2E_MODELS`, `VOZ_DIARIZATION_E2E_AUDIO`, `VOZ_OUT`, `VOZ_LAUNCHER`, `VOZ_ICON`, `VOZ_FASTER_WHISPER_MODEL_DIR`, `VOZ_CMD`, `VOZ_ROOT`, `VOZ_OPENAI_API_KEY`, `VOZ_FASTER_WHISPER_MODEL_SOURCE`, `VOZ_FASTER_WHISPER_MODEL_REVISION`, `VOZ_FASTER_WHISPER_MODEL_`, `VOZ_ELEVENLABS_API_KEY`, `VOZ_AUDIT_PATH_ALLOW`, `VOZ_API`, `VOZ_STATE`, `VOZ_DESKTOP_TOKEN`, `VOZ_DATA`, `VOZ_CONFIG`, `VOZ_CACHE`.

Nota: `VOZ_PLAN_MAESTRO` aparece como texto dentro de documentación, no como variable; `VOZ_FASTER_WHISPER_MODEL_` es un prefijo truncado en la búsqueda. `VOZ_DESKTOP_TOKEN` solo aparece en `docs/packaging/tauri-plan.md` y no está implementada.

## Datos del propietario que el rename debe respetar

- `~/.local/share/voz/voz.sqlite3` y `projects/`, `models/`, `uploads/`, `waveforms/` (ver `06`).
- Cache de Buzz: solo lectura; VOZ no escribe ahí y el rename no debe tocarlo (AGENTS.md y HANDOFF).
- Acceso directo `voz.desktop` en el escritorio y en `~/.local/share/applications`.
