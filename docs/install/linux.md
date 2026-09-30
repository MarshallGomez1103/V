# Instalación en Linux

VOZ es una aplicación local: un comando `voz` que arranca un servidor en
`127.0.0.1` y una interfaz web servida por él. Todavía no hay release pública, así
que se instala desde un wheel construido a partir del repositorio.

> **Estado de verificación.** Solo Bazzite (Fedora Atomic) se ha verificado. Estos
> pasos son genéricos y no se han probado en otras distribuciones; si algo falla,
> abre un issue con la salida de `voz doctor --redact`.

## Requisitos

- Linux x86-64 con `glibc` y Python **3.12 o superior** (`uv` puede descargarlo).
- [`uv`](https://docs.astral.sh/uv/) instalado para el usuario.
- **FFmpeg** (`ffmpeg` y `ffprobe` en el `PATH`) para importar y normalizar audio.
  Instálalo con el gestor de tu distribución o, en sistemas inmutables, en un
  contenedor de usuario (Distrobox). No hace falta para arrancar la interfaz.
- Opcional, para transcribir en GPU: una GPU NVIDIA con controlador CUDA 12
  operativo en el host. Los runtimes cuBLAS/cuDNN llegan como wheels de pip.

## Construir el wheel

Desde un checkout (requiere `uv`; el bundle web ya va versionado en `src/voz/static`):

```bash
git clone <url-del-repositorio> voz && cd voz
uv build --wheel --out-dir dist
sha256sum dist/*.whl
```

## Instalar

```bash
uv tool install dist/voz_transcriber-*.whl
voz --help
voz doctor
```

`uv tool install` crea un entorno aislado y enlaza `voz` en `~/.local/bin`
(ejecuta `uv tool update-shell` si no está en tu `PATH`). Para arrancar:

```bash
voz                       # http://127.0.0.1:8765 y abre el navegador
voz --no-browser --port 9000
```

VOZ solo escucha en `127.0.0.1` por defecto; `--host` con otra dirección expone el
servicio en la red y debe ser una decisión deliberada.

## Faster Whisper local (extra `asr-local`)

La transcripción local usa Faster Whisper, que es opcional y aún **experimental**:

```bash
uv tool install --force \
  "voz-transcriber[asr-local] @ ./dist/voz_transcriber-0.1.0-py3-none-any.whl"
```

(Ajusta el nombre del archivo a la versión construida. Los wheels CUDA pesan
cientos de MB: el entorno de la herramienta con el extra ocupa unos 2,6 GB y la
instalación tardó unos 4 minutos con la caché de `uv` vacía.)

En Linux el extra incluye `nvidia-cublas-cu12` y `nvidia-cudnn-cu12`, de modo que
CTranslate2 encuentra CUDA 12 sin tocar el sistema. Esto solo instala la
dependencia: los pesos del modelo **no** se descargan hasta que eliges y confirmas
un modelo desde la interfaz. Sin GPU NVIDIA VOZ usa CPU de forma explícita. Comprueba
el resultado con `voz doctor`.

## Dónde guarda VOZ los datos

VOZ respeta XDG Base Directory (nunca escribe en el checkout):

| Contenido | Ruta |
| --- | --- |
| Configuración | `${XDG_CONFIG_HOME:-~/.config}/voz/` |
| Datos: base SQLite, proyectos, originales, modelos | `${XDG_DATA_HOME:-~/.local/share}/voz/` |
| Caché | `${XDG_CACHE_HOME:-~/.cache}/voz/` |
| Estado y logs | `${XDG_STATE_HOME:-~/.local/state}/voz/` |

Para probar sin tocar tus datos, exporta esas cuatro variables hacia un directorio
temporal antes de ejecutar `voz`. Ojo: `uv` también respeta `XDG_CACHE_HOME` y
`XDG_DATA_HOME`, así que con ellas redirigidas descargará de nuevo su caché de
paquetes y un CPython gestionado (3.12). Para no repetirlo, exporta además
`UV_CACHE_DIR` y `UV_PYTHON_INSTALL_DIR` hacia sus ubicaciones reales.

## Actualizar

Construye el wheel nuevo y ejecuta `uv tool install --force dist/voz_transcriber-*.whl`.
**Reinstalar sin el extra lo quita** (verificado: `voz doctor` vuelve a avisar de
que falta `asr-local`); si lo usas, repite el comando completo de la sección
anterior. El esquema de la base se migra solo al arrancar y antes de migrar se
guarda una copia en `~/.local/state/voz/backups/`; aun así, copia
`~/.local/share/voz/` antes de actualizar si contiene trabajo que no quieres perder.

## Desinstalar

```bash
uv tool uninstall voz-transcriber
```

Eso no borra tus proyectos ni modelos. Si quieres eliminarlos, revisa el contenido
de los directorios de la tabla anterior y bórralos tú mismo (contienen tus
grabaciones y transcripts).

## Problemas frecuentes

- `voz: command not found`: añade `~/.local/bin` al `PATH` (`uv tool update-shell`).
- Puerto ocupado: usa `--port` con otro número; `voz doctor` lo comprueba.
- Falta FFmpeg: `voz doctor` lo indica; la importación no funcionará hasta instalarlo.

## Verificado en Bazzite

**Fecha:** 2026-09-30 (S15.10). **Máquina:** Bazzite `bazzite-nvidia-open`
(Fedora 44, kernel 7.2.7), NVIDIA GeForce RTX 4060 Laptop, `uv 0.12.21`,
FFmpeg 8.1.3 en `/usr/bin`, Python del sistema 3.14.7.

Método: checkout limpio (`git clone` del commit `435ed0a`) en un directorio
temporal y **todas** las variables `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` y `XDG_*`
apuntando a otro directorio temporal, sin tocar `~/.local`. Los pasos son los de
este documento, en este orden; red solo hacia PyPI (más la descarga del CPython
gestionado que hace `uv`, ver la nota de `XDG_*` arriba).

| Paso | Comando | Resultado |
| --- | --- | --- |
| Construir | `uv build --wheel --out-dir dist` | `voz_transcriber-0.1.0-py3-none-any.whl` |
| Instalar | `uv tool install dist/voz_transcriber-*.whl` | instala el ejecutable `voz` (unos 11 s) |
| Ayuda | `voz --help` (desde un cwd fuera del checkout) | muestra `serve` y `doctor` |
| Diagnóstico | `voz doctor` | 7 ok, 3 avisos (sin modelos, sin `asr-local`, sin detección de GPU), 0 fallos, código 0 |
| Arrancar | `voz --no-browser --port 9000` | `GET /` 200, `GET /api/health` 200 `{"status":"ok"}`, escucha solo en `127.0.0.1:9000`, SIGINT apaga limpio |
| Extra | `uv tool install --force "voz-transcriber[asr-local] @ ./dist/voz_transcriber-0.1.0-py3-none-any.whl"` | instala `faster-whisper`, `nvidia-cublas-cu12` y `nvidia-cudnn-cu12` (unos 4 min, 2,6 GB) |
| Diagnóstico con extra | `voz doctor` | 9 ok, 1 aviso (sin modelos), 0 fallos; `runtime ASR: faster-whisper disponible`; `GPU/CUDA: float16, int8, int8_float16` |
| Opciones | `GET /api/transcription-options` | lista los modelos Faster Whisper del catálogo; ningún peso se descarga |
| Actualizar | `uv tool install --force dist/voz_transcriber-*.whl` | funciona, pero **quita el extra** (ver Actualizar) |
| Desinstalar | `uv tool uninstall voz-transcriber` | quita el ejecutable; `voz.sqlite3` en `XDG_DATA_HOME/voz` permanece, como dice la sección |
| Script | `scripts/check-install.sh` | `voz --help`, `doctor --json`, `GET /` y `/api/health` 200 en un puerto libre, apagado con código 0 |

Correcciones hechas a la documentación y al código a raíz de esta verificación:

- La sección *Actualizar* no decía que reinstalar sin el extra lo elimina.
- El aviso de `voz doctor` sugería `uv sync --extra asr-local`, que no sirve en
  una instalación con `uv tool`; ahora remite a este documento.
- El tamaño del extra y la nota sobre `XDG_*` y `uv` no estaban documentados.

No verificado: el extra `diarization` (`sherpa-onnx`) con `uv tool install`, el
arranque en otras distribuciones y una transcripción real (no se descargó ningún
modelo, por diseño). Los checks de desarrollo están en
[setup-bazzite.md](../development/setup-bazzite.md#verificado-en-bazzite).
