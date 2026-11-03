# 06 · Auditoría de integración con Linux, empaquetado e instalación

Sistema objetivo: Bazzite (Fedora Atomic). Este equipo corre Bazzite con KDE/Wayland según el entorno del propietario; no se alteró el sistema operativo durante la auditoría.

## Veredicto

El lanzamiento por terminal funciona y está verificado. El **icono de escritorio no es portable**: genera rutas absolutas al checkout y se rompe al mover o reinstalar el proyecto. Además no tiene función de desinstalación. Corregir esto antes de distribuir.

## Comando `voz` y lanzamiento

| Elemento | Estado | Evidencia |
|---|---|---|
| Entry point `voz` | Implementado | `pyproject.toml` `[project.scripts]`; `interfaces/cli/main.py` |
| Arranque de Uvicorn en loopback | Verificado | Arranque en esta auditoría: `GET /api/health` → `{"status":"ok","version":"0.1.0"}` |
| Apertura del navegador | Implementada | `run_server(open_browser=...)`; `--no-browser` |
| Puerto fijo 8765 | Implementado; sin reasignación automática | `main.py:28` `DEFAULT_PORT = 8765`; `doctor` comprueba el puerto |
| Apagado limpio | Verificado en tests (`tests/e2e/test_cli_shutdown.py`); ROADMAP BOOT-BE-003 | — |
| Segundo doble clic reutiliza el servidor | Implementado (`b2e6741`) | Commit |

## Icono de escritorio y `.desktop`

**Archivo instalado en este equipo** (solo lectura, `~/.local/share/applications/voz.desktop`):

```
[Desktop Entry]
Type=Application
Name=VOZ
Comment=Transcripción local de audio y video
Exec="<repo-V>/Iniciar-Linux.sh"
Path=<repo-V>
Icon=<repo-V>/packaging/icons/voz.png
Terminal=true
Categories=AudioVideo;Audio;
```

Generador: `src/voz/infrastructure/desktop_shortcut.py`, método `_linux` (líneas 126–137):

- `Exec`, `Path` e `Icon` se construyen con `self._root`, que viene de `checkout_root()` (`Path(__file__).resolve().parents[3]`, línea 37). Es decir, **la ruta del checkout actual, absoluta, en el momento de crear el acceso directo**.
- Se escribe en dos sitios: el escritorio (`xdg-user-dir DESKTOP`, en este equipo `<Escritorio>`) y `~/.local/share/applications`.
- `exists()` (líneas 96–98) solo comprueba que el archivo registrado exista. **No valida que `Exec` apunte a algo que exista**. La UI seguirá diciendo que el acceso directo existe tras mover el checkout.
- No hay función para eliminar el acceso directo (búsqueda: sin `remove`/`delete`/`unlink` en el módulo; el único `unlink` es el PNG del `.app` de macOS, línea 192).

Comprobación de portabilidad (lectura de código y del archivo real): **no portable**. Si el checkout se mueve, `Exec` e `Icon` apuntan a rutas inexistentes. Si se reinstala desde otra ruta, el acceso directo viejo sigue apuntando a la ruta vieja hasta que se vuelva a crear desde Ajustes.

Recomendación: `Exec=voz` cuando VOZ esté instalado con `uv tool install` (la plantilla `packaging/common/voz.desktop` ya lo hace), y para el modo checkout, regenerar el archivo al arrancar si la ruta cambió. Añadir `exists()` que compruebe `Exec` y una función de eliminación.

## Lanzadores

| Archivo | Qué hace | Riesgo |
|---|---|---|
| `Iniciar-Linux.sh` | Delega en `Iniciar-Mac.command` | Bajo |
| `Iniciar-Mac.command` | Instala uv si falta, luego `uv run --extra asr-local --extra diarization voz` | **`curl ... install.sh \| sh` sin versión fijada ni checksum** (línea 15) |
| `Iniciar-Windows.bat` | Equivalente en Windows, CRLF por `.gitattributes` | Verificado en CI con bash; no ejecutado a mano |

`uv run` sincroniza el entorno en cada arranque. Coherente con el modelo de "doble clic", pero implica que cada arranque toca `.venv` del checkout.

## Instalación y desinstalación

| Ruta | Estado |
|---|---|
| `uv tool install` desde wheel | Verificado (PKG-001/002/004): instala, ejecuta `voz` y `doctor` fuera del checkout |
| Checkout con lanzador | Principal para el propietario |
| Desinstalación de la app | `uv tool uninstall` o borrar la carpeta; no hay desinstalador |
| Desinstalación del acceso directo | **No existe**; hay que borrar `voz.desktop` a mano en el escritorio y en `~/.local/share/applications` |
| AppImage | Prototipo: base 46 MiB, arranque ~1 s (PKG-006); no en CI |
| Flatpak | Prototipo: base 52,6 MB instalado; `asr-local` 2,8 GB; appid `dev.voz.Voz` provisional |

## Actualizaciones

- No hay mecanismo de actualización. Con checkout: `git pull` y el lanzador sincroniza. Con `uv tool`: reinstalar el wheel.
- `release-dry-run.yml` construye el artefacto y no publica; no se ejecutó (requiere push, S15.14 pendiente de autorización).

## Procesos, puertos y ciclo de vida

- Un servidor por equipo: el segundo doble clic reutiliza el abierto (`b2e6741`).
- `voz doctor` comprueba puerto, FFmpeg/ffprobe, rutas XDG, disco y GPU sin cargar modelos (verificado en tests; no ejecutado en esta auditoría).
- Apagado desde la UI con cabecera `X-VOZ-Action: shutdown` (`interfaces/api/shutdown.py`), con ejecución graceful del job en curso (queda recuperable).

## Rutas XDG, persistencia y logs

Verificado en `src/voz/infrastructure/paths.py` y en el equipo:

| Tipo | Ruta en este equipo | Contenido |
|---|---|---|
| Datos | `~/.local/share/voz/` | `voz.sqlite3` (9,5 MB), `projects/`, `models/`, `uploads/`, `waveforms/` según `ls` |
| Caché | `~/.cache/voz/` | `uploads/`, `waveforms/` |
| Configuración | `~/.config/voz/` | Vacía en este equipo (no hay claves guardadas) |
| Logs | No hay directorio de logs | Salida a la consola del lanzador |

Los datos no están dentro del checkout (ADR-0006 y AGENTS.md). Hay un riesgo de dos fuentes de verdad con `~/.cache/voz/uploads`: no verificado si el contenido se limpia.

## Permisos

- Archivos del acceso directo: `chmod 0755` (línea 149 de `desktop_shortcut.py`), necesario para que GNOME/KDE lo acepten.
- `gio set metadata::trusted true` cuando `gio` existe (líneas 151–152): evita el aviso de confianza en GNOME. En KDE no se verifica.
- Base de datos y medios: permisos del usuario; los tests de permisos (`test_safe_fs.py`) usan modos POSIX.

## Wayland / KDE

No verificado: no se ejecutó la interfaz dentro de la sesión gráfica del propietario ni se abrió el acceso directo. La apertura del navegador usa `webbrowser`, que depende del escritorio.

## Bazzite / Fedora Atomic

- `docs/development/setup-bazzite.md` y README: no se recomienda `rpm-ostree` para el bootstrap ordinario. Consistente con la imagen inmutable.
- Dependencias CUDA se instalan como wheels `nvidia-*` en el entorno del proyecto, no en el sistema (decisión explícita en `pyproject.toml`).

## Problemas de esta área

| ID | Descripción | Severidad |
|---|---|---|
| LNX-01 | Acceso directo con rutas absolutas; `exists()` no valida | P1 (AV-P1-01) |
| LNX-02 | Sin desinstalación del acceso directo | P2 (AV-P2-12) |
| LNX-03 | `curl \| sh` del instalador de uv sin pin ni checksum | P2 (AV-P2-02) |
| LNX-04 | Sin mecanismo de actualización | P3 (plan Tauri lo contempla) |
| LNX-05 | Sin logs en archivo | P2 (AV-P2-13) |
| LNX-06 | Wayland/KDE sin verificar | Brecha de verificación |
