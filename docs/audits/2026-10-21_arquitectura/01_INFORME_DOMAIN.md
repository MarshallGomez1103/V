### INFORME — domain

**Metadatos:** fecha 2026-10-21 · HEAD 96284c5 · rutas revisadas: `src/voz/domain/` (19 archivos, 1 700 líneas; lista en `files_domain.tsv`) · alcance: inspección estática (lectura completa de los 19 archivos, `grep` de imports y de usos en `src/voz/application`, `src/voz/infrastructure`, `src/voz/interfaces`, lectura de `tests/unit/domain/` por nombres y conteo) · límites: no se ejecutó ningún test, linter ni tipador; no se auditó application/infrastructure/interfaces más allá de los usos citados; no se leyeron los ADR de `docs/adr/`.

**Cobertura:** asignados 19 · superficial 0 · profunda 19 · omitidos 0 · ~líneas 1 700 · dependencias principales: solo biblioteca estándar (`re`, `dataclasses`, `datetime`, `uuid`, `enum`, `typing`, `math`, `unicodedata`, `__future__`). Consumidores: `application` (job_runner, rediarize, edit_segment, quality_profiles), `infrastructure` (persistence, asr, tts, media_storage) e `interfaces` (api, cli).

#### 1. Responsabilidades y dependencias

- Todas las entidades son `@dataclass(frozen=True, slots=True)`; `grep` no encontró ningún `@dataclass` sin `frozen` en el dominio. Validación en `__post_init__` (p. ej. `src/voz/domain/entities/transcription_job.py:142`, `src/voz/domain/entities/synthesis_job.py:89`).
- Las entidades son en su mayoría objetos de valor validados. El comportamiento se concentra en tres sitios: `TranscriptionJob` (7 métodos públicos de transición o progreso, `transcription_job.py:124-349`), `SynthesisJob` (`synthesis_job.py:70-204`) y `Segment.edit_text` (`segment.py:83`).
- Anémicas o casi sin reglas: `Word`, `Project`, `Voice`, `MediaAsset`, `SynthesizedAudio`. `Transcript` declara en su docstring "identity and invariants" (`transcript.py:1`), pero solo valida identidad y fecha; no posee ni protege sus segmentos.
- Dependencia entre entidades de procesos distintos: `SynthesisJob` importa `InvalidJobTransition` desde el módulo de transcripción (`src/voz/domain/entities/synthesis_job.py:13`).
- Serialización dentro del dominio: `QualityProfile.to_dict` y `from_dict` (`src/voz/domain/entities/quality_profile.py:111`, `:124`), y `VadSettings.to_dict`/`from_dict` (`quality_profile.py:55`, `:64`). El docstring de `to_dict` dice "shown by the API" (`quality_profile.py:112`).

#### 2. Arquitectura hexagonal

- **Sin violación comprobada de dependencias.** Ninguno de los 19 archivos importa FastAPI, SQLAlchemy, ONNX, CTranslate2, FFmpeg, torch ni paquetes de `voz.application`, `voz.infrastructure` o `voz.interfaces` (verificado con `grep -rn "^\s*(from|import) "` sobre `src/voz/domain/`).
- **Violación de vocabulario comprobada (no de import).** El dominio nombra conceptos de proveedor:
  - `ComputePrecision` usa los valores del tipo de cómputo de CTranslate2, como `int8_float16` (`src/voz/domain/entities/processing_profile.py:20-24`). `ProcessingProfile` se describe como "Provider-neutral" (`processing_profile.py:1`).
  - `QualityProfile` está modelado sobre Whisper: `beam_size`, `condition_on_previous_text`, `no_speech_threshold` (`quality_profile.py:85-88`). `VadSettings` se documenta como "Silero VAD in Faster Whisper" (`quality_profile.py:32`).
  - `Segment.avg_logprob` es una métrica de Whisper (`segment.py:47`), aunque `TranscriptionSegment` del puerto también trae `no_speech_prob` y `compression_ratio` que el dominio no conserva (`src/voz/application/ports/transcription.py:123-140`).
  - `ModelCapability` cita "sherpa-onnx", "ENGINE_CAPABILITIES" y "GET /api/models" en su docstring (`model_descriptor.py:17-22`). `ENGINE_CAPABILITIES` vive en `src/voz/infrastructure/model_registry.py:51`, así que la documentación del dominio apunta a infraestructura.
- **Sospecha de frontera de presentación:** `to_dict`/`from_dict` en entidades (ver sección 1). No hay dependencia externa, pero el formato de API vive en el dominio.
- **Reglas de dominio fuera del dominio:** ver sección 3 (duplicación de validaciones en puertos, adaptadores y migraciones de esquema).

#### 3. Diseño y mantenibilidad

**Duplicación comprobada de reglas**

| Regla | Dónde está |
|---|---|
| Offsets enteros, no negativos, `start < end` | `word.py:9`, `segment.py:15`, `speaker_turn.py:11`; repetido en `src/voz/application/ports/transcription.py:142-144` y `:208`, `src/voz/application/ports/diarization.py:106`, y como `CHECK` en `src/voz/infrastructure/persistence/schema.py:109-110`. `segment.py:12-14` ya tiene un comentario `ponytail:` que acepta la duplicación. |
| Texto no vacío | `word.py:18`, `segment.py:24` (sin `strip`), `synthesis_request.py:29` (`strip` y NUL), `_validation.py:18` (`strip` y controles < 32), `model_descriptor.py:46` (`category` "C"), `filename_safety.py:13` (Cc, Cf y bidi). Hay cinco políticas distintas para "texto". |
| Código de error | `transcription_job.py:115` y `synthesis_job.py:61` (idénticas). |
| Marca temporal con zona | `transcription_job.py:107` no normaliza a UTC; `_validation.py:9` sí. Ambas se usan en entidades. |
| Monotonía temporal | `transcription_job.py:344` y `synthesis_job.py:198`. |
| Tabla de transiciones | `transcription_job.py:61-86` y `synthesis_job.py:36-50`: misma forma, implementadas dos veces. |
| SHA-256 / revisión de 40 hex | `media_asset.py:17`, `synthesized_audio.py:16`, `model_descriptor.py:14`; fuera del dominio: `src/voz/application/ports/model_installation.py:66`, `src/voz/application/ports/transcription_checkpoint.py:18`, `src/voz/infrastructure/custom_models.py:355` y `:408`. |
| Límite de 20 000 caracteres | `synthesis_request.py:18`; literal duplicado en `src/voz/infrastructure/edge_lab_tts.py:73`. |

**Tamaño y cohesión (sin marcar violación SOLID solo por tamaño)**

- `TranscriptionJob` mezcla cuatro responsabilidades: ciclo de vida (`state`), progreso global y por etapa (`progress`, `stage_progress`), tiempos (`started_at`, `stage_started_at`, `transcription_job.py:135-139`) y error (`error_code`). Los tiempos parecen telemetría para UI (`src/voz/interfaces/api/job_views.py`, `src/voz/interfaces/api/job_events.py`); (hipótesis) podrían ser una proyección y no parte del agregado.
- `ModelDescriptor` agrupa identidad, capacidades, procedencia de instalación (`source`, `revision`, `provenance`, `model_descriptor.py:148`) y perfil de ejecución (`profile`, `model_descriptor.py:72`).
- `ModelCapability` mezcla capacidades con hardware: `GPU` y `CPU` (`model_descriptor.py:36-37`) se asignan como capacidades en `src/voz/infrastructure/asr/catalog.py:19-20`, mientras `ProcessingProfile.device_preference` ya expresa lo mismo. `REALTIME` (`model_descriptor.py:35`) no tiene ningún uso en `src/voz`.
- Dos conceptos llamados "profile": `ProcessingProfile` (ejecución) y `QualityProfile` (decodificación). Riesgo de confusión al nombrar en API y persistencia.
- `SynthesisRequest` guarda `provider_id`, `model_id` y `voice_id` como `str` (`synthesis_request.py:63-65`), cuando `ModelDescriptor.identity` (`model_descriptor.py:137`) y `Voice` ya modelan esa identidad.
- Uso repetido de `cast(object, …)` para validar en tiempo de ejecución (16 apariciones, p. ej. `synthesis_request.py:83`, `model_descriptor.py:100`, `model_descriptor.py:129`). Es un patrón consistente, pero ruidoso.

**Reglas de estado y progreso** (detalle en hallazgo DOMAIN-02)

- `TranscriptionJob.with_progress` impide retroceder (`transcription_job.py:272-273`), pero `reopen_for_diarization` fija un progreso arbitrario (`transcription_job.py:313-332`). El llamador lo fija a 0,8 (`src/voz/application/job_runner.py:87`, `src/voz/application/rediarize.py:114-116`), así que el progreso baja de 1,0 a 0,8. El test lo confirma (`tests/unit/domain/test_transcription_job.py:443`).

**Nombres y código muerto:** `ModelCapability.REALTIME` sin uso (ver arriba). No se encontró código muerto adicional en el dominio por lectura.

#### 4. Concurrencia, errores y recursos

- Concurrencia: no aplica dentro del dominio. Las entidades son inmutables, no hay I/O ni estado compartido mutable.
- Reloj: las transiciones aceptan `at`, pero si no se pasa llaman a `datetime.now(UTC)` dentro del dominio (`transcription_job.py:201`, `:238`, `:275`, `:345`; `synthesis_job.py:134`). Es inyectable, pero el valor por defecto acopla el dominio al reloj del sistema.
- Errores: `InvalidJobTransition(ValueError)` (`transcription_job.py:89`) y el resto son `TypeError`/`ValueError` con mensaje libre, sin código estable. `AGENTS.md` pide códigos estables; (hipótesis) el mapeo a códigos ocurre en `interfaces`. Por verificar.
- Razonamiento estático (no ejecutado): `can_transition_to` hace `target in frozenset(...)` sin validar antes (`transcription_job.py:212-215`, `synthesis_job.py:145-148`). Un `target` no hashable (p. ej. una lista) lanzaría `TypeError` de Python en vez del error de dominio. Impacto bajo.

#### 5. Seguridad y privacidad

- Buena práctica comprobada: `SynthesizedAudio` rechaza rutas absolutas, unidades (`:`), separadores `\` y segmentos `..` o vacíos (`src/voz/domain/entities/synthesized_audio.py:19-25`). `MediaAsset` documenta que las rutas de almacenamiento pertenecen a infraestructura (`media_asset.py` docstring, líneas 22-26).
- Riesgo ligado a DOMAIN-03: `MediaAsset.display_name` no aplica la regla de caracteres de control y bidi (`media_asset.py:55-56`). La protección vive en `src/voz/interfaces/api/media.py:142` y `src/voz/infrastructure/media_storage.py:254`.
- `Segment.original_text`, `quality_flags` y el texto literal son contenido de audio del responsable. El dominio no imprime ni registra nada (sin imports de `logging`); no se encontraron secretos en `src/voz/domain/`.
- `MediaAsset.content_sha256` identifica el contenido original (`media_asset.py:17`). (hipótesis) No es secreto, pero permite reconocer un archivo conocido. Bajo.

#### 6. Pruebas y evidencias

- Existen 16 archivos en `tests/unit/domain/` con 139 funciones `def test_` (conteo estático; no ejecutado). Cubren por archivo: `transcription_job` 26, `synthesis_job` 13, `segment` 17, `media_asset` 11, `synthesis_request` 11, `speaker` 10.
- Huecos observados por lectura (no exhaustivos; grep):
  - El test de reapertura solo parte de `COMPLETED` (`tests/unit/domain/test_transcription_job.py:430-450`). No hay prueba de reapertura desde `FAILED` ni `CANCELLED`, aunque el dominio lo permite (`transcription_job.py:321-322`).
  - No encontré pruebas que fijen la coherencia entre `edited`, `revision` y `original_text` en `Segment` (`segment.py:42-44`).
  - No encontré prueba de `display_name` con caracteres bidi o de formato (Cf) en `MediaAsset`.
- Nada de lo anterior se ejecutó; la existencia de un test no implica que pase.

#### 7. Preparación para STT en tiempo real

**Impedimentos comprobados**

- `TranscriptionJob` exige `media_asset_id` (`transcription_job.py:129`) y `Transcript` también (`transcript.py:21`). Una sesión en vivo no tiene archivo original; (hipótesis) habría que relajar o sustituir ese vínculo.
- `Segment` exige texto no vacío (`segment.py:24-28`) y `end_ms > start_ms` (`segment.py:15-20`). Una hipótesis parcial puede tener texto vacío y finales de tiempo inestables.
- La identidad de segmento es derivada del índice: `transcript_id = uuid5(job_id, "transcript")` (`src/voz/application/job_runner.py:130`) y `segment_id = uuid5(transcript_id, f"segment:{index}")` (`job_runner.py:715`). Si una corrección cambia el orden o el número de segmentos, las identidades cambian. Un flujo en vivo necesita identidad por secuencia de flujo.
- `ModelCapability.REALTIME` existe (`model_descriptor.py:35`) y no se usa. Vocabulario preparado, sin modelo de sesión.
- No hay concepto de parcial, final ni sesión en el dominio ni en `application/ports`.

**Cómo separar parcial, final y corrección (propuesta de diseño, no implementación)**

- Hipótesis parcial: valor inmutable, sin identidad persistente. Campos sugeridos: `stream_seq`, `revision`, `start_ms`/`end_ms` relativos al flujo y un `finality` de dos valores (parcial o final). Una hipótesis reemplaza a la anterior con el mismo `stream_seq` y mayor `revision`.
- Final: solo al cerrar un enunciado. Se promueve a `Segment` mediante un caso de uso de aplicación, con identidad derivada de `(session_id, stream_seq)` y no del índice.
- Corrección posterior a final: hoy existe `Segment.edit_text` (`segment.py:83-94`), que es una edición humana (`edited`, `revision`, `original_text`). Una corrección del ASR necesita un origen distinto. Hoy no hay campo de origen (`asr` frente a `user`); es decisión abierta (DOMAIN-04).
- Máquina de estados de sesión: basta una tabla pequeña de estados (`CREATED → LISTENING → DRAINING → CLOSED`, más `FAILED`), con el mismo patrón de transición que ya existe. No se recomienda un agregado DDD completo.

**Qué reutilizar y qué separar**

- Reutilizar: `Word` y la validación de offsets (si se extrae a un valor común), `ModelDescriptor.identity` como referencia de modelo, `Speaker` para diarización en vivo, `ModelCapability.REALTIME`, y el patrón de transición con tabla.
- Mantener separado: `Segment` como texto final persistido e inmutable salvo `edit_text`; `TranscriptionJob` (pipeline por lotes con etapas PROBING y PREPROCESSING que no aplican al vivo); `SynthesisJob`; y `TranscriptionSegment` del puerto, que es salida de proveedor (`src/voz/application/ports/transcription.py:123`).
- Se conservaría `SpeakerTurn` como intervalo de clúster batch; el flujo en vivo necesitaría su propio intervalo de hablante (hipótesis).

**Preguntas abiertas para la revisión central**

1. ¿Una sesión en vivo produce un `Transcript` propio o un flujo de hipótesis que se consolida al cerrar?
2. ¿`Segment` necesita campo de origen (`asr` frente a `user`)?
3. ¿La identidad por índice en lote se mantiene, o pasa a identidad por secuencia en ambos flujos?

#### 8. Top 5 hallazgos

| ID | Severidad | Hallazgo | Evidencia | Impacto | Recomendación |
|---|---|---|---|---|---|
| DOMAIN-01 | alta | El modelo no puede representar una sesión STT en vivo sin contaminar `Segment`, `Transcript` ni `TranscriptionJob`. No hay concepto de parcial ni de sesión, los vínculos exigen `media_asset_id` y la identidad es por índice. | `transcription_job.py:129`, `transcript.py:21`, `segment.py:15-28`, `job_runner.py:130`, `job_runner.py:715`, `model_descriptor.py:35` (REALTIME sin uso) | Cualquier parcial obliga a crear un tipo nuevo o a mezclar estados en la entidad persistida. | Decidir un modelo separado: valor de hipótesis con `stream_seq`/`revision`/`finality` y una tabla de estados de sesión pequeña; promoción a `Segment` solo con finales. |
| DOMAIN-02 | alta | Reglas de estado divergentes. `reopen_for_diarization` se salta la tabla de transiciones, acepta `FAILED` y `CANCELLED`, y baja el progreso de 1,0 a 0,8. `TranscriptionJob` permite `FAILED` sin `error_code`, mientras `SynthesisJob` lo exige. | `transcription_job.py:313-332`, `:321-322`, `:176-179`, `:252-254`; `synthesis_job.py:166-167`; `job_runner.py:87`; `rediarize.py:114-116`; `test_transcription_job.py:430-450` | Estados que la API o la UI pueden mostrar de forma ambigua; el progreso deja de ser monótono sin que la invariante lo diga. | Decidir si la reapertura es transición de la tabla, si el progreso puede bajar (y documentarlo) y si `FAILED` exige código en ambos procesos. Añadir pruebas de reapertura desde `FAILED`/`CANCELLED`. |
| DOMAIN-03 | media | La regla de nombres de archivo no se aplica en el dominio. `MediaAsset.display_name` omite `has_unsafe_filename_character`, aunque el módulo se declara "single source of truth". `require_non_blank` solo rechaza controles < 32. | `media_asset.py:55-56`, `filename_safety.py:1,13`, `_validation.py:25-26`; enforcement en `src/voz/interfaces/api/media.py:142`, `src/voz/infrastructure/media_storage.py:254`, `src/voz/interfaces/api/openai_compat.py:165` | (hipótesis, razonamiento estático no ejecutado) Un nombre con U+202E o U+200B pasaría la validación del entity; la protección depende de que cada adaptador la aplique. | Decidir si el dominio es dueño de la regla y, si sí, aplicarla en `MediaAsset` con prueba de regresión (ver sección 6). |
| DOMAIN-04 | media | `Segment` permite combinaciones incoherentes: `edited`, `revision` y `original_text` son independientes; `words` no se re-alinean tras `edit_text`; el esquema no lo restringe. | `segment.py:42-44`, `segment.py:83-94`, `schema.py:105-110`, `src/voz/application/edit_segment.py:40-42` | Trazabilidad del texto literal de ASR frágil; no hay campo para correcciones que no sean humanas. | Decidir las invariantes (`edited` ⇔ `revision > 0` ⇔ `original_text` definido), qué pasa con `words` tras editar y si existe un campo de origen. |
| DOMAIN-05 | media | El dominio se declara neutral pero modela conceptos de proveedor: vocabulario de CTranslate2, parámetros de Whisper y métricas de Whisper. `ModelCapability` mezcla hardware (`GPU`/`CPU`) con capacidades. Hay dos conceptos "profile". | `processing_profile.py:1,20-24`, `quality_profile.py:32,85-88`, `segment.py:47`, `model_descriptor.py:17-37`, `infrastructure/asr/catalog.py:19-20` | Cada proveedor nuevo obliga a tocar el dominio; se confunden perfiles de ejecución y de decodificación. | Decidir si la neutralidad es un requisito real. Si lo es, separar parámetros de proveedor en infraestructura y dejar en dominio solo intención (rendimiento y calidad) y capacidades. |

#### 9. No verificado

- No se ejecutó ningún test, linter, tipador ni build (regla del encargo). Los conteos son estáticos.
- Las afirmaciones sobre comportamiento de Python (`TypeError` por hash en `frozenset`, normalización de zona horaria) son razonamiento estático.
- No se auditaron en profundidad `application`, `infrastructure` ni `interfaces`; solo se citan usos para explicar dependencias.
- No se leyeron los ADR de `docs/adr/` (ADR-0010 se cita en el dominio); no se revisó `ROADMAP.md`.
- No se comprobó la historia de Git (`git log`/`blame`) de estas entidades.
- Si existen pruebas de integración que cubran los huecos de la sección 6 fuera de `tests/unit/domain/`, no se revisaron.
