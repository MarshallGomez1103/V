### INFORME — tts_cloud

**Metadatos:** fecha 2026-10-21 · HEAD 96284c5 (main, árbol limpio al inicio) · rutas revisadas: las 35 de files_tts_cloud.tsv (src/voz/infrastructure/tts/*, cloud/*, secrets.py, edge_lab_tts.py, synthesis_storage.py, model_registry.py, model_storage.py, artifact_download.py, custom_model*.py, custom_models.py, disk_space.py). Contexto leído: AGENTS.md, ADR-0006 y ADR-0010, docs/licenses/models.md, ROADMAP.md §17, y el flujo de consentimiento en application/ e interfaces/ solo para verificarlo · alcance: estático · límites: sin ejecución, sin red, sin medir RAM ni latencia.

**Cobertura:** asignados 35 · superficial 6 · profunda 29 · omitidos 0 · ~líneas 7.798 · dependencias principales: sherpa-onnx (extra `diarization`, pyproject.toml:39-42), numpy (solo en el worker), stdlib (urllib, http.client, tarfile), puertos de application/ports.

#### 1. Responsabilidades y dependencias

- **TTS implementado (verificado):** (a) sherpa-onnx local, un proceso hijo por fragmento: src/voz/infrastructure/tts/sherpa_provider.py:37-59 y subprocess_provider.py:144-315; el worker fuerza `provider="cpu"` (tts/sherpa_worker.py:73). El servidor nunca importa sherpa_onnx para TTS; solo comprueba `find_spec` (src/voz/bootstrap.py:391-392). (b) OpenAI-compatible `/audio/speech`, local o en nube (cloud/openai_compatible.py:312-431), cableado en bootstrap.py:620-633. `tts/fake.py` no está cableado en producción. No existe TTS nativo de OpenAI ni de ElevenLabs (ElevenLabs es solo STT). Edge Lab solo mide (edge_lab_tts.py:37-160).
- **Modelos seleccionables:** catálogo fijo de 7 modelos (tts/catalog.py:136-249): 4 Piper (es_MX ald, es_MX claude int8, es_ES davefx, en_US lessac), 2 Kitten (nano, mini) y 1 Kokoro multilingüe. Las voces salen de la metadata ONNX (tts/families.py:330-361); los nombres curados de catalog.py:108-133 son respaldo. Sus propios comentarios marcan como no verificados el orden de Kitten y los ids de Kokoro en inglés. Además hay modelos por endpoint declarados por el usuario (compatible_endpoints.py:115-160) y modelos importados (custom_models.py:707-712).
- **Nombre de voz:** `es_MX-claude-high` (tts/catalog.py:151-158) usa "Claude" como nombre del dataset de Piper. La UI lo mostrará así. Es un riesgo de confusión de marca, no una afiliación. Para documentación o el responsable.
- **Instalación:** explícita y confirmada (application/model_tasks.py:211 exige `confirm is True`). Descarga pinneada por tamaño y SHA-256 (artifact_download.py:51-69) antes de extraer. Extracción manual de solo los archivos del catálogo, espeak-ng-data y las notas (tts/model_store.py:167-222), sin extractall. Publicación atómica con `.voz-tts.json` como marca de commit (model_store.py:367-383).
- **Eliminación:** tts/model_store.py:385-390 (`_clear`, no sigue enlaces), con confirmación exacta del id en application/model_manager.py:241-243.
- **Integridad en uso:** solo tamaño de archivo (model_store.py:254-271). El propio código lo declara como ponytail.
- **Acoplamiento de empaquetado:** el runtime de TTS depende del extra `diarization` (pyproject.toml:39-42).

#### 2. Arquitectura hexagonal
- **Comprobado OK:** los puertos SpeechSynthesisProvider (application/ports/speech_synthesis.py:152), TranscriptionProvider (ports/transcription.py:257-273), CompatibleEndpointStore y ProviderSecretsPort tienen implementación en infraestructura. sherpa_onnx se importa solo dentro de procesos hijos (tts/sherpa_worker.py:65).
- **Sospecha (baja):** la regla de consentimiento para guardar un endpoint aparece dos veces, en la interfaz (interfaces/api/providers.py:177-179) y en el puerto (application/ports/compatible_endpoints.py:150-155).
- **Sospecha (media-baja):** conviven dos modelos de localidad, el enum `SynthesisLocality` (ports/speech_synthesis.py:57-61) y los booleanos `cloud`/`remote` de ModelRegistration (ports/transcription_options.py:21-23). compatible_audio.py:93-95 y 113-117 filtra con booleanos.

#### 3. Diseño y mantenibilidad
- **Duplicación de transporte:** `HttpRequest`, `HttpResponse` y `TransportError` están definidos dos veces (cloud/openai_transport.py:20-60 y cloud/elevenlabs_transport.py:31-57), con contratos distintos: el de OpenAI tiene `abort` y el de ElevenLabs no.
- **Tres validadores de rutas relativas:** tts/model_store.py:138-147 (`_unsafe`), custom_models.py:92-103 (`safe_relative`) y model_storage.py:195-214 (`_custom_intact`). Riesgo de divergencia.
- **Errores duplicados:** `_fail`, `_failure`, `_failed` y `_synthesis_error` (cloud/openai_transcription.py:65, cloud/elevenlabs_scribe.py:94, cloud/openai_compatible.py:238-251).
- **Código parcial:** la familia `matcha` figura en families.py:72-76 y custom_models.py:63, pero `discover_files` la rechaza (families.py:184-185). `RoutingModelStore.download` no tiene rama para `custom-` (model_registry.py:254-275). Hipótesis, sin verificar: no hay llamadas que lo alcancen.
- **Tamaño:** custom_models.py (712 líneas) mezcla HTTP, parseo, política de licencias y staging. No es violación SOLID por tamaño.

#### 4. Concurrencia, errores y recursos
- **Hijo por fragmento:** Popen en subprocess_provider.py:252-258, timeout 120 s (`:55`, `:271-279`), terminate y luego kill (`:317-331`), `close()` (`:333-340`), hilos daemon de lectura y escritura (`:264-270`). Errores tipados (`:284-296`, `:309-312`). Correcto.
- **Compute slot:** compartido por STT, diarización y TTS (src/voz/bootstrap.py:578 y 650-656; application/synthesis/runner.py:84-85). Las llamadas a nube también ocupan ese slot mientras esperan red (hipótesis de impacto en latencia, no medida).
- **Cancelación en vuelo:** sí en OpenAI-compatible y TTS compatible (openai_compatible.py:159-163; openai_transport.py:75-). No en OpenAI directo (cloud/openai_transcription.py:261, sin `abort`) ni en ElevenLabs (elevenlabs_scribe.py:243-252; elevenlabs_transport.py:117-122). En esos dos casos la espera de respuesta dura hasta 600 s (openai_transcription.py:105) o 3600 s (elevenlabs_scribe.py:56-57, 241).
- **Lectura sin tope:** cloud/openai_transport.py:63, 66 y 104 leen el cuerpo completo. openai_compatible.py:413-428 no limita el audio recibido. ElevenLabs trunca en silencio a 64 MiB (elevenlabs_transport.py:86).
- **Audio completo en memoria:** openai_transcription.py:159 (`audio.read()`) y elevenlabs_scribe.py:128 si el flujo no es seekable.
- **Reintentos:** OpenAI reenvía el WAV entero en cada reintento (openai_transcription.py:262-283). ElevenLabs no reintenta el POST (elevenlabs_scribe.py:185).
- **Disco:** la instalación TTS no comprueba espacio libre (tts/model_store.py:316-365). Sí lo hacen la importación personalizada (custom_models.py:436) y ASR (model_storage.py:135-137).
- **Memoria sin control:** en tts/ y en custom_model_worker no hay RLIMIT ni cgroup. Solo Edge Lab usa RLIMIT_AS (edge_lab_worker.py:63-70). La RAM del catálogo es solo una pista (catalog.py:104, 203, 223, 247). La admisión de STT sí la comprueba (create_transcription_job.py:194, 240-252), pero la de TTS no (create_synthesis_job.py:94-143).

**Controles de CPU, GPU y memoria (lo que hay):** hilos = min(4, núcleos-1) (subprocess_provider.py:78-80), pasados a sherpa como `num_threads` (sherpa_worker.py:72). Solo CPU: capacidad CPU en catalog.py:73 y `provider="cpu"` en sherpa_worker.py:73. Fragmentos de 400 caracteres (sherpa_provider.py:34) y una frase por generate (sherpa_worker.py:29). Timeout de 120 s. Sin tope de memoria.

#### 5. Seguridad y privacidad

**Rutas que envían audio o texto fuera del equipo (todas):**
1. OpenAI STT: cloud/openai_transcription.py:49 (URL), :159 (audio), :237-284 (POST, transporte en :261 y :266); transporte openai_transport.py:51-72 (urlopen en :62); cableado en bootstrap.py:494-495.
2. ElevenLabs STT: cloud/elevenlabs_scribe.py:49 (URL), :178-253 (POST en :244); glosario como keyterms en :207-215; transporte elevenlabs_transport.py:63-92; cableado bootstrap.py:505.
3. OpenAI-compatible STT en nube: cloud/openai_compatible.py:191-235 (URL en :216, reutiliza openai_transcription.py:237); prompt en openai_transcription.py:253-254.
4. OpenAI-compatible TTS en nube, envía TEXTO: cloud/openai_compatible.py:366-431 (cuerpo JSON en :396-404, URL en :406, transporte en :413); cableado en bootstrap.py:626-631.
5. Prueba de conexión (clave y GET /models): cloud/openai_compatible.py:452-477 (GET en :456-463); ruta interfaces/api/providers.py:235-252.
6. Solo metadatos, sin audio ni texto del usuario: HEAD de la URL del modelo (custom_models.py:316-329, en prepare, antes de confirmar), API de HF (custom_models.py:341), descargas de pesos (artifact_download.py:93; tts/model_store.py:345; model_storage.py:258-265 y :689).
- No hay ruta de nube desde la API local compatible: application/compatible_audio.py:89-132 excluye cloud y remote.

**Consentimiento, verificado de punta a punta:**
- **STT en nube, cierra en fallo:** interfaces/api/jobs.py:84 (StrictBool, por defecto False) → :283 → application/create_transcription_job.py:170-175 rechaza sin `cloud_consent is True`. La localidad sale de cloud/catalog.py:36 (OpenAI y ElevenLabs siempre True) y de openai_compatible.py:141.
- **Endpoint en nube, cierra en fallo:** ports/compatible_endpoints.py:150-155 (no se construye sin consentimiento); cloud/compatible_store.py:37-48 y :46 (una entrada inválida se descarta); openai_compatible.py:116-121 (cada llamada revalida la localidad y el consentimiento); interfaces/api/providers.py:177-179 (loopback nunca registra consentimiento).
- **Sin fallback automático:** bootstrap.py:489-512 elige el proveedor solo por el `provider_id` del modelo elegido; bootstrap.py:407 lo declara. Los fallback que existen en el código son locales (infrastructure/asr/faster_whisper.py:163; application/asr_device_selection.py:48).
- **TTS en nube, NO cierra por trabajo:** create_synthesis_job.py:94-143 no tiene parámetro de consentimiento ni comprueba la localidad. CreateSynthesisBody (interfaces/api/synthesis.py:93-100) no tiene campo de consentimiento. La confirmación existe solo en la UI (apps/web/src/components/SpeakWorkspace.tsx:147-152 y :284-287). Lo único que frena es el consentimiento por endpoint.
- **Reanudación sin reconfirmar:** application/job_runner.py:292-298 (`recover`) reencola los trabajos no terminales sin volver a pedir consentimiento. Para endpoints sí se revalida (openai_compatible.py:120). OpenAI y ElevenLabs solo exigen que la clave exista (openai_transcription.py:156-157; elevenlabs_scribe.py:175).
- **Granularidad:** el consentimiento es un booleano por endpoint (compatible_endpoints.py:125), sin distinguir capacidad, sin caducidad y, en TTS, sin distinguir trabajo. Revocar = borrar el endpoint (providers.py:212-216) o quitar la clave.

**Hallazgos de seguridad:**
- **Clave al cambiar de host:** al editar base_url sin enviar `key`, la clave guardada se conserva (providers.py:182-185) y se envía al host nuevo (openai_compatible.py:391-395 y :221; openai_transcription.py:259-260). La UI lo indica: "Deja vacío para conservar la clave" (apps/web/src/i18n/messages/endpoints.ts:26). No hay prueba para la edición aceptada; test_providers_api.py:331-360 solo cubre la edición rechazada.
- **Nube en http://:** ports/compatible_endpoints.py:76-78 acepta el esquema http, y el consentimiento no exige https. Los pesos por URL también aceptan http (custom_models.py:167), y la URL de HF es configurable (custom_models.py:187).
- **Hijos con entorno completo:** custom_model_worker.py:70-75 (`env={**os.environ, ...}`) y tts/subprocess_provider.py:252-258 (sin `env`). Ambos cargan pesos no confiables en parsers nativos y el entorno incluye las claves de secrets.py:49-52. Sin RLIMIT (ver sección 4).
- **Pesos sin SHA-256:** model_storage.py:122-132 y :775-778 (sin hash, solo tamaño). custom_models.py:402-418 (hash solo si HF publica LFS) y :255 (URL sin hash). Los digests se calculan después de descargar (custom_models.py:527-554).
- **Redirecciones (hipótesis, sin verificar):** el camino de OpenAI directo usa urlopen (openai_transport.py:62), que sigue redirecciones con cabeceras. El host es fijo y el riesgo es bajo. El camino compatible las evita (openai_compatible.py:11-13).
- **Micrófono:** no hay captura. apps/web solo usa AudioContext para reproducir (apps/web/src/components/AudioPlayer.tsx:37-45). La cabecera Permissions-Policy ya concede `microphone=(self)` (src/voz/interfaces/api/security_headers.py:18).
- **Positivo:** claves en 0600 con escritura atómica (secrets.py:122-158). Las cabeceras con la clave tienen repr oculto (openai_transport.py:20-27). El worker sanea mensajes y rutas (tts/protocol.py:145-149).

**Licencias y restricciones documentadas (docs/licenses/models.md):**
- §3.4 (líneas 141-179) cubre los 7 modelos TTS, y el catálogo coincide con la tabla (líneas 152-160). Restricciones: Piper en-US y las voces fine-tuned heredan el dataset Lessac (investigación, no comercial) y espeak-ng-data es GPL-3.0 (se copia en la instalación del usuario).
- §4 (líneas 191-213): KittenTTS 2 tiene licencia restrictiva y no está en el catálogo. La importación acepta cualquier familia con la licencia que declare el usuario (custom_models.py:288-294), sin verificación.
- Los pesos no se redistribuyen y se instalan solo con confirmación.

#### 6. Pruebas y evidencias (nada ejecutado)
- **Existen:** tests/unit/infrastructure/tts/* (protocolo, familias, worker, proveedor de subproceso, catálogo, tienda); tests/unit/infrastructure/cloud/* (ElevenLabs, nube); test_openai_transcription.py y test_openai_cloud_opt_in.py; test_secrets.py; tests/integration/test_providers_api.py; test_tts_default_wiring.py; test_custom_models_default_wiring.py. Hay contrato en tests/contract/test_openai_compatible.py.
- **Huecos (por grep, sin ejecución):**
  - a. Consentimiento por trabajo en TTS nube: sin aserción de rechazo (tests/integration/test_synthesis_api.py:158 solo usa el id de nube).
  - b. Edición aceptada de URL con clave: sin prueba.
  - c. Rechazo de http:// en nube: sin prueba.
  - d. Cancelación en vuelo: solo durante la subida de ElevenLabs (tests/unit/infrastructure/cloud/test_elevenlabs_scribe.py:476) y durante el backoff de OpenAI (test_openai_transcription.py:351, 368).
  - e. Entorno heredado por hijos y pesos sin SHA: sin pruebas.
  - f. Tope de tamaño de respuesta: sin pruebas.
  - g. Voces de respaldo de Kitten y Kokoro: sin verificar.

#### 7. Preparación para STT en tiempo real
- **Reutilizable:** MultipartBody, con progreso y cancelación por bloque (cloud/elevenlabs_transport.py:95-140). `_abortable` y `_with_abort`, que cancelan a mitad de petición sin redirecciones ni proxies (openai_compatible.py:159-163; openai_transport.py:75-). La planificación de ventanas con solape y propiedad por punto medio (openai_transcription.py:200-235, 332-343, 352-410).
- **Impedimentos:** el puerto es batch (ports/transcription.py:265-273, recibe un BinaryIO abierto). No hay transporte WebSocket ni SSE: solo stdlib. Se lee el audio completo (openai_transcription.py:159). `SpeechSynthesisProvider.streaming` existe (ports/speech_synthesis.py:71) pero es False en todos.
- **Decisiones abiertas (ROADMAP.md:608-616, S17.01-S17.02):** motor local, transporte (WebSocket o HTTP troceado), alcance del consentimiento por sesión, retención de fragmentos (hoy el WAV de síntesis es inmutable en synthesis_storage.py) y presupuesto de coste: OpenAI 0,006 USD/min (cloud/openai_limits.py:38-54) y ElevenLabs 0,40 USD/h (elevenlabs_pricing.py:19), sin tope.
- **Riesgos de sesión continua de micrófono:** captura sin consentimiento vigente en el tiempo. Envío continuo a nube, con coste y exposición acumulada. El consentimiento actual no caduca ni se pide por sesión. En OpenAI y ElevenLabs la cancelación no corta la petición en vuelo. El slot de cómputo bloquea otras tareas. Si se acumula audio completo en memoria, la memoria crece sin límite.

#### 8. Top 5 hallazgos
| ID | Severidad | Hallazgo | Evidencia | Impacto | Recomendación |
|---|---|---|---|---|---|
| TTS_CLOUD-01 | alta | La clave guardada se envía al host nuevo tras editar base_url | interfaces/api/providers.py:182-185; cloud/openai_compatible.py:391-395, 221; tests/integration/test_providers_api.py:331-360 | Fuga de credencial a un tercero | Decidir si el cambio de host borra la clave o exige reingresarla. Añadir prueba de la edición aceptada |
| TTS_CLOUD-02 | alta | Los endpoints de nube aceptan http:// | ports/compatible_endpoints.py:76-78; custom_models.py:167 | Clave, audio y texto en claro | Decidir si la nube exige https (y qué excepción, si la hay, para LAN) |
| TTS_CLOUD-03 | alta | Hijos de validación y síntesis heredan el entorno completo y cargan pesos no confiables sin límites | custom_model_worker.py:70-75; tts/subprocess_provider.py:252-258; application: edge_lab_worker.py:63-70 (RLIMIT solo en Edge Lab) | Claves expuestas a parsers nativos; memoria sin tope | Decidir entorno mínimo y límites de recursos para hijos; pasar a seguridad e modelos |
| TTS_CLOUD-04 | media | TTS en nube sin consentimiento por trabajo en el servidor | application/synthesis/create_synthesis_job.py:94-143; interfaces/api/synthesis.py:93-100; apps/web/.../SpeakWorkspace.tsx:147-152 | Inconsistente con STT (create_transcription_job.py:170-175); la API se salta la confirmación de la UI | Decidir si cloud_consent por trabajo aplica también a TTS |
| TTS_CLOUD-05 | media | La cancelación no corta la petición en vuelo en OpenAI y ElevenLabs; los trabajos en nube se reanudan sin reconfirmar | cloud/openai_transcription.py:261; cloud/elevenlabs_scribe.py:243-252; application/job_runner.py:292-298 | Coste y audio enviado tras cancelar; envío automático tras reinicio | Pasar a QA una prueba de cancelación en vuelo. Decidir la política de reanudación en nube |

Otros riesgos medios (en la sección 5): pesos sin SHA-256 (model_storage.py:122-132) y lectura de respuestas sin tope (openai_transport.py:63, 66, 104).

#### 9. No verificado
- Ningún test, instalación ni build se ejecutó. El comportamiento de sherpa-onnx, los parsers nativos y los límites de memoria no se verificaron.
- Hipótesis sin probar: redirecciones de urllib con cabeceras (openai_transport.py:62); coste de RAM y latencia de los hijos; impacto del slot compartido con llamadas de red; nombres de voz de respaldo de Kitten y Kokoro.
- Upstream no contrastado en vivo (OpenAI, ElevenLabs, Hugging Face, releases de sherpa). Las licencias se tomaron solo de docs/licenses/models.md.
- Superficiales (6): cloud/elevenlabs_mapping.py (mapeo de palabras, líneas 80-178), custom_model_detection.py (salvo detect_download), model_registry.py (ManagedModelCatalog, 110-184), model_storage.py (partes 300-489, 560-647, 800-943 y 978-1024), synthesis_storage.py (open_for_reading, delete_job, _build_wav) y tts/fake.py (solo cabecera). Ver coverage_tts_cloud.tsv.
- No revisado a fondo fuera del área: application/job_runner.py, application/model_tasks.py, interfaces/api/synthesis.py (solo el modelo de entrada) y el contenido de los tests (solo nombres y grep).
- Pregunta abierta para el responsable del proyecto: ¿el consentimiento de TTS en nube debe ser por trabajo, como en STT? ¿Se acepta http:// en nube, aunque sea LAN?
