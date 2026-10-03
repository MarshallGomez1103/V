# Instalación en Windows y macOS

> **Estado de verificación.** VOZ solo se ha usado a mano en Linux (Bazzite). El
> código tiene rutas específicas para Windows y macOS y su CI (`Backend /
> windows-latest` y `macos-latest`) ejecuta toda la batería de pruebas y arranca el
> servidor real, pero hasta que alguien lo use en un equipo real **es
> experimental**. Si algo falla, abre un issue con la salida de `voz doctor --redact`.

## Requisitos

- [`uv`](https://docs.astral.sh/uv/) (descarga el Python correcto solo; el
  repositorio fija Python **3.12** en `.python-version`).
- Windows 10/11 x86-64, macOS 13 o superior (Apple Silicon; Intel funciona con
  Python 3.12/3.13).
- Nada más: FFmpeg se obtiene automáticamente (abajo).

Desde un checkout, el equivalente a "clonar y hacer doble clic" es:

```bash
uv run --extra asr-local --extra diarization voz
```

## FFmpeg automático

VOZ necesita `ffmpeg` y `ffprobe`. Si no están en el `PATH`, al arrancar descarga
**una sola vez** (unos 40-140 MB según el sistema) una compilación estática del
repositorio `zackees/ffmpeg_bins`, fijada a un commit y verificada con SHA-256, en
la carpeta de caché de VOZ (`…/cache/ffmpeg/`). No usa el paquete `static-ffmpeg`
(arrastra `twine` y unas 25 dependencias y descarga sin sumas de comprobación).
Un FFmpeg ya instalado siempre tiene prioridad. Sin red, `voz doctor` indica cómo
instalarlo a mano (`winget install ffmpeg`, `brew install ffmpeg`).
Desactivar la descarga: variable `VOZ_FFMPEG_AUTO_DOWNLOAD=0`.

## GPU

- **Windows con NVIDIA**: el extra `asr-local` incluye `nvidia-cublas-cu12` y
  `nvidia-cudnn-cu12` (unos 1,3 GB de wheels). VOZ registra sus DLL antes de cargar
  CTranslate2. Si CUDA no carga, VOZ usa la CPU (int8) con un aviso, nunca falla el
  trabajo. Hace falta el controlador NVIDIA (no el CUDA Toolkit).
- **macOS**: siempre CPU (int8); no hay CUDA.

## Dónde guarda VOZ los datos

| Contenido | Windows | macOS |
| --- | --- | --- |
| Configuración | `%LOCALAPPDATA%\voz\config` | `~/Library/Application Support/voz/config` |
| Datos (base SQLite, proyectos, modelos) | `%LOCALAPPDATA%\voz\data` | `~/Library/Application Support/voz/data` |
| Caché (FFmpeg, ondas) | `%LOCALAPPDATA%\voz\cache` | `~/Library/Caches/voz` |
| Estado y copias de seguridad | `%LOCALAPPDATA%\voz\state` | `~/Library/Application Support/voz/state` |

Una variable `XDG_*_HOME` absoluta sustituye la carpeta correspondiente en
cualquier sistema (útil para pruebas o instalaciones portátiles).

## Garantías más débiles que en Linux/macOS

- **Windows no tiene `dir_fd`.** En Linux y macOS los originales y derivados se
  abren relativos a un descriptor de directorio sin seguir enlaces simbólicos. En
  Windows se comprueba cada componente con `lstat` (rechaza enlaces y uniones)
  antes de usarlo, pero queda una ventana de carrera que `dir_fd` cierra. La
  escritura sigue siendo atómica (copia a temporal + enlace duro sin reemplazo) y
  el original, de solo lectura y nunca modificado. Requiere NTFS (enlaces duros).
- Windows no tiene modos POSIX: el fichero de claves API (`secrets.toml`) se
  protege con los permisos del perfil de usuario en lugar de `0600`, y no se
  comprueba el modo al leerlo.
- `fsync` de directorios no existe en Windows (NTFS lo cubre con su diario).
- El pico de memoria de `voz bench` no cuenta procesos hijos en Windows.
