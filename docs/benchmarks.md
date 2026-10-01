# Benchmarks locales (`voz bench`)

Mide tiempo, factor de tiempo real (RTF), memoria y, si hay referencia, WER/CER
de un modelo **ya instalado**. Sección 13 del roadmap (S13.07-S13.10) y S9.10.
Nada se descarga, nada sale de la máquina y los datos del benchmark **nunca**
viven dentro del repositorio.

## Uso

```bash
uv run voz bench \
  --model-dir <directorio-del-modelo> \
  --source Systran/faster-whisper-large-v3 \
  --revision edaa852ec7e145841d8ffdb056a99866b5f0a478 \
  --device cuda            # cuda | cpu
  --dataset <nombre|ruta>  # ver "Dataset personal"
  [--compute-type float16|int8_float16|int8]   # por defecto float16 (cuda) / int8 (cpu)
  [--engine faster-whisper|whisper-cpp] [--language es] [--json]
```

- `--model-dir` es obligatorio y se usa tal cual: `voz bench` no descarga ni
  busca modelos. `--source` y `--revision` deben coincidir con una entrada del
  catálogo fijado de VOZ (así la procedencia del resultado no se inventa). Con
  `--engine whisper-cpp`, `--source` es el id del modelo (`large-v3-turbo-q5_0`)
  porque todos comparten repo; requiere `VOZ_WHISPER_CPP_BIN` o `whisper-cli` en
  el `PATH` y solo se mide en `cpu`.
- Salida de texto (tabla por clip + totales) o `--json` (`schema_version: 1`,
  sin rutas del host). Errores: `benchmark_*` con código de salida 2; fallos del
  motor, código 1.

### Qué se mide

| Métrica | Cómo |
| --- | --- |
| Tiempo de carga | primera transcripción de 1 s de silencio (fuerza la carga perezosa del modelo; incluye ~1 s de inferencia). En whisper.cpp el modelo se recarga en cada llamada, así que es el coste de arranque por llamada. |
| Tiempo y RTF | `perf_counter` alrededor de cada clip; RTF = segundos de cómputo / segundos de audio (< 1 es más rápido que tiempo real). Los totales suman clips. |
| RAM | pico RSS (`ru_maxrss`) del proceso; con whisper.cpp, del proceso hijo más grande. Es el pico de **todo el proceso** (incluye intérprete y librerías), `ram_delta` es pico final menos pico antes de cargar el modelo. |
| VRAM | pico **muestreado** cada 0,2 s con `nvidia-smi` en un hilo (cota inferior: puede perder picos más cortos que el intervalo). Se informa la base previa y el delta; `n/d` sin GPU o en `cpu`. |
| WER / CER | `application/evaluation.py`; ver abajo. Tasa de corpus = ediciones totales / longitud de referencia total (no el promedio de tasas por clip). |

### WER / CER (S13.10)

Funciones puras con la biblioteca estándar. Normalización de ambos textos:
NFKC, `casefold`, todo carácter de puntuación o símbolo (`P*`, `S*`) pasa a
espacio (los apóstrofes y guiones separan palabras), espacios colapsados.
**Se conservan acentos y dígitos**: "está" ≠ "esta" y "3" ≠ "tres" (los números
no se convierten, para no esconder errores reales). La distancia es Levenshtein
(sustitución, inserción y borrado cuestan 1) sobre palabras (WER) o caracteres
(CER, contando espacios simples). El WER puede superar 100 %. Referencia vacía:
0 si la hipótesis también es vacía, sin tasa en otro caso.

## Dataset personal fuera de Git (S13.09)

`--dataset <nombre>` lee `$XDG_DATA_HOME/voz/benchmarks/<nombre>/`
(por defecto `~/.local/share/voz/benchmarks/<nombre>/`); un valor con `/` o que
empieza por `.` se toma como ruta. Si el directorio (o el de datos) cae **dentro
del checkout del repositorio**, el comando se niega (`benchmark_dataset_inside_checkout`),
cubierto por tests. Los audios y las referencias son datos privados: no los
copies al repo.

`manifest.json`:

```json
{
  "language": "es",
  "items": [
    {"audio": "reunion1.wav", "reference": "texto exacto dicho en el audio"},
    {"audio": "reunion2.wav", "reference_file": "reunion2.txt"},
    {"audio": "sin_referencia.wav"}
  ]
}
```

Las rutas son relativas al dataset y no pueden salir de él. Un clip sin
referencia solo aporta tiempo/memoria. `language` es opcional (`--language` lo
anula; sin ninguno, el motor detecta idioma).

## Resultados medidos (S13.07)

> **Lee esto antes de usar los números.** El audio es **sintético** (`espeak-ng`,
> voz española, sin ruido, un solo locutor, vocabulario simple). Mide velocidad,
> memoria y consistencia entre modelos; **no representa las clases reales**
> (varios hablantes, eco, ruido, acentos). El WER aquí es optimista y no debe
> citarse como precisión real. Medición única por configuración (sin repeticiones),
> con otros procesos de desarrollo posibles en la máquina: los tiempos de CPU
> tienen ruido.

- **Fecha:** 2026-09-30. **Commit base del repo:** `dc842ae` (árbol con cambios sin
  commitear de otros slices de la oleada 5c).
- **Hardware:** Intel Core i7-13650HX (20 hilos), NVIDIA GeForce RTX 4060 Laptop
  8 GB (8188 MiB), Linux 7.2.7 (Bazzite/Fedora 44), Python 3.14.7.
- **Versiones:** faster-whisper 1.2.1, CTranslate2 4.8.2, espeak-ng 1.52.0,
  whisper.cpp v1.9.4 (compilado solo CPU, `-DGGML_NATIVE=ON`, GCC 16.2.1).
- **Modelos** (revisiones fijadas del catálogo de VOZ):
  `mobiuslabsgmbh/faster-whisper-large-v3-turbo@0a363e91…`,
  `Systran/faster-whisper-large-v3@edaa852e…`,
  `ggerganov/whisper.cpp@5359861c…` `ggml-large-v3-turbo-q5_0.bin`
  (SHA-256 verificado `394221709cd5…ffa7e2`).
- **Dataset:** idioma `es`, 6 clips de 34-39 s (217 s en total, 96-105 palabras y
  540-614 caracteres de referencia cada uno, textos escritos a mano) y 1 clip largo de 434,6 s (7,2 min)
  que **concatena dos veces los mismos 6 clips** (el texto de referencia se repite).
  Generado en un directorio temporal fuera del repo y borrado al terminar; no se
  versiona. Reproducible: mismo texto + `espeak-ng -v es -s 160` + `ffmpeg -ar 16000 -ac 1`.
- **Comando:** el de "Uso" con `--dataset <dir temporal>`; resultados en `--json`.

### Clips cortos (6 × ~36 s)

| Configuración | Carga | RTF | WER | CER | RAM pico | VRAM pico (base 80) |
| --- | --- | --- | --- | --- | --- | --- |
| faster-whisper turbo, CUDA float16 | 2,6 s | 0,025 | 1,66 % | 0,81 % | 2163 MiB | 2344 MiB |
| faster-whisper large-v3, CUDA float16 | 2,6 s | 0,073 | 1,99 % | 0,81 % | 3576 MiB | 5512 MiB |
| faster-whisper turbo, CPU int8 | 20,8 s | 0,242 | 1,83 % | 0,84 % | 2092 MiB | n/d |
| whisper.cpp turbo q5_0, CPU | 12,2 s | 0,804 | 1,83 % | 0,84 % | 958 MiB | n/d |

### Clip largo (434,6 s)

| Configuración | Tiempo | RTF | WER | CER |
| --- | --- | --- | --- | --- |
| faster-whisper turbo, CUDA float16 | 10,1 s | 0,023 | 1,66 % | 0,92 % |
| faster-whisper large-v3, CUDA float16 | 52,7 s | 0,121 | **8,14 %** | 6,31 % |
| faster-whisper turbo, CPU int8 | 89,4 s | 0,206 | 1,58 % | 0,88 % |
| whisper.cpp turbo q5_0, CPU | 319,4 s | 0,735 | 2,33 % | 1,50 % |

### Qué se puede y no se puede concluir

- En esta máquina turbo en GPU es ~3 veces más rápido que large-v3 en clips cortos con ~3,2 GB
  menos de VRAM (large-v3 usa 5,5 de 8 GB: cabe, pero con poco margen para otras
  cargas de GPU). Con audio sintético limpio ambos aciertan casi igual en clips cortos.
- large-v3 empeoró mucho en el clip largo (8,14 %), **no en los cortos**. No se
  investigó la causa; una hipótesis es que el texto repetido del clip largo
  (dos veces el mismo contenido) favorezca omisiones o repeticiones, un artefacto
  de este dataset. Habría que revisar la transcripción y repetir con audio real
  antes de sacar conclusión sobre large-v3.
- La CPU con faster-whisper int8 (RTF 0,2) es utilizable; whisper.cpp q5_0 con
  los flags del adapter es ~3,3 veces más lento (RTF 0,8) pero usa menos de la
  mitad de RAM. Ambos usan 4 hilos por defecto (`whisper-cli -t` = 4; CTranslate2
  con `cpu_threads=0`); no se ajustaron hilos.
- Cada procesamiento es una sola pasada sin repeticiones ni varianza medida.

## whisper.cpp real: formato `-ojf` (S9.10)

Compilación verificada en esta máquina (solo CPU): `uvx cmake`, GCC 16.2.1,
`cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON` y
`cmake --build build --target whisper-cli` sobre el tag **v1.9.4**; el binario
acepta todos los flags que exige `probe_whisper_cpp`. La salida real de
`--output-json-full` (claves `systeminfo`, `model`, `params`, `result.language`,
`transcription[].offsets/text/tokens[].{text,offsets,id,p,t_dtw}`) coincide con
lo que lee el adapter; se guardó un extracto en
`tests/fixtures/whisper_cpp/real_ojf_v1.9.4.json` y
`tests/unit/infrastructure/asr/test_whisper_cpp_real_format.py` comprueba que
`WhisperCppProvider` lo mapea a segmentos y palabras. Sin discrepancias de
formato. Discrepancias de documentación:

- `docs/whisper-cpp.md` indica `git checkout 5359861c…  # misma revisión que el
  catálogo`, pero esa revisión es la del repo de **modelos** en Hugging Face
  (`ggerganov/whisper.cpp`), no un commit del repo de código (no existe allí).
  Para compilar hay que usar un tag, p. ej. `v1.9.4`.
- Compilación con CUDA/Vulkan: no probada aquí (solo CPU).

## Limitaciones conocidas

- Una sola GPU (`nvidia-smi` primera GPU); sin NVIDIA, VRAM es `n/d`.
- El pico de RAM es del proceso completo y no distingue modelo de librerías.
- El pico de VRAM es muestreado: cota inferior.
- La carga incluye 1 s de inferencia (ver tabla de métricas).
