# AppImage y Flatpak: prototipos medidos (S15.12, S15.13)

Estado: **prototipos funcionales, no publicados y no soportados** (AGENTS.md: lo no
ejercitado en una plataforma es experimental). Se construyeron y probaron el
2026-09-30 solo en Bazzite (Fedora Atomic) x86-64 con una RTX 4060 Laptop, wheel
`voz_transcriber-0.1.0` construido desde `HEAD`. No hay CI para estos formatos.

Recetas reproducibles en `packaging/`:

| Archivo | Para qué |
| --- | --- |
| `packaging/appimage/build.sh`, `AppRun` | AppImage: CPython standalone (uv) + wheel + dependencias en `usr/lib/voz` |
| `packaging/flatpak/build.sh`, `dev.voz.Voz.yml`, `dev.voz.Voz.metainfo.xml` | Flatpak sobre `org.freedesktop.Platform//25.08` |
| `packaging/common/smoke.sh` | Arranca el empaquetado con `--no-browser`, mide el tiempo a `/api/health` 200, comprueba `/` y la parada con SIGINT |
| `packaging/common/voz.desktop`, `voz.svg` | Lanzador e icono compartidos |

```bash
packaging/appimage/build.sh [wheel]            # VOZ_EXTRAS=asr-local, VOZ_FFMPEG_DIR=<dir con ffmpeg/ffprobe estáticos>
packaging/flatpak/build.sh [wheel]             # VOZ_EXTRAS=asr-local; instala con --user
packaging/common/smoke.sh ./VOZ-0.1.0-x86_64.AppImage
packaging/common/smoke.sh flatpak run dev.voz.Voz
```

Ambos scripts trabajan en `VOZ_WORK` (un `mktemp -d` por defecto; nunca el repo),
parten de `git archive HEAD` si no se les da un wheel y necesitan red (PyPI, CPython
standalone de uv, `appimagetool`, extensión `org.flatpak.Builder` y SDK `--user`).
El ID `dev.voz.Voz` es provisional y no está registrado.

## Resultados medidos

Arranque = proceso lanzado con XDG vacíos hasta `/api/health` 200 (migración de la
base incluida), 3 repeticiones por variante donde se indica.

| Variante | Artefacto | Instalado | Build | Arranque a `/api/health` |
| --- | --- | --- | --- | --- |
| AppImage base (FFmpeg del host) | 46 MiB (48 450 040 B) | 171 MB (AppDir) | 8-9 s con caché de uv vacía | 0,93 / 1,11 / 0,94 s |
| AppImage base + FFmpeg estático | 98 MiB (102 742 520 B) | | 7 s (+ 42 MB de descarga) | 1,11 s |
| AppImage `asr-local` | 1,42 GiB (1 525 004 792 B) | 4,3 GB (AppDir + trabajo) | 192 s (166 s de dependencias) con caché de uv vacía | 1,23 / 1,27 s |
| Flatpak base | 11 MB (bundle, 11 565 320 B) | 52,6 MB | 111 s | 1,05 / 0,70 / 0,69 s |
| Flatpak `asr-local` | 1,06 GB (bundle, 1 059 718 376 B) | 2,8 GB | 7,3 min `flatpak-builder` + ~14 min de `build-bundle` | 0,66 s |

Notas de medición: los tiempos de la variante base del Flatpak incluyen descargar
los wheels de PyPI; el AppImage reutiliza el mismo CPython. `build-bundle` tarda
mucho en la variante ASR por la compresión de ostree; para uso local no hace falta
(basta `flatpak-builder --install`).

### Qué se comprobó en cada formato

- `voz doctor --json` dentro del empaquetado: FFmpeg `ok`, rutas escribibles,
  `runtime ASR ok faster-whisper disponible` y `GPU/CUDA ok CUDA: float16, int8,
  int8_float16` en **ambas** variantes `asr-local` (los cuBLAS/cuDNN de pip van
  dentro: `nvidia/` pesa 2,2 GB y es el grueso del tamaño).
- Parada limpia: AppImage sale con 0 tras SIGINT. `flatpak run` devuelve 130 (el
  SIGINT lo recibe también el envoltorio de `flatpak run`); el servidor se detiene.
- No se transcribió audio ni se descargó ningún modelo (reglas de la oleada).
- **No** se probó: abrir el navegador desde el lanzador `.desktop` (los humos usan
  `--no-browser`), ejecución en otras distribuciones, AppImage sin FUSE
  (`--appimage-extract-and-run` es la alternativa), aarch64.

## FFmpeg

- **AppImage**: `AppRun` antepone `usr/bin` al `PATH`. Sin `VOZ_FFMPEG_DIR` usa el
  FFmpeg del host (en Bazzite, el del sistema o Distrobox; si falta, `voz doctor`
  lo avisa y la UI arranca igual). Con binarios estáticos de johnvansickle.com
  (7.0.2, ~77 MB cada uno) el AppImage crece 52 MiB comprimido y `voz doctor`
  reporta `ffmpeg version 7.0.2-static`. Esos binarios son **GPLv3**: redistribuirlos
  exige incluir su licencia y la oferta de fuentes, así que no se incluyen por
  defecto.
- **Flatpak**: no hace falta nada; el runtime 25.08 trae `/usr/bin/ffmpeg` y
  `ffprobe` (7.1.3) y CPython 3.13, y el wheel (`requires-python >=3.12`) se
  instala con el `pip3` del SDK en `/app`. Los códecs con patentes dependerían de
  la extensión `ffmpeg-full` (no probada con medios reales).

## Problemas y límites

**Sandbox y red.** El servidor escucha en `127.0.0.1` dentro del sandbox. Sin
`--share=network` el loopback del sandbox es otro y el navegador del host no lo
alcanza: se comprobó con `flatpak run --unshare=network` (el servidor arranca y
`/api/health` no responde desde fuera). La app declara `--share=network`, que
además habilita los proveedores cloud solo si el usuario los elige; la escucha sigue
siendo `127.0.0.1`, pero el sandbox ya no aísla la red.

**XDG.** VOZ ya respeta XDG. Flatpak fija `XDG_*` a `~/.var/app/dev.voz.Voz/`: los
datos (base, proyectos, modelos de GB) quedan **separados** de los de `uv tool
install` y no se comparten. El AppImage usa las rutas XDG normales del host, o sea
los mismos datos que una instalación con `uv`. Los originales se suben desde el
navegador, así que no se pide acceso al sistema de archivos.

**GPU/CUDA.** En Flatpak hace falta `--device=all` (`/dev/nvidia*`; `--device=dri`
no basta) y la extensión `org.freedesktop.Platform.GL.nvidia-<versión>` que coincida
con el controlador del host (en Bazzite ya está). Con `--nodevice=all`,
`voz doctor` pasa a `solo CPU (int8)`. `--device=all` debilita el sandbox y Flathub lo
revisa. El AppImage no tiene esa restricción: usa el controlador del host
directamente. Ambos llevan CUDA 12 por wheels, así que dependen de que el
controlador del host sea compatible.

**Reproducibilidad y Flathub.** El manifiesto resuelve dependencias de PyPI en la
compilación con `--share=network` (`ponytail:` marcado en el manifiesto). Flathub
exige fuentes fijadas y compilación sin red: habría que generar un módulo por wheel
(`flatpak-pip-generator`) con hashes. Para el extra ASR eso son ~1 GB de fuentes.
Tampoco se verificó `flatpak-builder-lint` ni el metainfo contra `appstreamcli`.

**AppImage.** Requiere FUSE 2 para ejecutarse directamente; el CPython standalone
es autocontenido, pero las ruedas manylinux dependen de la glibc del host. El
AppImage no se actualiza ni se firma. `AppRun` no define `PYTHONHOME`: el CPython
standalone localiza su stdlib respecto a su binario.

## Recomendación

1. Mantener `uv tool install` (docs/install/linux.md) como camino soportado.
2. Si se quiere un binario descargable, **empezar por el AppImage base** (46 MiB,
   8 s de build, arranque ~1 s, sin red en la ejecución, GPU sin permisos
   especiales) con FFmpeg del host y `voz doctor` como guía. Es el formato con
   menos piezas móviles y ya reproduce el comportamiento de `uv tool install`.
   La variante `asr-local` (1,4 GiB) solo como descarga aparte y etiquetada
   experimental, hasta ejercitarla en GPU real con un modelo.
3. Dejar el Flatpak para después: encaja con Bazzite y trae Python/FFmpeg, pero
   exige `--share=network` y `--device=all`, datos separados y reescribir el
   manifiesto para Flathub (fuentes fijas, ID real, `flatpak-builder-lint`).
4. Antes de publicar cualquiera: añadirlo al workflow de release (`release-dry-run`)
   solo cuando haya un humo en CI (el AppImage base sí puede, sin GPU), y registrar
   la licencia GPL si se distribuye FFmpeg.
