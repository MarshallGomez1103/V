### INFORME — speech

**Metadatos:** fecha 2026-10-21 · HEAD 96284c5 · rutas revisadas: las 26 de `src/voz/infrastructure/asr/`, `audio/`, `diarization/`, `inference_audio.py`, `buzz_cache.py` y `edge_lab_worker.py`; lectura de cableado en `src/voz/bootstrap.py`, `src/voz/application/chunked_transcription.py`, `recoverable_transcription.py`, `ports/transcription.py`, `compute_slot.py`; contexto en `ROADMAP.md` §17, `docs/benchmarks.md`, `docs/sherpa-onnx-asr.md`, `docs/whisper-cpp.md` · alcance: inspección estática de solo lectura · límites: nada ejecutado; sin red; el comportamiento interno de faster-whisper, CTranslate2, sherpa-onnx y whisper.cpp no se comprobó (solo se citan sus contratos tal como los usa el repo).

**Cobertura:** asignados 26 · superficial 11 · profunda 15 · omitidos 0 · ~líneas 5 479 (profunda ~4 017) · dependencias principales: faster-whisper/CTranslate2 (en proceso), sherpa-onnx (ASR y diarización en subproceso), whisper-cli (subproceso), FFmpeg/ffprobe (subproceso), numpy (diarización), stdlib.

#### 1. Responsabilidades y dependencias
- Motores de transcripción: faster-whisper en proceso (`src/voz/infrastructure/asr/faster_whisper.py:265`); whisper.cpp como `whisper-cli` por invocación (`asr/whisper_cpp.py:268`); sherpa-onnx ASR en worker por invocación (`asr/sherpa_onnx.py:217`, `asr/sherpa_onnx_worker.py:122`).
- Diarización sherpa-onnx en worker por ejecución (`diarization/sherpa.py:173`, `diarization/worker.py:24`).
- Audio: normalización a WAV 16 kHz mono PCM16 con FFmpeg (`audio/ffmpeg.py:40`); picos de forma de onda a 8 kHz (`audio/waveform_peaks.py:129`); sondeo con ffprobe (`audio/ffprobe.py:33`); paso de descriptores (`audio/media_args.py:30`).
- Partición en fragmentos y propiedad del solape: en application, no en infraestructura (`application/chunked_transcription.py:83`, `:114`, `:143`).
- Descarga de FFmpeg (`audio/ffmpeg_tools.py:146`) y lectura de modelos de Buzz (`buzz_cache.py:85`).

#### 2. Arquitectura hexagonal
- Cumple: los adaptadores implementan el puerto `TranscriptionProvider` (`application/ports/transcription.py:257`) y los tipos de proveedor no salen del adaptador. Sin violación comprobada de dependencias en el área.
- Sospecha (tensión de aislamiento): el probe de faster-whisper importa `faster_whisper` y `ctranslate2` en el proceso del servidor (`asr/options.py:86-89`, `asr/hardware.py:50`); el probe de sherpa ASR también importa `sherpa_onnx` en proceso (`asr/sherpa_onnx_options.py:37`), mientras la diarización usa `find_spec` sin importar (`diarization/availability.py:11-12`). Un import nativo roto podría afectar al servidor (hipótesis).
- Contrato solo por lote: `transcribe(audio: BinaryIO) -> TranscriptionResult` (`ports/transcription.py:265-272`). No hay puerto de flujo; el progreso sale solo por `on_position` (`ports/transcription.py:227`).
- Capacidad declarada sin implementación: `TRANSLATION` en `asr/catalog.py:17`; el adaptador nunca pasa `task="translate"` (`asr/faster_whisper.py:422-435`).

#### 3. Diseño y mantenibilidad
- Duplicación: cinco bucles de subproceso con políticas distintas (poll, terminate/kill, plazo): `asr/whisper_cpp.py:268-306`, `asr/sherpa_onnx.py:217-323`, `audio/ffmpeg.py:220-301`, `diarization/sherpa.py:186-245`, `audio/waveform_peaks.py:185-257`. No hay violación SOLID; sí duplicación con reglas divergentes.
- Ruta latente: el recorte `options.clip` del adaptador (`faster_whisper.py:426-433`, `sherpa_onnx.py:138-145`, `whisper_cpp.py:259-265`) no se activa en producción, porque `chunked_transcription.py:218` y `recoverable_transcription.py:182` fuerzan `clip=None` y el recorte lo hace la fuente (`inference_audio.py:101-132`). Si se activara, la línea temporal sería incoherente: `_read_clip` devuelve un WAV que empieza en 0, pero el adaptador recibe tiempos absolutos (`sherpa_onnx.py:144` rechaza `start_ms >= end_ms`). Verificado por lectura; los tests de `tests/unit/infrastructure/asr/test_sherpa_onnx.py:86` ejercitan esa rama.
- Comentario obsoleto: `bootstrap.py:546` dice "one cached sherpa engine (~30 MB of ONNX)", pero la diarización recarga los modelos en cada ejecución (`diarization/sherpa.py:176-178`); el `SherpaEngine` en proceso (`diarization/sherpa.py:88-100`) no se usa en producción.
- Nombres y tipos: Protocols finos y tipados (`faster_whisper.py:33-75`, `sherpa_onnx_worker.py:25-51`); códigos de error estables (`ports/transcription.py:21-27`).

#### 4. Concurrencia, errores y recursos
**Carga y reutilización de modelos (pregunta 1):**
- faster-whisper: carga perezosa en `_engine_for` (`faster_whisper.py:455-478`), clave (proveedor, id, fuente, revisión); dispositivo y precisión se fijan en el constructor (`:279-281`). Una ranura de caché con expulsión tras 60 s sin uso (`bootstrap.py:267`, `asr/runtime_cache.py:13-84`).
- whisper.cpp: sin residencia; `--model` va en cada llamada (`whisper_cpp.py:246`). `docs/benchmarks.md:35-36` lo confirma ("reloaded on every call").
- sherpa ASR: un reconocedor por invocación (`sherpa_onnx_worker.py:112-119`, `:184-197`).
- Diarización: el proveedor queda cacheado (`bootstrap.py:566-572`); los modelos se recargan en cada pasada del hijo (`diarization/sherpa.py:176-178`).

**Concurrencia (pregunta 3):**
- Un proceso, un cómputo pesado: `application/compute_slot.py:1-12` (ADR-0010) serializa ASR, diarización y TTS.
- `FasterWhisperProvider` mantiene `_engine_lock` (RLock) durante toda la llamada (`faster_whisper.py:290`, `:330`); `close()` espera a la inferencia en curso (`:293-301`).
- `SingleRuntimeCache.use` ejecuta `create()` (carga de pesos) bajo el lock de caché (`runtime_cache.py:37-42`); `release()` no comprueba `_busy` (`:53-57`), a diferencia de `_expire` (`:80-84`). Lo llaman validación de modelos (`bootstrap.py:463`), `release_asr` (`:574-576`) y el sintetizador (`:657`). No encontré interbloqueo: el hilo que infiere no necesita el lock de caché mientras posee el del motor. Riesgo: `release()` espera a que termine el fragmento en curso (minutos con fragmentos de 30 min).
- Hilos CPU: whisper.cpp usa sus valores por defecto (4 según `docs/benchmarks.md:139-140`); faster-whisper no fija `cpu_threads` (`faster_whisper.py:240-247`); sherpa ASR usa 1 hilo (Whisper) o 2 (transductor) (`sherpa_onnx_worker.py:70`, `:105`); diarización `min(8, cpus-1)` (`diarization/sherpa.py:58-60`). El edge lab declara "no cross-process compute lock" (`edge_lab_worker.py:119`), así que sus medidas no reflejan contención real.
- Aislamiento del GIL: el worker de diarización documenta que la llamada nativa de sherpa retiene el GIL durante minutos (`diarization/worker.py:3-5`). faster-whisper corre en proceso sin ese aislamiento (hipótesis: el mismo riesgo con CTranslate2).

**Errores, OOM y cancelación (pregunta 5):**
- Errores de faster-whisper: excepciones de terceros se tipan (`faster_whisper.py:384-402`); un `RuntimeError` (p. ej. OOM CUDA) se marca PROVIDER_FAILED reintentable.
- Fallback de palabras: ante cualquier `Exception` no tipada reintenta el fragmento completo sin palabras (`:358-378`), no solo ante fallos de alineación. Duplica el trabajo y, si la causa es memoria, probablemente vuelve a fallar (hipótesis).
- Fallback CUDA→CPU: solo al construir el motor y solo para `RuntimeError`/`ValueError` (`:249-262`). En Linux `_preload_cuda_libraries` devuelve siempre True (`:140-142`), así que el aviso de CPU (`:236-238`) solo cubre Windows. Un `OSError` al cargar bibliotecas no degrada (hipótesis).
- Cancelación faster-whisper: se comprueba por segmento (`:440`, `:553-560`); la latencia de cancelación es de un segmento, hasta ~30 s de audio (hipótesis, sin medir).
- whisper.cpp: sondeo cada 0.1 s y terminate→kill a los 2 s (`whisper_cpp.py:286-306`). **Sin plazo**: el bucle (`:286-292`) solo sale con fin del proceso o cancelación. Código ≠ 0 → PROVIDER_FAILED no reintentable (`:296-297`), sin distinguir OOM ni señal. stdout/stderr a DEVNULL (`:277-279`): diagnóstico perdido.
- sherpa ASR: plazo de 1800 s por invocación (`sherpa_onnx.py:75`, `:233`, `:250-251`); con fragmentos de 30 min y CPU lenta podría agotarse (hipótesis). Cancelación y plazo matan el grupo con SIGKILL (`:319`). Los errores de E/S se convierten con `from None` (`:161-162`, `:315`), lo que oculta la causa. Un fallo descarta los segmentos parciales (`:262-304`). Los crashes nativos y el OOM quedan dentro del hijo y solo aparecen como código ≠ 0.
- Diarización: el código de salida del hijo no se inspecciona (`diarization/sherpa.py:239-245`); sin plazo; "sin END" se convierte en RuntimeError y luego en PROVIDER_FAILED (`:409-415`).
- Normalizador FFmpeg: sin plazo (`audio/ffmpeg.py:253-291`, espera final sin timeout `:280`). Cualquier código ≠ 0 se reporta como CORRUPTED_MEDIA (`:280-281`, `:576-580`) y stderr se descarta (`:200`, `:318-323`): un fallo de disco o de la herramienta parece un medio corrupto. La cancelación es correcta (terminate, 1 s de gracia, kill; `:360-373`).
- ffprobe: plazo de 15 s (`audio/ffprobe.py:37`, `:130`), pero `subprocess.run` no fija `stdin=DEVNULL` (`:124-131`), a diferencia de la regla de AGENTS.
- Formas de onda: plazo de 600 s con watchdog (`audio/waveform_peaks.py:139`, `:219`); un fallo se devuelve como "no decodificable".
- Edge lab: `apply_limits` limita RLIMIT_AS, es decir memoria virtual y no RSS (`edge_lab_worker.py:58-77`; `docs/edge-lab-results.md:31` lo declara).

**Recursos y fugas (pregunta 4):**
- `faster_whisper.py:97`, `:151`: `_dll_directory_handles` crece con cada carga en Windows. Fuga leve y acotada por el número de cargas.
- Copias: cada fragmento se materializa en memoria (`inference_audio.py:116`, `:125-132`; ~58 MB para 30 min + solape) y luego se copia a disco en whisper.cpp (`whisper_cpp.py:197-198`) y en sherpa (`sherpa_onnx.py:131-136`).
- Diarización: audio completo en memoria, int16 y luego float32 (`diarization/sherpa.py:289-290`). 1 h 47 min ≈ 102,7 M muestras ≈ 411 MB en float32 en el padre, más el bloque que lee el hijo (`diarization/worker.py:28`). Cálculo aritmético, no medido.
- Referencias a modelos antiguos: `RemoveModel` solo invalida la diarización (`bootstrap.py:829`, `:566-572`). El runtime ASR residente no se libera al borrar un modelo, y `_engine_for` reutiliza el motor si la clave coincide sin revisar archivos (`faster_whisper.py:466-468`). Permanece hasta 60 s tras el último uso (hipótesis: un trabajo podría usar un modelo ya borrado).
- Temporales de audio en la caché XDG (`bootstrap.py:517-522`); con muerte abrupta del proceso no hay limpieza (hipótesis).

#### 5. Seguridad y privacidad
- El `snapshot_dir` de Buzz es ruta de host y solo se usa en application (`application/ports/external_models.py:31-38`, `application/import_external_model.py:105`); no aparece en la capa de interfaces.
- Buzz: verificación solo por tamaño, sin hash (`buzz_cache.py:117-149`, `:139`). El import enlaza (hardlink) los ficheros al almacén VOZ (`infrastructure/model_storage.py:442`): una modificación externa afectaría al modelo copiado (hipótesis, riesgo bajo).
- Descarga automática de FFmpeg cuando falta, activa por defecto y desactivable con `VOZ_FFMPEG_AUTO_DOWNLOAD` (`audio/ffmpeg_tools.py:14`, `:159`). URL fijada por commit y SHA-256 (`:33-34`, `:190`). Es tráfico de red en ejecución; contrastar con la regla local-first de `AGENTS.md`. Remitir a seguridad.
- Sin red en modelos: `HF_HUB_OFFLINE=1` (`sherpa_onnx.py:244`) y `local_files_only=True` (`faster_whisper.py:475`).
- Temporales: audio y peticiones con modo 0600 (`sherpa_onnx.py:129`, `:158`, `:235`); directorio 0700 (`whisper_cpp.py:190`); JSON del edge lab 0600 (`edge_lab_worker.py:225`).

#### 6. Pruebas y evidencias
- Hay tests de cancelación y plazo: whisper.cpp (`tests/unit/infrastructure/asr/test_whisper_cpp.py:459`), sherpa (`test_sherpa_onnx.py:124`, `:138`, `:292`, `:314`), ciclo de vida de faster-whisper (`test_faster_whisper_lifecycle.py:227`, `:269`), diarización (`tests/unit/infrastructure/diarization/test_sherpa_provider.py:242`, `:254`), FFmpeg (`tests/integration/audio/test_ffmpeg_media_normalizer_integration.py:175`), fragmentación (`tests/unit/application/test_chunked_transcription.py:87`) y palabras en solapes (`tests/unit/application/test_word_timestamps.py:116`, `:199`). Ninguno ejecutado.
- Huecos: `diarization/worker.py` sin referencia en tests (grep 0); `runtime_cache.py` aparece en un solo archivo; no hay prueba de concurrencia entre `release()` y `use()`; no hay prueba de latencia ni de ventanas solapadas en sherpa (lo reconoce `docs/sherpa-onnx-asr.md:46-49`).

#### 7. Preparación para STT en tiempo real
- **Streaming real del motor** (entrada y salida incrementales): no existe en ningún adaptador. No hay `OnlineRecognizer` ni equivalente (búsqueda sin coincidencias). `ModelCapability.REALTIME` está definida (`domain/entities/model_descriptor.py:35`) pero ningún catálogo la declara.
- **Salida incremental dentro de una llamada**: faster-whisper emite segmentos de forma perezosa (`faster_whisper.py:439-444`), pero la lista se devuelve al final. sherpa ASR escribe eventos JSONL por ventana (`sherpa_onnx_worker.py:171-181`; `sherpa_onnx.py:262-304`), que el padre acumula; no se exponen a la API.
- **Pseudostreaming por ventanas** (no equivalente al anterior): sherpa ASR trabaja con ventanas independientes de 30 s, sin solape (`sherpa_onnx_worker.py:21`, `:149-161`); el pipeline trocea en fragmentos de 30 min con 5 s de solape (`chunked_transcription.py:86-87`).
- **SSE**: informa del progreso de un trabajo por polling (`interfaces/api/job_events.py:52-63`; `ROADMAP.md:107`); no transporta audio.
- Impedimentos: contrato batch (`ports/transcription.py:257-272`); `TranscriptionOptions` sin campos de flujo (`:213-229`); whisper.cpp copia hasta EOF (`whisper_cpp.py:197-198`); sherpa escribe el fichero completo antes de lanzar (`sherpa_onnx.py:128-136`); normalización completa y validada antes de publicar (`ffmpeg.py:451-463`); una ranura de cómputo global (`compute_slot.py`); checkpoints por fragmento (`recoverable_transcription.py:167-183`).
- Puntos de extensión: `on_position` (`ports/transcription.py:227`), `TranscriptionCancellationToken` (`:48-55`), `SingleRuntimeCache` (residencia) y el protocolo JSONL de sherpa como precedente de eventos. Decisiones abiertas para S17.01 (`ROADMAP.md:614`): motor, transporte, tamaño de ventana y solape, y si el motor vive en proceso o en worker (la diarización ya eligió worker por el GIL).
- **Latencia (evidencia)**: solo hay RTF por lote. `docs/benchmarks.md:110-124` (n=1, equipo del autor, incluye GPU RTX 4060 Laptop): faster-whisper CUDA turbo 0.025 (cortos) y 0.023 (largo); CPU int8 0.242 y 0.206; whisper.cpp CPU 0.804 y 0.735. Carga: 2.6 s en CUDA, 20.8 s en CPU int8 y 12.2 s en whisper.cpp (`:114-115`). No hay medida de latencia por ventana ni de primer segmento. Con RTF 0.24 en clips de 36 s, una ventana corta de unos segundos no tiene garantía de baja latencia (hipótesis: costes fijos por llamada).
- **¿Puede un motor actual procesar ventanas de baja latencia?** No con la arquitectura actual. faster-whisper es el único que evita recargar el modelo entre llamadas, pero el contrato es por lote y el coste por ventana no está medido. whisper.cpp y sherpa ASR cargan el modelo en cada invocación.
- **¿Es la diarización compatible con tiempo real?** No. Requiere todo el audio (`diarization/sherpa.py:267-290`), el motor es offline (`:98`, `OfflineSpeakerDiarization`) y el modo de rango repite la pasada completa (`:357-365`, `:434-446`). Es posprocesamiento. El comentario de `sherpa.py:54-55` da 70 s con 8 hilos para 11 min de audio; no verificado aquí.

#### 8. Top 5 hallazgos
| ID | Severidad | Hallazgo | Evidencia | Impacto | Recomendación |
|---|---|---|---|---|---|
| SPEECH-01 | alta | No hay streaming real: contrato batch, entradas completas y ningún motor con capacidad de tiempo real | `ports/transcription.py:257-272`; `whisper_cpp.py:197-198`; `sherpa_onnx.py:128-136`; `ROADMAP.md:614` | S17 no tiene camino técnico; el pseudostreaming con invocaciones repetidas es costoso (carga por llamada en whisper.cpp y sherpa) | Decidir motor, transporte y residencia en el ADR de S17.01; medir latencia por ventana, no solo RTF |
| SPEECH-02 | alta | La diarización es offline y requiere audio completo; el modo de rango repite la pasada | `diarization/sherpa.py:267-290`, `:357-365`, `:434-446` | No sirve para tiempo real; memoria de ~411 MB en float32 para 1 h 47 min (cálculo) | Tratarla como posprocesamiento; medir el coste del segundo pase y la memoria pico |
| SPEECH-03 | media | whisper.cpp y el normalizador FFmpeg no tienen plazo, y los errores de herramienta se pierden o se clasifican como medio corrupto | `whisper_cpp.py:286-292`, `:278-279`, `:296-297`; `ffmpeg.py:253-291`, `:280-281`, `:200` | Un proceso colgado bloquea el compute slot hasta cancelar; diagnóstico insuficiente | Decidir plazo por proceso, conservar stderr truncado y separar fallo de herramienta de medio corrupto |
| SPEECH-04 | media | Solape y límites sin deduplicación textual; sherpa no solapa sus ventanas de 30 s | `sherpa_onnx_worker.py:149-161`; `docs/sherpa-onnx-asr.md:46-49`; `chunked_transcription.py:114-141`; `docs/benchmarks.md:237-241` | WER global 31,3 % con 10 min frente a 52,0 % con 30 min en corpus sintético n=1; no es un bug demostrado | Medir con audio real antes de cambiar la ventana o el solape; no tratarlo como defecto confirmado |
| SPEECH-05 | media | Liberación de modelos: `release()` ignora `_busy`, `RemoveModel` no libera el runtime ASR y la reutilización no revisa archivos | `runtime_cache.py:53-57`, `:80-84`; `bootstrap.py:463`, `:829`; `faster_whisper.py:466-468` | Bloqueos de hasta un fragmento; posible uso de un modelo borrado hasta 60 s | Definir la política de invalidación y añadir un test de concurrencia y de borrado |

Otros hallazgos (sin ranking): ruta de recorte latente (`sherpa_onnx.py:144`); fallback de palabras demasiado amplio (`faster_whisper.py:358-378`); descarga de FFmpeg activa por defecto (`ffmpeg_tools.py:159`); `TRANSLATION` declarada sin implementar (`asr/catalog.py:17`); probe nativo en proceso del servidor (`asr/options.py:86-89`).

#### 9. No verificado
- No se ejecutó ningún test, benchmark ni motor. Las cifras de RTF y de carga provienen de `docs/benchmarks.md` (n=1, corpus sintético, sin latencia por ventana) y no se reproducen aquí.
- Comportamiento interno no comprobado: GIL durante la inferencia de CTranslate2; OOM y abort nativo; granularidad real de cancelación en faster-whisper; semántica de `--offset-t` en whisper.cpp; `OfflineSpeakerDiarization` y `from_whisper` de sherpa-onnx. Todo lo marcado como hipótesis queda pendiente.
- Interbloqueo y carreras de `SingleRuntimeCache`: análisis estático, sin escenario reproducido.
- Pico de memoria de diarización: cálculo, no medición.
- Descargas y hashes de FFmpeg: no contrastados (sin red).
- Partes superficiales (11 archivos, ver coverage): catálogos y descriptores, parseo de streams de ffprobe, instalación de modelos de diarización (área de seguridad).

Cobertura por archivo: `coverage_speech.tsv` (carpeta de trabajo de la auditoría, fuera del repositorio).
