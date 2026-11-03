# 10 · Preparación para STT en tiempo real

HEAD `96284c5`. Este documento sintetiza las secciones 7 de los ocho informes. No es un diseño ni un contrato: cada dimensión recoge el estado actual, la evidencia, la brecha y las preguntas abiertas para S17.01 (`ROADMAP.md:608-618`). Marcas de origen:
- **[O]**: observado en código.
- **[D]**: documentado, sin comprobar.
- **[I]**: inferido.
- **[NV]**: no verificado.

## Resumen
Hoy V no tiene ninguna pieza del camino en vivo: captura, transporte bidireccional, puerto de streaming, modelo de sesión e inferencia incremental. Sí tiene piezas reutilizables:
- token de cancelación;
- tipos de segmento y palabra con invariantes;
- `ModelCapability.REALTIME` declarada;
- reloj inyectable;
- `ComputeSlot` y `AdmissionGate`;
- plantilla de consentimiento cloud que falla cerrado (STT);
- stores de alta frecuencia en la UI.

La diarización es exclusivamente offline.

## 1. Captura de micrófono
- **Estado [O]:** no existe. No hay ninguna coincidencia de `getUserMedia`, `MediaRecorder`, `AudioWorklet` ni `mediaDevices` en `apps/web/src`. `AudioContext` solo se usa para reproducir y amplificar (`apps/web/src/components/AudioPlayer.tsx:37-48`).
- **Brecha:** falta captura, permisos, selección de dispositivo e indicador visible.
- **Preguntas:**
  - ¿AudioWorklet con PCM16 o MediaRecorder (Opus, decodificado en el servidor)?
  - El modo LAN por IP no es un contexto seguro para `getUserMedia` [I].
  - `Permissions-Policy: microphone=(self)` ya está concedido (`src/voz/interfaces/api/security_headers.py:18`) [O]. ¿Se mantiene?

## 2. Transporte cliente-servidor
- **Estado [O]:**
  - Solo hay SSE servidor→cliente para progreso, por sondeo de 0,5 s y keepalive de 15 s (`src/voz/interfaces/api/job_events.py:52-53`).
  - El audio entra como cuerpo o multipart completo.
  - `host_guard.py:52-61` y `server_auth.py:77-86` ya tratan el scope `websocket`, pero no hay rutas y `uv.lock` no contiene `websockets` ni `wsproto` (uvicorn 0.52.4).
  - El proxy de Vite no tiene `ws: true` (`apps/web/vite.config.ts:21-27`).
- **Brecha:** no hay canal de subida incremental.
- **Preguntas:** WebSocket (dependencia nueva, requiere aprobación); subida HTTP en streaming (requisitos de HTTP/2 en el navegador [NV]); o segmentos cortos idempotentes con `seq` más SSE. Para WebSocket habría que validar `Origin` en el handshake. Detalle en `06` §7.

## 3. Audio PCM y normalización
- **Estado [O]:**
  - La normalización pasa por FFmpeg, solo con archivos completos y validación antes de publicar (`src/voz/infrastructure/audio/ffmpeg.py:451-463`).
  - whisper.cpp lee hasta EOF (`src/voz/infrastructure/asr/whisper_cpp.py:197-198`).
  - sherpa escribe el archivo completo antes de lanzar (`src/voz/infrastructure/asr/sherpa_onnx.py:128-136`).
- **Brecha:** no hay ruta de frames en memoria con formato declarado (tasa, canales, muestra).
- **Preguntas:** ¿se remuestrea en el navegador o en el servidor? ¿Qué tamaño de frame se usa?

## 4. VAD
- **Estado [O]:** en el código propio no hay VAD para el flujo. El silencio solo existe a nivel de segmento (`tests/unit/application/test_quality_flags.py:44`) y, como opción del motor, en lote (ver `03` §4).
- **Preguntas:** ¿VAD del motor, de sherpa-onnx o en el cliente? ¿Qué umbral de fin de enunciado se usa?

## 5. Inferencia incremental
- **Estado [O]:** ningún adaptador hace streaming real.
  - faster-whisper genera segmentos perezosos, pero devuelve la lista al final (`src/voz/infrastructure/asr/faster_whisper.py:439-444`).
  - sherpa ASR usa ventanas de 30 s sin solape (`sherpa_onnx_worker.py:21`, `:149-161`).
  - whisper.cpp y sherpa cargan el modelo en cada invocación.
- **Brecha:** hay que distinguir streaming real del motor de pseudostreaming por ventanas. Hoy solo es posible lo segundo, y con coste por ventana sin medir.
- **Preguntas:** ¿qué motor local usar (p. ej. un reconocedor online de sherpa-onnx [I], o faster-whisper con ventanas)? ¿Qué ventana y qué solape?

## 6. Resultados parciales y finales
- **Estado [O]:**
  - No hay concepto de parcial ni final en el dominio ni en los puertos.
  - `Segment` exige texto no vacío y `end_ms > start_ms` (`src/voz/domain/entities/segment.py:15-28`).
  - La identidad de segmento se deriva del índice (`src/voz/application/job_runner.py:715`).
  - La UI identifica la vista previa con la clave `start:end:text` (`apps/web/src/components/LivePreview.tsx:57`).
- **Brecha:** faltan identidad estable por enunciado, revisión, y finales inmutables y ordenados.
- **Preguntas:** ¿un evento separado del `Segment` persistido (`01` §7, `02` §7)? ¿Hace falta un campo de origen `asr`/`user`?

## 7. Sesiones
- **Estado [O]:** no existe el concepto. `TranscriptionJob` y `Transcript` exigen `media_asset_id` (`transcription_job.py:129`, `transcript.py:21`).
- **Preguntas:**
  - ¿Basta una máquina de estados pequeña (`01` §7 propone CREATED→LISTENING→DRAINING→CLOSED/FAILED)?
  - ¿La sesión produce un `Transcript` al cerrar o es efímera?

## 8. Cancelación
- **Estado [O]:** `TranscriptionCancellationToken` (`src/voz/application/ports/transcription.py:47-53`) y `_AnyEventToken` (`job_runner.py:146`) son reutilizables. En OpenAI directo y ElevenLabs la cancelación no corta la petición en vuelo (`04` TTS_CLOUD-05).
- **Preguntas:** cierre del navegador, inactividad y apagado del servidor.

## 9. Backpressure
- **Estado [O]:** la cola de jobs se deduplica por id, pero no hay ninguna cola acotada por bytes ni por segundos. La síntesis acumula todo el PCM (`src/voz/application/synthesis/runner.py:269-285`). Las respuestas cloud se leen sin tope (`04` §4).
- **Preguntas:** ¿qué límite (segundos o bytes) y qué política al llenarse: rechazar con código, descartar o marcar hueco?

## 10. Reconexión
- **Estado [O]:** SSE sin `id` ni `Last-Event-ID`; cada conexión recibe una instantánea (`job_events.py:32-34`). La reconexión del cliente se delega al navegador (`apps/web/src/api/jobEvents.ts:27`).
- **Preguntas:** ¿reanudar por `sequence`? Requiere retener audio o eventos, lo que entra en tensión con la privacidad (`06` Q6).

## 11. Concurrencia CPU/GPU
- **Estado [O]:**
  - Un único `ComputeSlot` FIFO, sin prioridad, para ASR, diarización, TTS y validación (`src/voz/application/compute_slot.py:53-89`); las llamadas cloud también lo ocupan (`04` §4).
  - El runtime ASR se libera tras 60 s inactivo (`src/voz/bootstrap.py:267`) y desaloja al cambiar de modelo.
- **Brecha:** una sesión en vivo esperaría detrás de un batch de horas.
- **Preguntas:** ¿prioridad, preemption, slot dedicado o rechazo con código?

## 12. Persistencia opcional
- **Estado [O]:** la cola durable reencola todo lo no terminal al arrancar (`job_runner.py:292-297`) y asume chunks de 30 min (`job_runner.py:81`).
- **Conclusión de `05`:** la sesión en vivo no debe convertirse en un job durable.
- **Preguntas:** ¿qué se persiste (metadatos de sesión, registro de consentimiento, finales) y qué nunca (audio y parciales por defecto)?

## 13. Privacidad
- **Estado [O]:** no se captura audio hoy. `media_storage` hace los originales inmutables, y la API compatible conserva el audio de cada petición (`src/voz/application/compatible_audio.py:224`).
- **Preguntas:**
  - ¿Buffer solo en memoria?
  - ¿Opt-in separado para guardar?
  - ¿TTL y borrado?
  - ¿Logs sin texto?

## 14. Consentimiento cloud
- **Estado [O]:**
  - **STT por trabajo:** falla cerrado (`src/voz/interfaces/api/jobs.py:84` → `create_transcription_job.py:170-175`).
  - **Endpoints:** el consentimiento se guarda al registrarlos (`src/voz/application/ports/compatible_endpoints.py:150-152`).
  - **TTS en nube:** no hay consentimiento por trabajo en el servidor.
  - **Reanudación:** reencola sin reconfirmar.
  - No se observó ningún fallback automático a la nube (`04` §5).
- **Preguntas:** ¿consentimiento por sesión, revocable y con caducidad? ¿Se acepta `http://`, hoy permitido (`compatible_endpoints.py:76`)?

## 15. Pruebas
- **Estado [O]:**
  - Patrón sólido de interleavings con reloj inyectado (`tests/integration/application/test_job_runner_cancel_races.py:45-62`).
  - Fixtures de audio: solo tonos de 440 Hz (`tests/fixtures/README.md:3-5`).
  - No hay pruebas de WebSocket de datos, backpressure ni reconexión.
- **Preguntas:** fuente de frames inyectable con reloj virtual; formas de onda generadas en el test (silencio, ráfagas, huecos).

## 16. Medición de latencia
- **Estado [D]:** solo RTF por lote, n=1, en el equipo del autor (`docs/benchmarks.md:110-124`), con carga del modelo de 2,6 a 20,8 s. No hay latencia por ventana ni de primer resultado.
- **Brecha:** no existe un presupuesto definido (S17.05).
- **Preguntas:**
  - En CI solo es determinista lo que se cuenta con reloj inyectado (eventos, sondeos, reintentos).
  - Los milisegundos reales y el RTF deben ser opt-in en hardware real (`08` §6b).
