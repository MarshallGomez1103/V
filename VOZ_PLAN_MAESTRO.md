# VOZ — Plan maestro de arquitectura y desarrollo

> Aplicación local-first para transcripción de archivos de audio/video con múltiples motores ASR, diarización de hablantes, edición sincronizada con waveform y exportación. Diseñada para ejecutarse localmente mediante el comando `voz`.

## 0. Visión del producto

VOZ debe sentirse como una mezcla entre la experiencia de edición de ElevenLabs Speech-to-Text y la flexibilidad local de Buzz:

- El usuario ejecuta `voz`.
- VOZ levanta un servidor local en `127.0.0.1`.
- Se abre automáticamente el navegador.
- El usuario arrastra un archivo de audio o video.
- VOZ inspecciona el archivo, conserva el original y crea una versión normalizada para inferencia.
- El usuario elige un motor/modelo o usa el modo `Auto`.
- La transcripción se procesa localmente por defecto.
- Opcionalmente puede utilizar proveedores cloud configurados por API key.
- La interfaz muestra waveform, segmentos, timestamps, hablantes y progreso.
- El usuario puede renombrar hablantes, corregir texto, buscar, reproducir desde un segmento y exportar.
- Los modelos locales se descargan, verifican, administran y eliminan desde una pantalla propia.
- El proyecto se distribuye como software open source y no requiere un servidor remoto.

### Principios de producto

1. **Local-first y privacy-first.**
2. **Offline real** después de descargar los modelos elegidos.
3. **Proveedor intercambiable:** la aplicación no depende de Whisper, OpenAI, ElevenLabs o pyannote.
4. **Procesamiento reproducible:** cada transcripción registra modelo, versión, parámetros y pipeline.
5. **No bloquear la UI:** toda transcripción es un Job.
6. **Original inmutable:** nunca modificar el archivo cargado.
7. **Arquitectura extensible sin microservicios prematuros.**
8. **Una instalación sencilla y una CLI memorable:** `voz`.

---

# 1. Decisión arquitectónica principal

## 1.1 Estilo recomendado

**Monolito modular local + Clean/Hexagonal Architecture + pipeline asíncrono de jobs.**

No recomiendo microservicios para la primera versión. El sistema corre para un usuario en una máquina y comparte GPU, filesystem y base de datos local. Separarlo prematuramente en servicios aumenta instalación, puertos, serialización, observabilidad y fallos sin aportar valor inmediato.

La frontera importante no debe ser “servicio A vs servicio B”, sino **dominio/aplicación vs infraestructura**.

## 1.2 Capas

```text
┌──────────────────────────────────────────────────────────────┐
│                        Web UI (React)                        │
│ waveform · editor · speakers · models · jobs · settings     │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP + SSE/WebSocket
┌──────────────────────────────▼───────────────────────────────┐
│                      API / Adapters IN                       │
│ FastAPI · CLI Typer · schemas · auth-local                  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Application / Use Cases                   │
│ ImportMedia · CreateJob · Transcribe · Diarize · Align      │
│ RenameSpeaker · EditTranscript · Export · ManageModels      │
└──────────────────────────────┬───────────────────────────────┘
                               │ ports
┌──────────────────────────────▼───────────────────────────────┐
│                         Domain                               │
│ Project · MediaAsset · Transcript · Segment · Word          │
│ Speaker · ModelDescriptor · Job · ProcessingProfile         │
└──────────────────────────────┬───────────────────────────────┘
                               │ ports
┌──────────────────────────────▼───────────────────────────────┐
│                     Adapters OUT / Infra                     │
│ FasterWhisper · whisper.cpp · OpenAI · ElevenLabs           │
│ pyannote · FFmpeg · SQLite · filesystem · model registry    │
└──────────────────────────────────────────────────────────────┘
```

## 1.3 Patrones

- **Strategy:** cada motor de transcripción implementa el mismo `TranscriptionProvider`.
- **Adapter:** Faster Whisper, whisper.cpp, OpenAI y ElevenLabs se adaptan al modelo interno.
- **Factory/Registry:** descubrimiento y creación de proveedores/modelos.
- **Repository:** persistencia de proyectos, jobs, segmentos y configuración.
- **Command:** operaciones largas o mutables (`TranscribeMedia`, `ExportTranscript`).
- **Observer / pub-sub interno:** eventos de progreso hacia UI.
- **State:** ciclo de vida del Job.
- **Facade:** `TranscriptionPipeline` coordina ingestión, VAD, ASR, diarización, alignment y merge.
- **Dependency Injection:** infraestructura conectada a puertos en composition root.

Evitar CQRS completo y Event Sourcing en v1. Separar comandos/consultas a nivel de casos de uso es suficiente.

---

# 2. Stack técnico recomendado

## Backend

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2 + Alembic
- SQLite en WAL mode
- Typer para CLI
- `uv` para dependencias y empaquetado
- FFmpeg + ffprobe para ingestión
- asyncio para coordinación
- `concurrent.futures` / procesos dedicados para cargas pesadas
- SSE para progreso de jobs; WebSocket solamente donde realmente haga falta bidireccionalidad

## Frontend

- React + TypeScript
- Vite
- TanStack Query
- Zustand o estado local acotado
- WaveSurfer.js para waveform/playback/regions
- virtualización de listas para transcripciones largas
- componentes accesibles; no acoplar lógica de transcripción a la UI

## Persistencia

```text
~/.local/share/voz/
├── voz.db
├── projects/
│   └── <project-id>/
│       ├── original/
│       ├── normalized/
│       ├── chunks/
│       ├── exports/
│       └── artifacts/
└── models/

~/.cache/voz/
├── waveforms/
├── temp/
└── downloads/

~/.config/voz/
└── config.toml
```

Respetar XDG Base Directory en Linux.

---

# 3. Pipeline de audio

```text
Import
  ↓
ffprobe
  ↓
Validación + metadata
  ↓
Conservar original
  ↓
FFmpeg normalize/decode
  ↓
VAD opcional
  ↓
Chunk planner
  ↓
ASR
  ↓
Word alignment (si aplica)
  ↓
Speaker diarization (si aplica)
  ↓
Reconciliación speaker ↔ word/segment
  ↓
Merge global
  ↓
Post-processing no destructivo
  ↓
Persistencia
  ↓
Waveform + editor
  ↓
Export
```

## Compatibilidad de formatos

No diseñar la app alrededor de una lista cerrada de extensiones. La frontera de entrada debe ser **“archivo que FFmpeg puede decodificar”**.

La UI puede anunciar formatos comunes:

`mp3, wav, flac, m4a, aac, ogg, opus, webm, mp4, mov, mkv, avi, mpeg...`

El backend debe ejecutar `ffprobe` y decidir por codec/stream real.

### Normalización

Para ASR local:

```text
PCM float/16-bit
mono
16 kHz
```

pero **conservar siempre el original** para reproducción/exportación y para evitar pérdida acumulativa.

---

# 4. Motores de transcripción

## 4.1 Faster Whisper — proveedor local principal

**Rol:** opción predeterminada para equipos NVIDIA con VRAM suficiente.

Perfiles iniciales:

- `fast`: `turbo`, compute `float16` o `int8_float16`
- `balanced`: `large-v3-turbo`
- `quality`: `large-v3`
- `low-memory`: `medium` / `small`
- `cpu`: `small` o `medium`, `int8`

No fijar estos parámetros en la UI: deben venir de un `ModelDescriptor`.

## 4.2 whisper.cpp — fallback universal

Útil para:

- CPU
- Vulkan
- hardware sin CUDA apropiado
- modelos GGML/GGUF cuantizados
- instalación ligera

Debe ser un adaptador independiente; VOZ no debería conocer flags internos del ejecutable fuera del adapter.

## 4.3 WhisperX — capability opcional, no núcleo obligatorio

Puede aprovecharse para:

- timestamps a nivel de palabra
- forced alignment
- diarización integrada con pyannote
- batch ASR

Recomendación: no “casarse” con WhisperX como arquitectura. Extraer sus capacidades mediante adapters (`AlignmentProvider`, `DiarizationProvider`) para poder sustituirlas.

## 4.4 OpenAI — proveedor cloud opcional

Crear dos adapters:

- `OpenAITranscriptionProvider`
- `OpenAIDiarizedTranscriptionProvider`

No mezclar API keys ni facturación con Codex/ChatGPT. El usuario introduce `OPENAI_API_KEY`.

El adapter debe ocultar:
- límite de subida
- chunking
- retries
- rate limits
- response formats
- reconstrucción de offsets globales

## 4.5 ElevenLabs Scribe — proveedor cloud opcional

Implementar después del MVP local.

Ventaja: excelente experiencia de referencia para:
- speaker diarization
- word timestamps
- keyterms
- archivos largos
- muchos formatos

Nunca hacerlo dependencia obligatoria.

---

# 5. Diarización de speakers

Proveedor local recomendado:

`Pyannote Community-1`

Contrato propuesto:

```python
class DiarizationProvider(Protocol):
    def diarize(
        self,
        audio: AudioAsset,
        *,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult: ...
```

Separar:

- `SpeakerCluster`: identidad acústica provisional.
- `Speaker`: identidad editable en el proyecto.
- `SpeakerAssignment`: vínculo temporal.

Así `SPEAKER_00` puede renombrarse a `Profesor` sin reejecutar el modelo.

### Funciones de UX

- renombrar speaker
- fusionar speakers
- dividir asignación incorrecta
- reasignar segmento
- color persistente por speaker
- filtro “solo este speaker”
- speaker de referencia opcional en providers que lo permitan

---

# 6. Modelo de dominio

Entidades principales:

```text
Project
MediaAsset
TranscriptionJob
Transcript
Segment
Word
Speaker
SpeakerTurn
ModelDescriptor
ProcessingProfile
ExportArtifact
```

## Segment

```text
id
transcript_id
speaker_id?
start_ms
end_ms
text
confidence?
language?
source_provider
source_segment_index
edited
created_at
updated_at
```

## Word

```text
id
segment_id
start_ms
end_ms
text
confidence?
speaker_id?
```

## Job state machine

```text
QUEUED
  ↓
PROBING
  ↓
PREPROCESSING
  ↓
TRANSCRIBING
  ↓
ALIGNING
  ↓
DIARIZING
  ↓
MERGING
  ↓
PERSISTING
  ↓
COMPLETED

cualquier estado → FAILED
cualquier estado procesable → CANCELLING → CANCELLED
```

La UI nunca debe inferir el estado a partir de logs.

---

# 7. API interna

Ejemplos:

```text
POST   /api/projects
POST   /api/projects/{id}/media
GET    /api/projects/{id}
POST   /api/media/{id}/transcriptions
GET    /api/jobs/{id}
GET    /api/jobs/{id}/events
POST   /api/jobs/{id}/cancel

GET    /api/transcripts/{id}
PATCH  /api/segments/{id}
PATCH  /api/speakers/{id}
POST   /api/speakers/merge

GET    /api/models
POST   /api/models/download
DELETE /api/models/{id}
GET    /api/providers

POST   /api/transcripts/{id}/exports
```

No devolver rutas absolutas del sistema al navegador.

---

# 8. CLI `voz`

Objetivo:

```bash
voz
```

Comportamiento:

1. comprobar configuración
2. comprobar si ya existe una instancia
3. elegir puerto libre, por defecto `8765`
4. levantar API
5. servir frontend estático
6. abrir `http://127.0.0.1:8765`
7. mostrar logs mínimos
8. Ctrl+C apaga limpiamente

Otros comandos:

```bash
voz
voz --no-browser
voz --port 9000
voz doctor
voz models list
voz models pull <model>
voz models remove <model>
voz transcribe archivo.m4a --profile quality
voz config show
voz version
```

`voz doctor` debe comprobar:

- FFmpeg/ffprobe
- GPU NVIDIA visible
- CUDA/cuDNN compatibles
- PyTorch/CTranslate2
- almacenamiento libre
- permisos de directorios
- disponibilidad de modelos
- puertos
- API keys opcionales

---

# 9. Modelo manager

No guardar modelos dentro del repositorio.

Cada entrada:

```text
provider
family
model_id
display_name
version/revision
source
size_bytes
sha256?
license
capabilities
requirements
installed_path
installed_at
```

Capacidades:

```text
transcription
translation
word_timestamps
diarization
language_detection
realtime
gpu
cpu
```

UX:

- catálogo
- tamaño antes de descargar
- progreso
- pausa/cancelación si el backend lo permite
- checksum
- eliminar
- indicador “recomendado para tu equipo”
- benchmark local opcional

---

# 10. Estrategia para el hardware objetivo

Equipo observado:

- Intel Core i7-13650HX
- NVIDIA GeForce RTX 4060 Laptop
- 64 GB RAM aprox.
- Bazzite/Fedora Atomic
- KDE Plasma / Wayland

Recomendación:

1. **Faster Whisper + CUDA** como primera ruta.
2. `large-v3` / `turbo` como modelos iniciales a probar.
3. Pyannote en GPU cuando no compita simultáneamente con ASR.
4. Pipeline secuencial por defecto para no agotar VRAM:
   ASR → liberar modelo → diarización → merge.
5. Añadir un `ResourceGovernor` que conozca VRAM/RAM.
6. Mantener whisper.cpp como fallback.

No ejecutar ASR y diarización pesados simultáneamente hasta medir VRAM.

---

# 11. Bazzite/Fedora Atomic

Bazzite es image-based; evitar ensuciar el host.

Estrategia de desarrollo:

- CLI y herramientas livianas: Homebrew/`uv` en usuario.
- desarrollo reproducible: Distrobox o devcontainer.
- servicios persistentes: Podman/Quadlet solo más adelante.
- no usar `rpm-ostree` salvo necesidad real del sistema.
- datos/modelos siempre en HOME, no dentro del contenedor.

Para la primera distribución:

1. `uv tool install voz-transcriber` para CLI Python.
2. bundle del frontend dentro del paquete.
3. detectar FFmpeg o proveer instrucciones.
4. más adelante AppImage/Flatpak si la experiencia lo justifica.

Docker **no debe ser requisito** para ejecutar VOZ en una estación con GPU; puede ser una opción de desarrollo/CI.

---

# 12. Integración con Buzz

## Recomendación

**No hacer de Buzz una dependencia de ejecución.**

Buzz ya resuelve muchos problemas y es una referencia excelente, pero acoplar VOZ al GUI/proceso de Buzz haría que:
- dos aplicaciones administren modelos/configuración;
- el contrato dependa de internals ajenos;
- se complique la evolución;
- el error handling sea opaco.

### Qué sí reutilizar

1. estudiar su selección de backends;
2. replicar la idea de model cache;
3. reutilizar librerías que Buzz usa directamente;
4. si se copia/adapta código MIT, conservar avisos de licencia;
5. crear importador opcional del cache de Buzz:
   - detectar `~/.cache/Buzz`
   - mostrar modelos compatibles encontrados
   - enlazar/copy-on-demand, no moverlos

Esto permite que un usuario de Buzz no tenga que descargar dos veces algunos modelos.

---

# 13. UI objetivo

## Pantalla Home

- “Nuevo proyecto”
- drag & drop
- proyectos recientes
- estado de modelos

## Pantalla Transcription Workspace

```text
┌──────────────────────────────────────────────────────────┐
│ archivo · modelo · idioma · speakers · export · settings │
├──────────────────────────────────────────────────────────┤
│ Profesor  00:02:13.420                                   │
│ texto editable...                                        │
│                                                          │
│ Alumno    00:02:17.920                                   │
│ texto editable...                                        │
├──────────────────────────────────────────────────────────┤
│ waveform + playhead + regions por speaker                │
├──────────────────────────────────────────────────────────┤
│ zoom ───────  1.0x  ▶  buscar  speaker filter            │
└──────────────────────────────────────────────────────────┘
```

Funciones MVP:
- waveform
- click timestamp → seek
- reproducción sincronizada
- edición de texto
- rename speaker
- zoom
- buscar
- exportar TXT/SRT/VTT/JSON

Después:
- alineación visual palabra a palabra
- keyboard shortcuts
- split/merge segment
- waveform regions editables
- historial de ediciones
- “find low confidence”
- glosario/keyterms por materia
- resumen opcional y notas, claramente separados del transcript literal

---

# 14. Transcripción de clases largas

Para una clase de ~1 h 49 min:

1. importar el archivo completo;
2. conservar original;
3. normalizar una sola vez;
4. usar VAD para detectar regiones de voz;
5. crear chunks con pequeño overlap;
6. procesar los chunks en orden;
7. almacenar resultados parciales para reanudar;
8. reconciliar offsets al timeline original;
9. diarizar sobre el audio normalizado;
10. asignar speakers;
11. persistir incrementalmente.

Requisito importante:

> Si VOZ se cierra al minuto 87, no debe perder los primeros 86 minutos.

Por eso cada Job debe tener checkpoints.

---

# 15. Manejo de errores

Errores tipados:

```text
UnsupportedMediaError
CorruptedMediaError
ModelNotInstalledError
ModelDownloadError
InsufficientDiskError
InsufficientMemoryError
GpuUnavailableError
ProviderAuthenticationError
ProviderRateLimitError
TranscriptionError
DiarizationError
AlignmentError
ExportError
```

Cada error lleva:
- código estable
- mensaje de usuario
- detalle técnico
- acción sugerida
- retryable: true/false

Nunca mostrar traceback crudo como UX normal.

---

# 16. Observabilidad local

Sin telemetría remota por defecto.

Logs:
```text
~/.local/state/voz/logs/voz.log
```

Campos:
- job_id
- project_id
- stage
- provider
- model
- elapsed_ms
- memory
- gpu_memory
- error_code

Métricas locales útiles:
- realtime factor
- duración del archivo
- tiempo por etapa
- peak VRAM
- peak RAM
- número de segmentos
- porcentaje de speech
- retries

Pantalla “Diagnostics” exportable para issues de GitHub, con secretos y rutas sensibles redactados.

---

# 17. Seguridad y privacidad

- Bind únicamente a `127.0.0.1` por defecto.
- No exponer LAN sin flag explícito.
- API keys en keyring del sistema cuando sea posible.
- Nunca guardar keys en SQLite o logs.
- `.env` solo para desarrollo y siempre gitignored.
- validar path traversal en uploads/exports.
- filenames no son IDs.
- límites configurables de tamaño.
- sanitizar nombres de exportación.
- CSP apropiada en frontend.
- dependabot/Renovate opcional.
- SBOM en releases más adelante.

---

# 18. Testing / TDD

## Unit tests

- domain entities
- chunk planner
- timestamp merge
- speaker reconciliation
- state machine
- provider selection
- model registry
- export formatting

## Integration tests

- FFmpeg probe + conversion
- SQLite repositories
- API endpoints
- Faster Whisper adapter con fixture corto
- whisper.cpp adapter
- fake cloud provider
- resume de jobs

## Contract tests

Todos los `TranscriptionProvider` deben pasar el mismo suite:

```text
transcribe_valid_audio
returns_monotonic_timestamps
does_not_emit_negative_offsets
supports_cancellation
maps_provider_errors
preserves_language_metadata
```

## E2E

Playwright:
- importar archivo
- esperar job
- reproducir segmento
- editar
- renombrar speaker
- exportar

## Fixtures

Mantener audios pequeños y con licencia compatible:
- silencio
- un speaker
- dos speakers
- overlap
- ruido
- español
- audio corrupto
- formatos distintos

No subir grabaciones privadas de clases al repo.

---

# 19. CI/CD

GitHub Actions:

```text
PR
 ├─ lint backend
 ├─ typecheck backend
 ├─ unit tests
 ├─ frontend lint
 ├─ frontend typecheck
 ├─ frontend tests
 ├─ build frontend
 └─ integration tests CPU

main/tag
 ├─ todo lo anterior
 ├─ package wheel
 ├─ package sdist
 ├─ build artifacts
 ├─ generate checksums
 └─ release
```

GPU tests:
- no bloquear PR normal;
- workflow manual/self-hosted opcional.

Herramientas:
- Ruff
- Pyright/Mypy
- pytest
- coverage
- ESLint
- TypeScript strict
- Vitest
- Playwright
- pre-commit

---

# 20. Documentación

```text
docs/
├── architecture/
│   ├── c4-context.md
│   ├── c4-container.md
│   ├── c4-components.md
│   └── deployment.md
├── adr/
│   ├── 0001-modular-monolith.md
│   ├── 0002-hexagonal-boundaries.md
│   ├── 0003-sqlite-filesystem.md
│   ├── 0004-ffmpeg-ingestion.md
│   ├── 0005-provider-plugin-model.md
│   └── 0006-local-first.md
├── development/
│   ├── setup-bazzite.md
│   ├── testing.md
│   └── debugging.md
└── user/
    ├── install.md
    ├── models.md
    └── troubleshooting.md
```

El README público debe explicar:
- problema
- demo
- características
- privacidad
- instalación
- `voz`
- modelos
- arquitectura
- contribución
- licencia

---

# 21. Estructura del repositorio

```text
voz/
├── apps/
│   ├── api/
│   └── web/
├── src/
│   └── voz/
│       ├── domain/
│       │   ├── entities/
│       │   ├── value_objects/
│       │   ├── services/
│       │   └── events/
│       ├── application/
│       │   ├── commands/
│       │   ├── queries/
│       │   ├── ports/
│       │   └── services/
│       ├── infrastructure/
│       │   ├── audio/
│       │   ├── persistence/
│       │   ├── models/
│       │   ├── providers/
│       │   │   ├── faster_whisper/
│       │   │   ├── whisper_cpp/
│       │   │   ├── openai/
│       │   │   └── elevenlabs/
│       │   ├── diarization/
│       │   └── observability/
│       ├── interfaces/
│       │   ├── api/
│       │   └── cli/
│       └── bootstrap.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── docs/
├── scripts/
├── .github/
│   └── workflows/
├── pyproject.toml
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── SECURITY.md
```

---

# 22. Contexto para agentes de IA

## Archivos públicos en el repo

### `AGENTS.md`

Solo reglas estables del proyecto:
- arquitectura
- comandos
- estilo
- definición de done
- límites de capas
- cómo probar
- qué NO hacer

Este archivo sí puede versionarse porque ayuda a cualquier colaborador/agente.

### `ROADMAP.md`

Checklist de producto compartido.

### ADRs

Decisiones arquitectónicas durables, no conversación de agentes.

## Contexto privado local

```text
.ai/
├── CONTEXT.md
├── SESSION.md
├── HANDOFF.md
├── DECISIONS_PENDING.md
├── AGENT_LOG.md
└── scratch/
```

Agregar a `.gitignore`:

```gitignore
.ai/
CLAUDE.local.md
AGENTS.local.md
.codex/
```

### Regla de handoff

Antes de cambiar de Claude ↔ Codex:

1. actualizar `.ai/HANDOFF.md`;
2. marcar checklist completado en `ROADMAP.md`;
3. listar archivos modificados;
4. listar tests ejecutados;
5. anotar fallos abiertos;
6. dejar exactamente el siguiente objetivo;
7. no pegar toda la conversación.

Formato de `HANDOFF.md`:

```markdown
# Handoff

## Estado
...

## Terminado
- ...

## Pendiente inmediato
- [ ] ...

## Archivos tocados
- ...

## Tests
- `uv run pytest ...`

## Riesgos / bugs
- ...

## No cambiar
- ...

## Próximo agente
Implementa únicamente ...
```

---

# 23. Reglas para Claude/Codex

Incluir en `AGENTS.md`:

```markdown
# Engineering rules

1. No modificar más de una vertical slice por tarea.
2. No agregar dependencias sin justificarla.
3. El dominio no importa FastAPI, SQLAlchemy, torch, OpenAI ni FFmpeg.
4. Todo proveedor externo implementa un port.
5. No poner lógica de negocio en routers.
6. No poner SQL en casos de uso.
7. No guardar archivos binarios/modelos en Git.
8. No romper el modo offline.
9. Cada bug corregido debe tener prueba de regresión.
10. Ejecutar tests relevantes antes de marcar una tarea.
11. Actualizar ROADMAP.md solo después de verificar.
12. Si una decisión cambia arquitectura, crear/modificar ADR.
13. No reescribir módulos completos si basta un cambio pequeño.
14. No usar APIs cloud salvo selección explícita del usuario.
15. No inventar compatibilidad: feature no probada = experimental.
```

---

# 24. Roadmap ejecutable

## Sección 1 — Bootstrap del repositorio

- [ ] Crear repo y licencia
- [ ] Crear `pyproject.toml` con `uv`
- [ ] Crear frontend React/TS/Vite
- [ ] Crear FastAPI mínimo
- [ ] Crear CLI Typer `voz`
- [ ] `voz` inicia servidor y abre navegador
- [ ] Configurar XDG paths
- [ ] Añadir Ruff + type checker + pytest
- [ ] Añadir ESLint + TS strict + Vitest
- [ ] Crear CI inicial
- [ ] Crear `AGENTS.md`
- [ ] Crear `.ai/` y reglas de `.gitignore`
- [ ] Crear ADR-0001 monolito modular
- [ ] Verificar instalación limpia en Bazzite

**Definition of Done:** clonar → instalar → ejecutar `voz` → ver UI local.

## Sección 2 — Dominio y persistencia

- [ ] Modelar Project
- [ ] Modelar MediaAsset
- [ ] Modelar Transcript/Segment/Word
- [ ] Modelar Speaker/SpeakerTurn
- [ ] Modelar Job state machine
- [ ] Definir ports de repositories
- [ ] Implementar SQLite
- [ ] Alembic migrations
- [ ] WAL mode
- [ ] Tests unitarios de dominio
- [ ] Tests integración SQLite

**DoD:** proyectos y jobs sobreviven reinicio.

## Sección 3 — Ingestión multimedia

- [ ] Implementar `MediaProbePort`
- [ ] Adapter ffprobe
- [ ] Import seguro
- [ ] Hash del original
- [ ] Metadata de codec/duración/channels
- [ ] Normalización FFmpeg
- [ ] Progress reporting
- [ ] Cancelación
- [ ] Fixtures MP3/WAV/M4A/OGG/OPUS/WebM
- [ ] Manejo de archivo corrupto
- [ ] Limpieza de temporales

**DoD:** VOZ ingiere formatos comunes y genera audio normalizado reproducible.

## Sección 4 — Primer ASR local

- [ ] Definir `TranscriptionProvider`
- [ ] Definir `ModelDescriptor`
- [ ] Crear provider registry
- [ ] Adapter Faster Whisper
- [ ] Descarga de modelo
- [ ] Perfil `fast`
- [ ] Perfil `quality`
- [ ] detección GPU/CPU
- [ ] progreso por chunks
- [ ] persistencia incremental
- [ ] cancelación
- [ ] resume/checkpoints
- [ ] contract tests

**DoD:** archivo largo puede transcribirse localmente y reanudarse.

## Sección 5 — Workspace UI

- [ ] Upload drag & drop
- [ ] pantalla de job
- [ ] progreso por etapa
- [ ] lista de segmentos
- [ ] reproductor
- [ ] waveform
- [ ] seek desde timestamp
- [ ] autoscroll con playback
- [ ] edición de segmento
- [ ] búsqueda
- [ ] zoom
- [ ] virtualización para transcript largo
- [ ] autosave

**DoD:** experiencia usable similar al flujo básico mostrado en ElevenLabs.

## Sección 6 — Diarización

- [ ] Definir `DiarizationProvider`
- [ ] Adapter pyannote Community-1
- [ ] descarga/configuración
- [ ] detectar N speakers
- [ ] permitir min/max/exact speakers
- [ ] reconciliar turns con segmentos
- [ ] colores de speakers
- [ ] rename speaker
- [ ] merge speakers
- [ ] reassign segment
- [ ] pruebas con 2+ speakers

**DoD:** “quién dijo qué” es editable sin retranscribir.

## Sección 7 — Word timestamps y alignment

- [ ] Definir `AlignmentProvider`
- [ ] evaluar adapter WhisperX
- [ ] word timestamps
- [ ] reconciliar palabra-speaker
- [ ] click palabra → seek
- [ ] resaltar palabra actual
- [ ] fallback si idioma no tiene aligner

**DoD:** sincronización palabra/audio estable donde haya soporte.

## Sección 8 — Model Manager

- [ ] catálogo
- [ ] installed/not installed
- [ ] descarga con progreso
- [ ] checksum/revision
- [ ] eliminar
- [ ] disk usage
- [ ] detectar cache Buzz
- [ ] import/reuse compatible
- [ ] recomendaciones según hardware
- [ ] `voz doctor`

**DoD:** modelos administrables sin tocar carpetas manualmente.

## Sección 9 — whisper.cpp

- [ ] Adapter whisper.cpp
- [ ] detección binario
- [ ] CUDA build/documentación
- [ ] Vulkan build/documentación
- [ ] modelos cuantizados
- [ ] contract tests
- [ ] fallback automático

**DoD:** segunda implementación local completa bajo el mismo contrato.

## Sección 10 — Exportación

- [ ] TXT
- [ ] Markdown
- [ ] SRT
- [ ] VTT
- [ ] JSON canónico VOZ
- [ ] transcript por speaker
- [ ] transcript con timestamps
- [ ] pruebas golden files

**DoD:** export estable y testeado.

## Sección 11 — OpenAI opcional

- [ ] configuración segura API key
- [ ] adapter file transcription
- [ ] adapter diarized transcription
- [ ] chunking por límites reales
- [ ] offset stitching
- [ ] retries/backoff
- [ ] estimación de coste antes de enviar
- [ ] indicador CLOUD visible
- [ ] contract tests con fake client
- [ ] documentación privacidad

**DoD:** proveedor cloud intercambiable y nunca activado implícitamente.

## Sección 12 — ElevenLabs opcional

- [ ] API key
- [ ] Scribe v2 adapter
- [ ] diarization mapping
- [ ] word timestamps mapping
- [ ] keyterms
- [ ] archivos largos
- [ ] coste estimado
- [ ] contract tests fake
- [ ] documentación

**DoD:** backend adicional sin cambios en dominio/UI central.

## Sección 13 — Calidad de transcripción

- [ ] glossary/keyterms por proyecto
- [ ] prompt académico
- [ ] VAD configurable
- [ ] suppress hallucinations heuristics
- [ ] low-confidence review
- [ ] comparación A/B de modelos
- [ ] benchmark dataset personal no versionado
- [ ] WER/CER tool opcional
- [ ] profile recomendado por idioma

**DoD:** el usuario puede medir cuál modelo realmente funciona mejor para sus clases.

## Sección 14 — Robustez

- [ ] crash recovery
- [ ] atomic writes
- [ ] disk-space guard
- [ ] VRAM guard
- [ ] job cancellation real
- [ ] corrupted download recovery
- [ ] migration backup
- [ ] diagnostic bundle
- [ ] fuzz tests de import metadata

**DoD:** cerrar/reabrir VOZ no destruye trabajo.

## Sección 15 — Packaging y release

- [ ] wheel
- [ ] `uv tool install`
- [ ] frontend bundle incluido
- [ ] release GitHub
- [ ] checksums
- [ ] changelog
- [ ] semantic versioning
- [ ] instalación Bazzite documentada
- [ ] Linux generic install
- [ ] evaluar AppImage
- [ ] evaluar Flatpak

**DoD:** tercero puede instalarlo siguiendo solo README.

## Sección 16 — Open source readiness

- [ ] README profesional
- [ ] CONTRIBUTING
- [ ] CODE_OF_CONDUCT
- [ ] SECURITY
- [ ] issue templates
- [ ] PR template
- [ ] arquitectura C4
- [ ] ADRs completos
- [ ] screenshots/demo
- [ ] licencia de fixtures
- [ ] NOTICE de código/dependencias reutilizadas

**DoD:** repo listo para contribuciones externas.

---

# 25. Orden recomendado para agentes

No entregar a un agente “construye VOZ”.

Entregar vertical slices:

### Prompt de arranque

```text
Lee AGENTS.md, ROADMAP.md y los ADR relevantes.
Lee .ai/HANDOFF.md si existe.
Trabaja únicamente el checkbox indicado.
Antes de modificar código:
1. identifica capas afectadas,
2. propone archivos,
3. ejecuta tests base.
Implementa la solución mínima.
Añade/actualiza pruebas.
Ejecuta formatter, lint, typecheck y tests relevantes.
Solo entonces marca el checkbox.
Actualiza .ai/HANDOFF.md con estado y siguiente paso.
No avances al siguiente checkbox.
```

Idealmente cada agente recibe entre 1 y 3 checkboxes estrechamente relacionados.

---

# 26. MVP real

El MVP termina al completar:

- Secciones 1–6
- Sección 10

Eso da:

- `voz`
- navegador local
- upload
- formatos comunes
- Faster Whisper
- modelo descargable
- transcripción larga
- waveform
- edición
- speakers
- export

Todo lo demás puede evolucionar después sin cambiar el núcleo.

---

# 27. Qué NO hacer en la primera versión

- No Kubernetes.
- No RabbitMQ.
- No Kafka.
- No microservicios.
- No Postgres.
- No Redis obligatorio.
- No Electron/Tauri antes de validar la web local.
- No autenticar usuario único en localhost.
- No meter modelos en Docker images.
- No acoplar el dominio a Buzz.
- No construir un framework de plugins dinámicos antes de tener 2 proveedores reales.
- No ejecutar un LLM para “corregir” el transcript de forma silenciosa.
- No reemplazar el transcript literal por un resumen.

---

# 28. Evolución futura

Después del MVP:

- live microphone transcription
- captura de audio del sistema
- PWA
- desktop wrapper Tauri
- notas enlazadas a timestamps
- bookmarks
- vocabulario por asignatura
- chapter detection
- search semántico local
- resumen local con Ollama/llama.cpp
- export a Obsidian/Markdown
- identificación persistente de profesores mediante voice embeddings, solo opt-in
- multichannel audio
- watch folder
- batch folder transcription
- REST API documentada
- plugin SDK

Mantener estas funciones fuera del core de ASR.

---

# 29. Criterios de aceptación de arquitectura

La arquitectura va bien si:

- cambiar Faster Whisper por whisper.cpp no toca dominio;
- añadir OpenAI no obliga a cambiar la UI de segmentos;
- renombrar speaker no reejecuta ASR;
- un archivo de dos horas puede recuperarse tras cierre;
- ejecutar sin Internet funciona con modelos ya descargados;
- tests de dominio no cargan torch;
- frontend no sabe dónde se guardan archivos;
- SQLite puede reemplazarse sin reescribir casos de uso;
- el comando `voz` sigue siendo el único punto de entrada necesario.

---

# 30. Primera tarea concreta

**Objetivo:** skeleton ejecutable, sin ASR todavía.

- [ ] Crear repo `voz`
- [ ] Crear `AGENTS.md`
- [ ] Crear `ROADMAP.md`
- [ ] Crear `.ai/HANDOFF.md`
- [ ] Crear backend FastAPI con `/api/health`
- [ ] Crear frontend React con una pantalla Home
- [ ] Crear CLI Typer
- [ ] `voz` levanta Uvicorn
- [ ] `voz` abre browser
- [ ] empaquetar frontend o servirlo en modo dev
- [ ] tests para `/api/health`
- [ ] CI
- [ ] documentar setup Bazzite

**No instalar Whisper todavía.**

Primero garantizar que la columna vertebral del producto funciona.
