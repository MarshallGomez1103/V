# 10 · Resultados verificables de calidad, pruebas y seguridad

Todos los comandos se ejecutaron el 2026-10-10 sobre `1186908`, árbol limpio. Ningún comando modificó el árbol de trabajo (confirmado con `git status --porcelain | wc -l` → 0 al final).

## Aislamiento de los tests

`tests/conftest.py` solo fija `VOZ_FFMPEG_AUTO_DOWNLOAD=0`; **no aísla XDG ni `HOME` de forma global** (AV-P2-10). Para no tocar los datos reales del propietario, la suite se ejecutó con:

```
HOME=<scratch>/iso/home XDG_DATA_HOME=<scratch>/iso/xdg/data XDG_CONFIG_HOME=… XDG_CACHE_HOME=… XDG_STATE_HOME=…
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

Comprobación de que la base real no cambió: `~/.local/share/voz/voz.sqlite3` tenía 9 560 064 bytes y mtime 1791423706 antes y después de cada bloque de tests, y de la prueba de servidor.

## Resultados de checks oficiales

| Check | Comando | Resultado | Estado |
|---|---|---|---|
| Ruff lint | `.venv/bin/ruff check .` | "All checks passed!" | Verificado |
| Ruff format | `.venv/bin/ruff format --check .` | "376 files already formatted" | Verificado |
| Pyright estricto | `.venv/bin/pyright` | 0 errors, 0 warnings, 0 informations | Verificado |
| Pytest (aislado) | `.venv/bin/python -m pytest -q` (con XDG en scratch) | **1612 passed, 3 skipped, 1 warning in 42.19 s**, exit 0 | Verificado (log en `evidencia/pytest-isolated.log`) |
| Tests omitidos | — | `test_faster_whisper_real_opt_in.py:32` (requiere ruta de modelo), `test_job_runner_diarization.py:631` y `test_sherpa_provider.py:320` (requieren `VOZ_DIARIZATION_E2E_*`) | Opt-in, no ejecutados |
| Warning | — | `StarletteDeprecationWarning`: "Using httpx with starlette.testclient is deprecated; install httpx2" | Dependencia (AV-P3-05) |
| ESLint | `npm run lint` (`eslint . --max-warnings 0`) | exit 0 | Verificado |
| TypeScript | `npm run typecheck` (`tsc -b`) | exit 0 | Verificado |
| Vitest | `npx vitest run` | **59 archivos, 543 tests passed**, 44 s, exit 0 (log en `evidencia/vitest.log`) | Verificado |
| Build | `npx vite build --outDir <scratch> --emptyOutDir` | exit 0; aviso de chunk > 500 kB | Verificado |
| Reproducibilidad del bundle | `diff -rq <build> src/voz/static` | Sin diferencias: **idéntico byte a byte** | Verificado |
| Diff whitespace | `git diff --check HEAD~1 HEAD` | Sin salida, exit 0 (último commit) | Verificado parcialmente (no todo el historial) |
| Build en `npm run build` | No ejecutado tal cual | `vite.config.ts:15` tiene `outDir: '../../src/voz/static'` y `emptyOutDir: true`: ejecutar el script **reescribiría el bundle versionado**. Por eso se usó `--outDir` a scratch | Comportamiento documentado |

## Cobertura

No se calcula porcentaje de cobertura: no hay herramienta de cobertura configurada en `pyproject.toml` ni en `package.json`, y no se inventa un número.

## Tests por nivel (conteo de archivos)

| Nivel | Backend | Frontend |
|---|---|---|
| Unit | `tests/unit/**` (93 archivos `test_*.py`) | 59 archivos `*.test.ts(x)` junto a componentes, hooks y lib (total frontend) |
| Integration | `tests/integration/**` (48 archivos `test_*.py`, SQLite real, FFmpeg real, HTTP) | `App.flows.test.tsx`, `App.e2e.test.tsx` (simulados) |
| Contract | `tests/contract/**` (2 archivos) | — |
| E2E | `tests/e2e/**` (4 archivos: smoke CLI, shutdown, workspace, reinicio durante job) | — |
| Packaging | `tests/packaging/**` (2 archivos: versión y contenido del wheel) | — |

E2E real con modelo y GPU: no ejecutado (opt-in y requiere modelo).

## CI remoto (solo lectura, `gh run list` y `gh run view`)

| Run | Commit | Resultado | Jobs |
|---|---|---|---|
| 37177276110 | `1186908` | **success** | Frontend Node 22, Backend Python 3.12, Backend windows-latest, Backend macos-latest, Package wheel+sdist: todos success |
| 37176634829 | `3f4b03f` | success | — |
| 37157788192 | `9efd236` | success | — |
| 37157495600 | `050642a` | **failure** | — (arreglado en `9efd236`) |
| 37157175788 | `3b24eac` | **failure** | — |

Dos runs fallidos en `main` durante el trabajo de PWA y espera de UI en CI, corregidos después. Se registra porque demuestra fragilidad de los tests de UI bajo CI lento.

## Seguridad

### Auditoría de secretos — `scripts/audit-secrets.sh` (verificado)

| Modo | Resultado |
|---|---|
| `--tree-only` | **0 HIGH, 13 REVIEW**, exit 0 |
| Historial completo (42 commits) | **0 HIGH, 27 REVIEW**, exit 0; 84 commits de un solo autor con correo `noreply` |

Los REVIEW son: literales con forma de clave en `tests/unit/test_doctor.py` (fixtures falsas según la clasificación del script; **no se imprimieron valores**) y rutas personales en tests (`/home/...` de ejemplo). Ninguna clave real detectada.

### Dependencias

| Herramienta | Comando | Resultado |
|---|---|---|
| npm audit (producción) | `npm audit --omit=dev --json` (consulta al registro, sin datos del proyecto) | **1 HIGH**: `source-map-js` 1.0.0–1.2.1, GHSA-68fv-2mgg-jv7q (DoS por offsets de sourcemap indexado, CWE-1284, CVSS 7.5). Corrección disponible |
| npm audit (dev) | No ejecutado con dev | Pendiente |
| pip-audit / safety | No instalado | No instalado para no modificar el entorno: **no verificado** |
| Licencias de Python | No inspeccionadas con herramienta | Ver `NOTICE` del repo |

### Hallazgos de seguridad

| ID | Área | Hallazgo | Evidencia | Severidad | Estado |
|---|---|---|---|---|---|
| S-01 | Red local | Sin validación de cabecera `Host`: riesgo de DNS rebinding contra la API en loopback | `bootstrap.py` no añade middleware (`grep add_middleware` sin resultados); ADR-0006:81 "No hay autenticación. Loopback es el control de acceso" | P1 | Parcial: por lectura, no explotado |
| S-02 | Red | Sin autenticación; `--host` acepta cualquier dirección y expone toda la API a la red | `interfaces/cli/main.py:156-161` (`help="Bind address. Use a LAN address only when exposure is intentional."`), línea 148 `uvicorn.Config(host=host)`; ADR-0006:82 | P2 | Documentado; advertencia planificada |
| S-03 | Apagado | `POST /api/shutdown` exige cabecera personalizada `X-VOZ-Action: shutdown`, lo que fuerza preflight CORS que VOZ no contesta | `interfaces/api/shutdown.py` | Correcto | Verificado por lectura y test |
| S-04 | Borrado de proyecto | `DELETE /api/projects/{id}` exige `X-VOZ-Action: delete-project` | `interfaces/api/projects.py:32-33,156-163` | Correcto | Verificado por lectura |
| S-05 | Subprocesos | Ninguna llamada usa `shell=True` ni `os.system`; argumentos como listas | `grep -rn 'shell=True\|os.system'` sin resultados; ver `subprocess` en `04` | Correcto | Verificado por grep |
| S-06 | Subidas | Límite de 8 GiB, comprobación por `Content-Length` y por bytes recibidos, escritura en stream | `interfaces/api/media.py:36,170-206` | Correcto | Verificado por lectura y tests de API |
| S-07 | Secretos | Claves de proveedor fuera de SQLite y logs; `secrets.toml` 0600 atómico; `/api/providers` no devuelve la clave | ROADMAP CLOUD-SECRETS-001; `infrastructure/secrets.py`; `test_secrets.py` | Correcto | Verificado por tests; logs sin revisar |
| S-08 | Supply chain | Instalación de uv con `curl … install.sh \| sh` sin versión fijada ni checksum | `Iniciar-Mac.command:15` | P2 | Verificado por lectura |
| S-09 | Supply chain | Vulnerabilidad alta transitiva `source-map-js` | npm audit | P2 | Verificado con herramienta |
| S-10 | Privacidad cloud | El proveedor cloud se activa solo con clave y selección explícita; badge CLOUD; consentimiento | ROADMAP CLOUD-UI-001, OPENAI-004; ADR-0006 | Correcto | Verificado por tests y lectura |
| S-11 | Rutas | Respuestas sin rutas del host (salvo el acceso directo, que es local y no viaja al navegador) | ADR-0006:59 y tests "sin paths" (UI-PLAYER-001) | Correcto | Verificado por tests |
| S-12 | Traversal | Nombres de archivo seguros y anti-traversal en exportación; `safe_fs` con `dir_fd` y `O_NOFOLLOW` | `application/export/filenames.py`; `infrastructure/safe_fs.py` | Correcto | Verificado por tests |
| S-13 | Subida | Validación de tipo de contenido (415) y de nombre (255 caracteres, caracteres bidi peligrosos) | `interfaces/api/media.py:134-160` | Correcto | Verificado por lectura |

### Fuera de alcance de esta auditoría

- Ataques reales contra el servidor local (no se intentó ninguno, incluido DNS rebinding).
- Análisis de `safe_fs` en Windows (la CI corre los tests portables, no se revisó a fondo).

## Riesgos residuales

1. Tests de UI en CI sensibles a tiempo (dos runs fallidos de `main`).
2. Cloud nunca probado contra servicio real (`OPENAI-001`, `ELEVEN-*`: "experimental, no verificado contra el servicio").
3. Aislamiento de XDG en tests no garantizado globalmente (AV-P2-10).
4. Sin herramienta de cobertura ni de auditoría de dependencias Python.
