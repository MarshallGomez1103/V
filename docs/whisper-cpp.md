# whisper.cpp como provider local alternativo

Adapter: `src/voz/infrastructure/asr/whisper_cpp.py` (`provider_id = "whisper-cpp"`),
catálogo: `whisper_cpp_catalog.py`, política de sugerencia:
`src/voz/application/whisper_cpp_fallback.py`. Sección 9 del roadmap (S9.01-S9.09).

> **Estado de verificación.** El adapter, la detección y el catálogo están
> probados con un ejecutable **falso** (`tests/fixtures/whisper_cpp/fake_whisper_cli.py`)
> que imita la CLI y escribe el JSON. 2026-09-30: compilación **solo CPU**
> verificada con whisper.cpp v1.9.4 (`uvx cmake`, GCC 16.2.1); el JSON real de
> `-ojf` coincide con el adapter (fixture `tests/fixtures/whisper_cpp/real_ojf_v1.9.4.json`).
> Benchmark CPU/GPU (S9.10) en `docs/benchmarks.md`. CUDA/Vulkan sin verificar.

## Cómo encuentra VOZ el ejecutable

1. Si `VOZ_WHISPER_CPP_BIN` está definida, se usa **solo** esa ruta (debe ser un
   archivo ejecutable). Una ruta inválida no cae silenciosamente al `PATH`.
2. Si no, se busca `whisper-cli` en `PATH`.

La validación (`probe_whisper_cpp`) ejecuta `whisper-cli --help` sin shell y con
timeout, y exige los flags `--model --file --language --output-json-full
--output-file --no-gpu --no-prints --offset-t --duration` (whisper.cpp >= 1.7).
Resultado tipado `WhisperCppAvailability(available, reason, version)`; las
razones son códigos estables sin rutas: `whisper_cpp_not_found`,
`whisper_cpp_not_executable`, `whisper_cpp_probe_timeout`,
`whisper_cpp_missing_flags`. La versión se informa solo si el `--help` la imprime.

## Compilar con CUDA (NVIDIA)

Requiere CUDA Toolkit y un GCC compatible con él (en Fedora/Bazzite el GCC del
sistema suele ser demasiado nuevo: compila dentro de un toolbox/distrobox).

```bash
# Bazzite (sistema inmutable): entorno mutable para compilar
toolbox create whispercpp && toolbox enter whispercpp
sudo dnf install -y git cmake gcc-c++ make
# CUDA Toolkit: repositorio oficial de NVIDIA para Fedora, luego
#   sudo dnf install cuda-toolkit
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
git checkout v1.9.4   # tag verificado (solo CPU); 5359861c… es la revisión del repo de modelos en HF, no de este repo
cmake -B build -DGGML_CUDA=1
cmake --build build -j --config Release
# binario: build/bin/whisper-cli
```

Solo CPU sin toolbox (verificado): `uvx cmake -B build && uvx cmake --build build -j --config Release`.
Alternativa: `brew install cmake` (Homebrew en Bazzite) para cmake,
pero el toolkit de CUDA y el compilador compatible siguen necesitándose.

## Compilar con Vulkan (AMD/Intel/NVIDIA sin CUDA)

```bash
toolbox create whispercpp && toolbox enter whispercpp
sudo dnf install -y git cmake gcc-c++ make \
  vulkan-headers vulkan-loader-devel glslc shaderc
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
cmake -B build -DGGML_VULKAN=1
cmake --build build -j --config Release
```

Comprobar el driver con `vulkaninfo --summary` (paquete `vulkan-tools`) antes de
culpar al build. Sin ninguno de los dos flags el build es solo CPU.

## Apuntar VOZ al binario

```bash
export VOZ_WHISPER_CPP_BIN="$HOME/src/whisper.cpp/build/bin/whisper-cli"
```

Si el binario se ejecuta desde un toolbox, la ruta de `$HOME` es la misma
dentro y fuera del contenedor; las librerías CUDA/Vulkan del toolbox pueden no
estar en el host, en ese caso copia el build estático o exporta `LD_LIBRARY_PATH`
antes de arrancar VOZ.

## Modelos cuantizados (S9.05)

Repo `ggerganov/whisper.cpp`, revisión `5359861c739e955e79d9a303bcbc70fb988958b1`
(MIT). Un solo archivo `ggml-<model_id>.bin` por modelo, con tamaño y SHA-256
fijos; se instalan con `FileSystemModelStore.download` (resumible, verificado,
publicación atómica) y **nunca** sin petición explícita.

| model_id | archivo | tamaño (bytes) |
| --- | --- | --- |
| `large-v3-turbo-q5_0` | `ggml-large-v3-turbo-q5_0.bin` | 574 041 195 |
| `large-v3-turbo-q8_0` | `ggml-large-v3-turbo-q8_0.bin` | 874 188 075 |
| `large-v3-turbo` | `ggml-large-v3-turbo.bin` | 1 624 555 275 |
| `small-q5_1` | `ggml-small-q5_1.bin` | 190 085 487 |
| `small` | `ggml-small.bin` | 487 601 967 |
| `base` | `ggml-base.bin` | 147 951 465 |

## Contrato del adapter

- Comando (lista de argumentos, sin shell): `whisper-cli --model <ggml> --file
  <wav> --language <código|auto> --output-json-full --output-file <base>
  --no-prints [--no-gpu] [--offset-t <ms> --duration <ms>]`. El idioma es el
  subtag primario (`es-CO` -> `es`); `None` -> `auto`. `--no-gpu` solo con
  `force_cpu=True`. El clip de una invocación recuperable se pasa con
  `--offset-t/--duration`; los tiempos del JSON son globales, igual que en
  Faster Whisper.
- El audio se copia a un directorio temporal privado (0700) que se elimina
  siempre; se valida que sea WAV PCM 16 kHz mono 16 bit antes de lanzar el
  proceso (si no, `transcription_invalid_audio`).
- Segmentos: `transcription[].offsets.from/to` (ms) y `text`. Se quita el
  padding pero se conserva el espacio inicial de frontera de palabra (así
  `TranscriptionResult.text` sigue uniendo con `"".join`); los vacíos se
  descartan y los solapes de pocos ms se recortan para mantener el orden.
- Palabras (si `word_timestamps`): los tokens se agrupan en palabras (un espacio
  inicial abre palabra; se ignoran `[_BEG_]`, `[_TT_..]`); la probabilidad es la
  media de `p`. Si algún token no trae offsets válidos, el segmento queda sin
  palabras (el texto no se pierde). `t_dtw` se ignora por ahora.
- Fallos (todos con mensaje sin rutas): binario ausente o no ejecutable, código
  de salida != 0 y JSON ilegible/incompleto -> `transcription_provider_failed`;
  archivo de modelo ausente -> `transcription_model_not_installed`.
- Cancelación: se consulta el token cada 100 ms; al cancelarse se hace
  `terminate()` (y `kill()` tras 2 s) y se lanza `transcription_cancelled`.
  El proceso nunca queda huérfano ni deja temporales.

## Sugerencia de provider (S9.09)

`suggest_whisper_cpp(faster_whisper=RuntimeAvailability, whisper_cpp_available=bool)`
es una función pura: devuelve `ProviderSuggestion("whisper-cpp", razón)` con
`faster_whisper_runtime_missing` o `faster_whisper_no_cuda`, o `None`. Nunca
cambia de provider por sí sola (la UI la muestra y el usuario elige), nunca
propone un proveedor cloud y no sugiere nada si el hardware es desconocido.
