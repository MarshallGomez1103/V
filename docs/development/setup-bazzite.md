# Desarrollo de VOZ en Bazzite

Esta guía prepara un entorno de desarrollo sin modificar la imagen base de
Bazzite. Los comandos de la Opción A se ejecutaron tal cual en un checkout limpio
(ver [Verificado en Bazzite](#verificado-en-bazzite)); el estado de cada
funcionalidad sigue en [ROADMAP.md](../../ROADMAP.md). Para **instalar** VOZ como
usuario, sin checkout de desarrollo, usa [../install/linux.md](../install/linux.md).

## Principios para Bazzite/Fedora Atomic

- Evitar `rpm-ostree install` para herramientas ordinarias de desarrollo.
- Preferir herramientas en espacio de usuario o un contenedor Distrobox.
- No usar Docker/Podman como requisito para ejecutar VOZ con GPU.
- Mantener modelos y datos en los directorios XDG del usuario, nunca dentro de
  una imagen de contenedor o del repositorio.
- No instalar Whisper ni descargar modelos durante el bootstrap del skeleton.
- No reiniciar, rebasar la imagen del sistema ni cambiar drivers como parte de
  esta guía.

## Requisitos del bootstrap

Comprueba primero qué está disponible; no reinstales herramientas que ya
funcionan.

```bash
git --version
uv --version
node --version
npm --version
```

Para importar y normalizar audio hacen falta `ffmpeg` y `ffprobe` (los tests de
integración y E2E se saltan solos si faltan; la UI arranca sin ellos):

```bash
ffmpeg -version
ffprobe -version
```

Versiones objetivo del proyecto:

- Python 3.12, administrado por `uv`;
- Node.js compatible con la versión declarada por el frontend;
- npm usando el lockfile versionado.

No se debe depender del Python del sistema ni ejecutar `sudo pip install`.

## Opción A: herramientas de usuario

Esta es la ruta más corta cuando `uv`, Node y npm ya están disponibles en el
usuario. Desde la raíz del checkout:

```bash
uv sync --all-groups --all-extras
cd apps/web
npm ci
npm run build
cd ../..
uv run pytest
uv run voz --no-browser
```

La URL es `http://127.0.0.1:8765`. `--all-extras` instala también `asr-local`
(`faster-whisper`, cuBLAS/cuDNN, unos 2,6 GB) y `diarization` (`sherpa-onnx`):
**hace falta** porque `httpx`, que usan los tests HTTP (`TestClient`), solo llega
hoy de forma transitiva por `huggingface-hub`. Con solo `--all-groups`, `uv run
pytest` se interrumpe al recolectar `tests/e2e/test_workspace_flow.py`,
`tests/integration/test_jobs_memory_guard_api.py` y
`tests/integration/test_model_tasks_api.py` con `No module named 'httpx'`. Si
quieres un entorno mínimo, añade `httpx` al grupo `dev` de `pyproject.toml`.

## Opción B: Distrobox de desarrollo

Usa Distrobox cuando prefieras aislar toolchains o dependencias multimedia. La
carpeta de trabajo y los directorios XDG siguen perteneciendo al usuario del
host.

Ejemplo conceptual:

```bash
distrobox create --name voz-dev --image fedora:latest
distrobox enter voz-dev
```

Dentro del contenedor instala únicamente los prerequisitos de desarrollo que
falten, siguiendo la documentación oficial de cada herramienta, y luego ejecuta
los mismos comandos de la Opción A. No guardes modelos en capas del contenedor.

Las pruebas con CUDA deben tratarse como una actividad separada: primero se
verifica que el contenedor ve la GPU y luego se instala el stack declarado por
el proyecto. No se debe cambiar el driver del host para acomodar una dependencia
sin una decisión explícita y evidencia del problema.

## Desarrollo con frontend y backend separados

Durante desarrollo, dos terminales pueden ejecutar los procesos por separado.
Los scripts exactos quedan sujetos al bootstrap:

Terminal 1:

```bash
uv run voz --no-browser
```

Terminal 2:

```bash
cd apps/web
npm run dev
```

El frontend debe usar la configuración de desarrollo versionada para contactar
la API local. No codifiques rutas absolutas ni direcciones LAN.

## Comprobaciones de calidad

Backend:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

La verificación limpia de la Sección 1 exige probar desde un checkout nuevo o un
entorno vacío. Crear archivos no basta: `voz` debe iniciar, `/api/health` debe
responder y la Home debe cargarse en `127.0.0.1`. Registra el entorno y los
comandos realmente ejecutados en el handoff local antes de marcar S1.22.

## Directorios de ejecución

VOZ deberá respetar estas ubicaciones Linux:

```text
~/.config/voz/                      (reservado; aún no se escribe)
~/.local/share/voz/voz.sqlite3      (+ -wal y -shm)
~/.local/share/voz/projects/<id>/originals/ y derivatives/
~/.local/share/voz/models/
~/.cache/voz/                       (uploads/, downloads/, waveforms/)
~/.local/state/voz/backups/         (copias previas a migrar la base)
```

La tabla completa y quién escribe cada ruta están en
[ADR-0002](../adr/0002-sqlite-persistence.md).

Estos datos no se versionan. Un entorno de prueba debe poder redirigir las
variables XDG a un directorio temporal para no contaminar datos reales.

## Resolución de problemas del bootstrap

### `uv` usa un Python incorrecto

Comprueba la versión resuelta con `uv run python --version`. Corrige la
declaración del proyecto o permite que `uv` obtenga Python 3.12; no sustituyas el
Python del host.

### El puerto 8765 está ocupado

Comprueba el proceso existente y usa el flag documentado:

```bash
uv run voz --no-browser --port 9000
```

No termines procesos desconocidos automáticamente.

### La UI no carga

Verifica por separado:

1. que `/api/health` responde;
2. que el build del frontend termina sin errores;
3. si se ejecuta en modo desarrollo o como bundle servido por la API;
4. que la URL usa `127.0.0.1` y el puerto mostrado por la CLI.

### FFmpeg no está disponible

Esto bloquea la importación de audio, no el arranque de la UI. Registra el
diagnóstico (`uv run voz doctor`) y elige una instalación de usuario o Distrobox.
No añadas layering del sistema base como respuesta automática.

## Criterio de salida

El setup de Bazzite se considera verificado únicamente cuando un checkout limpio
permite instalar dependencias, ejecutar las comprobaciones relevantes, iniciar
`voz` y abrir la UI local. Esa verificación está hecha y registrada abajo; repítela
y actualiza la fecha cuando cambien las dependencias o el flujo.

## Verificado en Bazzite

**Fecha:** 2026-09-30 (S15.10). **Máquina:** Bazzite `bazzite-nvidia-open`
(Fedora 44), `uv 0.12.21`, Node 22.22.3, npm 10.9.8, FFmpeg 8.1.3.

Checkout limpio (`git clone` del commit `435ed0a`), con `XDG_*` y
`UV_PROJECT_ENVIRONMENT` en un directorio temporal; red solo hacia PyPI.

| Comando | Resultado |
| --- | --- |
| `uv sync --all-groups` | instala en unos 8 s, pero `uv run pytest` falla al recolectar (falta `httpx`, ver Opción A) |
| `uv sync --all-groups --all-extras` | instala en unos 4 min con la caché vacía |
| `uv run ruff check .` / `uv run ruff format --check .` | sin errores; 248 archivos formateados |
| `uv run pyright` | 0 errores, 0 avisos |
| `uv run pytest -q` | 1011 passed, 2 skipped (los smokes opt-in de modelo real y de diarización) |
| `uv run voz --no-browser --port 9002` | `GET /` 200 y `GET /api/health` 200; apagado con SIGINT limpio |
| `npm run lint`, `npm run typecheck` | sin errores |
| `npm run test` | 25 archivos, 198 tests pasan |
| `npm run build` | el bundle generado es idéntico al versionado en `src/voz/static` (`git status` limpio) |

No verificado: `npm ci` (esta sesión no tenía red hacia el registro de npm; el
frontend se comprobó con el `node_modules` ya instalado), la Opción B (Distrobox)
y los tests con un modelo real (`VOZ_FASTER_WHISPER_MODEL_*`).
