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
cientos de MB.)

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
temporal antes de ejecutar `voz`.

## Actualizar

Construye el wheel nuevo y ejecuta `uv tool install --force dist/voz_transcriber-*.whl`.
El esquema de la base se migra solo al arrancar; haz una copia de
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
