# VOZ roadmap

Este archivo es la fuente pública de verdad sobre el avance del producto. El
plan de fondo y sus razones están en [VOZ_PLAN_MAESTRO.md](VOZ_PLAN_MAESTRO.md).
El estado privado y transitorio de una sesión pertenece en `.ai/HANDOFF.md`.

## Convenciones

- Cada logro tiene un ID estable `S<section>.<number>`. Un ID publicado nunca se
  renumera ni se reutiliza; los nuevos logros se agregan al final de su sección.
- `[ ]` significa pendiente, `[x]` significa verificado. Código escrito pero no
  comprobado continúa pendiente.
- Una asignación comprende de uno a tres IDs estrechamente relacionados. Una
  excepción de bootstrap debe quedar explícita en el tablero.
- Estados permitidos: `pendiente`, `en curso`, `bloqueado`, `verificado`.
- La columna **Último logro verificable** describe el último checkpoint pequeño
  que sobrevivirá aunque una sesión termine. No describe intenciones vagas.
- La arquitectura duradera se registra en ADRs; el tablero no sustituye los ADR.

## Regla de actualización atómica

Antes de editar, el agente añade o reclama una fila con IDs exactos y estado `en
curso`. Nadie trabaja simultáneamente los mismos IDs. Después de cada checkpoint
verificado, se deben cambiar **en la misma edición**: el checkbox correspondiente,
el estado de la asignación y el último logro verificable. Si las pruebas fallan o
no pueden ejecutarse, el checkbox queda abierto y la fila registra el fallo o
bloqueo. No se marcan rangos completos por inferencia ni se borran logros de
otros agentes. El coordinador libera o reasigna IDs abandonados de forma
explícita.

## Trabajo activo inicial

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| BOOT-INT-001 | S1.01, S1.02 | `root` | verificado | Repositorio `main` inicializado y licencia MIT presente. |
| BOOT-INT-002 | S1.16, S1.19 | `root` | verificado | CI reproduce los checks locales; `.ai/`, secretos, medios, modelos y artefactos están excluidos. |
| BOOT-BE-001 | S1.03, S1.10, S1.11 | `backend_cli` | verificado | `uv sync --locked`, Ruff y Pyright pasaron con el entorno declarado. |
| BOOT-BE-002 | S1.05, S1.12 | `backend_cli` | verificado | `/api/health` respondió por HTTP real y los 15 tests Python pasaron. |
| BOOT-BE-003 | S1.06-S1.08 | `backend_cli` | verificado | `voz` levantó Uvicorn en loopback, sirvió la UI y apagó limpio con Ctrl+C; navegador cubierto por tests. |
| BOOT-BE-004 | S1.09 | `backend_cli` | verificado | Las tres pruebas de rutas XDG pasaron. |
| BOOT-WEB-001 | S1.04 | `frontend_web` | verificado | React/Vite compiló y el bundle quedó incluido en el wheel Python. |
| BOOT-WEB-002 | S1.13, S1.14 | `frontend_web` | verificado | ESLint y TypeScript strict pasaron después de `npm ci`. |
| BOOT-WEB-003 | S1.15 | `frontend_web` | verificado | Vitest ejecutó las dos pruebas de Home y health sin fallos. |
| BOOT-DOC-001 | S1.17, S1.18 | `docs_governance` | verificado | Reglas y roadmap creados; estructura, IDs y Markdown comprobados. |
| BOOT-DOC-002 | S1.20, S1.21 | `docs_governance` | verificado | ADR-0001 y setup Bazzite creados; enlaces y estructura comprobados. |
| BOOT-DOC-003 | S16.01 | `docs_governance` | verificado | README creado sin afirmar ASR implementado; enlaces comprobados. |
| BOOT-VERIFY-001 | S1.22 | `root` | verificado | Checkout limpio en Bazzite: locks, checks, Home/API HTTP y apagado limpio verificados. |

Cuando un paquete termine, conserva su fila como historial breve hasta el
siguiente corte coordinado; después puede moverse a un changelog de trabajo sin
alterar los IDs.

## Trabajo activo — Sección 2

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| DOM-CORE-001 | S2.01-S2.03 | `domain_core` | verificado | Project, MediaAsset y Transcript: 39 pruebas focalizadas y checks estrictos pasan. |
| DOM-TIME-001 | S2.04, S2.05 | `timeline_models` | verificado | Segment y Word validan offsets/pertenencia; suite de dominio integrada pasa. |
| DOM-JOB-001 | S2.08-S2.10 | `job_state` | verificado | Pipeline, fallo y cancelación explícitos; suite de dominio integrada pasa. |
| DOM-SPEAKER-001 | S2.06, S2.07 | `timeline_models` | verificado | Speaker rename monotónico y SpeakerTurn acústico separado; 28 pruebas pasan. |
| PERSIST-PORT-001 | S2.11 | `domain_core` | verificado | Ocho Protocols no exponen SQL/Session; tests estructurales pasan. |
| PERSIST-REPO-001 | S2.12 | `domain_core` | en curso | Adapter SQLAlchemy Core para los ocho ports asignado. |
| PERSIST-MIG-001 | S2.13 | `timeline_models` | en curso | Migración Alembic inicial alineada a metadata asignada. |
| PERSIST-WAL-001 | S2.14 | `job_state` | en curso | Factory SQLite con WAL, claves foráneas y prueba file-backed asignada. |
| VERIFY-DOM-001 | S2.15 | `job_state` | verificado | 198 pruebas unitarias; arquitectura limpia, Ruff y Pyright pasan. |
| VERIFY-SQL-001 | S2.16, S2.17 | por asignar | pendiente | Espera adapter SQLite y migración. |

---

## Sección 1 — Bootstrap del repositorio

- [x] **S1.01** Inicializar el repositorio con la estructura base acordada.
- [x] **S1.02** Elegir y añadir una licencia válida.
- [x] **S1.03** Crear `pyproject.toml` administrado con `uv` y Python 3.12.
- [x] **S1.04** Crear el frontend React, TypeScript y Vite.
- [x] **S1.05** Exponer un FastAPI mínimo con `GET /api/health`.
- [x] **S1.06** Crear el punto de entrada Typer `voz`.
- [x] **S1.07** Hacer que `voz` inicie Uvicorn en loopback.
- [x] **S1.08** Hacer que `voz` abra el navegador, salvo `--no-browser`.
- [x] **S1.09** Definir rutas XDG para config, datos, cache y estado.
- [x] **S1.10** Configurar Ruff para lint y formato backend.
- [x] **S1.11** Configurar el type checker backend.
- [x] **S1.12** Configurar pytest y una prueba de `/api/health`.
- [x] **S1.13** Configurar ESLint para el frontend.
- [x] **S1.14** Activar TypeScript strict y su comando de comprobación.
- [x] **S1.15** Configurar Vitest y una prueba mínima de Home.
- [x] **S1.16** Crear CI inicial para checks backend y frontend.
- [x] **S1.17** Crear `AGENTS.md` con reglas estables y comandos.
- [x] **S1.18** Crear este roadmap con IDs y seguimiento atómico.
- [x] **S1.19** Crear `.ai/` local y asegurar sus exclusiones de Git.
- [x] **S1.20** Registrar ADR-0001 del monolito modular.
- [x] **S1.21** Documentar el setup de desarrollo en Bazzite.
- [x] **S1.22** Verificar instalación limpia, arranque de `voz` y Home local en Bazzite.

**Criterio de salida:** desde un checkout limpio se instala el proyecto, se
ejecuta `voz` y se ve la UI local. No instalar Whisper en esta sección.

## Sección 2 — Dominio y persistencia

- [x] **S2.01** Modelar `Project` con identidad e invariantes.
- [x] **S2.02** Modelar `MediaAsset` sin rutas expuestas a la UI.
- [x] **S2.03** Modelar `Transcript`.
- [x] **S2.04** Modelar `Segment` con offsets válidos.
- [x] **S2.05** Modelar `Word` con offsets válidos.
- [x] **S2.06** Modelar `Speaker` editable.
- [x] **S2.07** Modelar `SpeakerTurn` separado de identidad acústica.
- [x] **S2.08** Modelar la máquina de estados de `TranscriptionJob`.
- [x] **S2.09** Probar transiciones válidas de jobs.
- [x] **S2.10** Probar rechazo de transiciones inválidas.
- [x] **S2.11** Definir ports de repositories.
- [ ] **S2.12** Implementar repositories SQLite.
- [ ] **S2.13** Crear migración Alembic inicial.
- [ ] **S2.14** Activar SQLite WAL mediante el adapter.
- [x] **S2.15** Añadir pruebas unitarias de entidades e invariantes.
- [ ] **S2.16** Añadir pruebas de integración de repositories SQLite.
- [ ] **S2.17** Verificar recuperación de proyectos y jobs tras reinicio.

**Criterio de salida:** proyectos y jobs sobreviven un reinicio sin que el
dominio dependa de SQLite.

## Sección 3 — Ingestión multimedia

- [ ] **S3.01** Definir `MediaProbePort`.
- [ ] **S3.02** Implementar el adapter ffprobe.
- [ ] **S3.03** Validar por streams/codecs y no solo por extensión.
- [ ] **S3.04** Copiar el original de forma segura e inmutable.
- [ ] **S3.05** Calcular y persistir el hash del original.
- [ ] **S3.06** Extraer duración, codec, sample rate y channels.
- [ ] **S3.07** Normalizar a audio mono de 16 kHz para inferencia.
- [ ] **S3.08** Conservar reproducción/exportación desde el original.
- [ ] **S3.09** Reportar progreso de normalización.
- [ ] **S3.10** Cancelar la normalización sin dejar artefactos corruptos.
- [ ] **S3.11** Añadir fixture WAV con licencia compatible.
- [ ] **S3.12** Añadir fixtures MP3 y M4A con licencia compatible.
- [ ] **S3.13** Añadir fixtures OGG, OPUS y WebM con licencia compatible.
- [ ] **S3.14** Mapear archivo corrupto a error tipado.
- [ ] **S3.15** Limpiar temporales de éxito, fallo y cancelación.
- [ ] **S3.16** Probar import contra path traversal y nombres inseguros.

**Criterio de salida:** VOZ ingiere formatos comunes que FFmpeg puede decodificar
y genera audio normalizado reproducible sin modificar el original.

## Sección 4 — Primer ASR local

- [ ] **S4.01** Definir el port `TranscriptionProvider`.
- [ ] **S4.02** Definir `ModelDescriptor` y sus capacidades.
- [ ] **S4.03** Crear el provider registry sin imports en dominio.
- [ ] **S4.04** Implementar el adapter Faster Whisper.
- [ ] **S4.05** Implementar descarga explícita de un modelo local.
- [ ] **S4.06** Registrar revisión y procedencia del modelo.
- [ ] **S4.07** Implementar perfil `fast` por descriptor.
- [ ] **S4.08** Implementar perfil `quality` por descriptor.
- [ ] **S4.09** Detectar GPU y elegir fallback CPU explícito.
- [ ] **S4.10** Planificar chunks con offsets globales.
- [ ] **S4.11** Reportar progreso por chunk.
- [ ] **S4.12** Persistir un resultado parcial verificado.
- [ ] **S4.13** Cancelar ASR entre unidades recuperables.
- [ ] **S4.14** Reanudar desde checkpoints sin repetir chunks completos.
- [ ] **S4.15** Añadir contract test de audio válido.
- [ ] **S4.16** Añadir contract test de timestamps monótonos y no negativos.
- [ ] **S4.17** Añadir contract test de cancelación y errores mapeados.
- [ ] **S4.18** Preservar metadata de idioma en el resultado canónico.

**Criterio de salida:** un archivo largo puede transcribirse localmente y
reanudarse bajo el contrato común.

## Sección 5 — Workspace UI

- [ ] **S5.01** Crear Home con acción “Nuevo proyecto”.
- [ ] **S5.02** Implementar selección y drag-and-drop de archivo.
- [ ] **S5.03** Mostrar validación de upload y errores seguros.
- [ ] **S5.04** Crear pantalla de job.
- [ ] **S5.05** Mostrar estado explícito por etapa.
- [ ] **S5.06** Consumir progreso mediante SSE.
- [ ] **S5.07** Renderizar lista de segmentos.
- [ ] **S5.08** Añadir reproductor del original.
- [ ] **S5.09** Renderizar waveform.
- [ ] **S5.10** Hacer seek al seleccionar un timestamp.
- [ ] **S5.11** Sincronizar selección/autoscroll con playback.
- [ ] **S5.12** Editar y guardar texto de un segmento.
- [ ] **S5.13** Buscar texto en el transcript.
- [ ] **S5.14** Controlar zoom del waveform.
- [ ] **S5.15** Virtualizar transcripts largos.
- [ ] **S5.16** Añadir autosave con estado visible.
- [ ] **S5.17** Probar importación, reproducción y edición E2E.

**Criterio de salida:** el flujo básico de upload, progreso, reproducción y
edición es usable con una grabación larga.

## Sección 6 — Diarización

- [ ] **S6.01** Definir el port `DiarizationProvider`.
- [ ] **S6.02** Modelar clusters, speakers y assignments por separado.
- [ ] **S6.03** Implementar adapter pyannote Community-1.
- [ ] **S6.04** Implementar descarga/configuración explícita del modelo.
- [ ] **S6.05** Ejecutar detección automática del número de speakers.
- [ ] **S6.06** Permitir mínimo y máximo de speakers.
- [ ] **S6.07** Permitir número exacto de speakers.
- [ ] **S6.08** Reconciliar turns con segmentos ASR.
- [ ] **S6.09** Asignar colores persistentes por speaker.
- [ ] **S6.10** Renombrar speaker sin reejecutar modelos.
- [ ] **S6.11** Fusionar speakers sin reejecutar ASR.
- [ ] **S6.12** Reasignar un segmento manualmente.
- [ ] **S6.13** Probar diarización con dos speakers.
- [ ] **S6.14** Probar overlap y segmentos sin speaker.
- [ ] **S6.15** Verificar liberación secuencial de VRAM entre ASR y diarización.

**Criterio de salida:** “quién dijo qué” se puede revisar y corregir sin volver a
transcribir.

## Sección 7 — Word timestamps y alignment

- [ ] **S7.01** Definir el port `AlignmentProvider`.
- [ ] **S7.02** Evaluar WhisperX contra fixtures e idiomas objetivo.
- [ ] **S7.03** Documentar la decisión de adapter de alignment.
- [ ] **S7.04** Persistir timestamps a nivel de palabra.
- [ ] **S7.05** Reconciliar palabra con speaker.
- [ ] **S7.06** Hacer seek al seleccionar una palabra.
- [ ] **S7.07** Resaltar la palabra actual durante playback.
- [ ] **S7.08** Implementar fallback cuando no exista aligner del idioma.
- [ ] **S7.09** Probar monotonicidad y límites de word timestamps.

**Criterio de salida:** palabra y audio permanecen sincronizados donde haya
soporte, con degradación explícita donde no lo haya.

## Sección 8 — Model Manager

- [ ] **S8.01** Definir catálogo canónico de modelos.
- [ ] **S8.02** Mostrar estado installed/not installed.
- [ ] **S8.03** Mostrar tamaño antes de descargar.
- [ ] **S8.04** Descargar con progreso visible.
- [ ] **S8.05** Permitir cancelación segura de descarga.
- [ ] **S8.06** Verificar checksum o revisión disponible.
- [ ] **S8.07** Eliminar un modelo con confirmación.
- [ ] **S8.08** Mostrar uso de disco por modelo/proveedor.
- [ ] **S8.09** Detectar cache de Buzz sin modificarlo.
- [ ] **S8.10** Reutilizar/importar un modelo compatible sin mover el original.
- [ ] **S8.11** Recomendar perfiles según hardware detectado.
- [ ] **S8.12** Implementar `voz doctor` para FFmpeg y puertos.
- [ ] **S8.13** Extender `voz doctor` para GPU/CUDA y runtime ASR.
- [ ] **S8.14** Extender `voz doctor` para disco, modelos y API keys opcionales.
- [ ] **S8.15** Probar descarga incompleta y recuperación.

**Criterio de salida:** el usuario administra modelos sin tocar carpetas
manualmente.

## Sección 9 — whisper.cpp

- [ ] **S9.01** Implementar adapter whisper.cpp bajo el port común.
- [ ] **S9.02** Detectar y validar el binario.
- [ ] **S9.03** Documentar build/uso con CUDA.
- [ ] **S9.04** Documentar build/uso con Vulkan.
- [ ] **S9.05** Registrar modelos cuantizados compatibles.
- [ ] **S9.06** Mapear salida a segmentos canónicos.
- [ ] **S9.07** Mapear fallos/cancelación a errores comunes.
- [ ] **S9.08** Pasar la suite completa de contract tests.
- [ ] **S9.09** Implementar fallback automático solo cuando sea seguro y visible.
- [ ] **S9.10** Comparar rendimiento CPU/GPU con fixtures controlados.

**Criterio de salida:** existe una segunda implementación local completa bajo el
mismo contrato.

## Sección 10 — Exportación

- [ ] **S10.01** Definir el port/servicio de exportación.
- [ ] **S10.02** Exportar TXT literal.
- [ ] **S10.03** Exportar Markdown.
- [ ] **S10.04** Exportar SRT con timestamps válidos.
- [ ] **S10.05** Exportar VTT con timestamps válidos.
- [ ] **S10.06** Exportar JSON canónico versionado.
- [ ] **S10.07** Exportar agrupado por speaker.
- [ ] **S10.08** Exportar texto con timestamps opcionales.
- [ ] **S10.09** Sanitizar nombres y evitar path traversal.
- [ ] **S10.10** Añadir golden tests TXT/Markdown.
- [ ] **S10.11** Añadir golden tests SRT/VTT.
- [ ] **S10.12** Añadir golden tests JSON.
- [ ] **S10.13** Verificar round-trip del formato canónico cuando aplique.

**Criterio de salida:** exportaciones estables, seguras y reproducibles completan
el MVP junto con las Secciones 1–6.

## Sección 11 — OpenAI opcional

- [ ] **S11.01** Diseñar configuración de API key fuera de SQLite y logs.
- [ ] **S11.02** Implementar adapter de file transcription.
- [ ] **S11.03** Implementar adapter de diarized transcription.
- [ ] **S11.04** Detectar límites reales mediante configuración/versiones probadas.
- [ ] **S11.05** Dividir archivos cuando el provider lo exija.
- [ ] **S11.06** Reconstruir offsets globales sin solapamientos inválidos.
- [ ] **S11.07** Implementar retries/backoff solo para fallos recuperables.
- [ ] **S11.08** Estimar coste antes de enviar.
- [ ] **S11.09** Mostrar indicador `CLOUD` antes y durante el job.
- [ ] **S11.10** Añadir fake client sin llamadas facturables.
- [ ] **S11.11** Pasar contract tests con el fake client.
- [ ] **S11.12** Documentar privacidad y datos enviados.
- [ ] **S11.13** Verificar que el provider nunca se activa implícitamente.

**Criterio de salida:** OpenAI es intercambiable, explícito y opcional; offline
sigue siendo el modo predeterminado.

## Sección 12 — ElevenLabs opcional

- [ ] **S12.01** Diseñar configuración segura de API key.
- [ ] **S12.02** Implementar adapter Scribe.
- [ ] **S12.03** Mapear diarización al formato canónico.
- [ ] **S12.04** Mapear word timestamps al formato canónico.
- [ ] **S12.05** Implementar keyterms por proyecto sin contaminar dominio.
- [ ] **S12.06** Manejar archivos largos y progreso.
- [ ] **S12.07** Estimar coste antes de enviar.
- [ ] **S12.08** Añadir fake client sin llamadas facturables.
- [ ] **S12.09** Pasar contract tests con el fake client.
- [ ] **S12.10** Documentar privacidad y datos enviados.
- [ ] **S12.11** Verificar que UI/dominio central no cambian por este adapter.

**Criterio de salida:** ElevenLabs funciona como backend adicional sin convertirse
en dependencia del producto.

## Sección 13 — Calidad de transcripción

- [ ] **S13.01** Modelar glossary/keyterms por proyecto.
- [ ] **S13.02** Crear perfil académico explícito y reproducible.
- [ ] **S13.03** Hacer VAD configurable por perfil.
- [ ] **S13.04** Implementar heurísticas no destructivas contra alucinaciones.
- [ ] **S13.05** Señalar segmentos de baja confianza.
- [ ] **S13.06** Crear flujo de revisión de baja confianza.
- [ ] **S13.07** Ejecutar comparación A/B de modelos sobre el mismo fixture.
- [ ] **S13.08** Medir tiempo, realtime factor, RAM y VRAM.
- [ ] **S13.09** Mantener dataset personal fuera de Git.
- [ ] **S13.10** Añadir herramienta opcional de WER/CER.
- [ ] **S13.11** Recomendar perfil por idioma usando resultados medidos.
- [ ] **S13.12** Separar transcript literal de cualquier postprocesamiento.

**Criterio de salida:** el usuario puede medir qué configuración funciona mejor
con sus grabaciones sin presentar intuiciones como resultados.

## Sección 14 — Robustez

- [ ] **S14.01** Recuperar jobs interrumpidos al iniciar.
- [ ] **S14.02** Escribir checkpoints y metadatos críticos atómicamente.
- [ ] **S14.03** Comprobar espacio antes de import/normalización.
- [ ] **S14.04** Comprobar espacio antes de descargar modelos.
- [ ] **S14.05** Añadir guard de RAM.
- [ ] **S14.06** Añadir guard de VRAM.
- [ ] **S14.07** Liberar modelos entre ASR y diarización por defecto.
- [ ] **S14.08** Implementar cancelación real por cada etapa procesable.
- [ ] **S14.09** Recuperar descargas corruptas/incompletas.
- [ ] **S14.10** Crear backup antes de una migración destructiva.
- [ ] **S14.11** Generar bundle diagnóstico redactado.
- [ ] **S14.12** Añadir fuzz tests de metadata de importación.
- [ ] **S14.13** Probar cierre/reapertura durante un job largo.
- [ ] **S14.14** Probar idempotencia de resume.

**Criterio de salida:** cerrar o reabrir VOZ no destruye el trabajo confirmado y
los fallos dan acciones recuperables.

## Sección 15 — Packaging y release

- [ ] **S15.01** Construir wheel reproducible.
- [ ] **S15.02** Construir sdist reproducible.
- [ ] **S15.03** Verificar instalación con `uv tool install`.
- [ ] **S15.04** Incluir el bundle frontend en el paquete.
- [ ] **S15.05** Verificar ejecución sin checkout de desarrollo.
- [ ] **S15.06** Crear workflow de release privado/de prueba.
- [ ] **S15.07** Generar checksums de artefactos.
- [ ] **S15.08** Mantener changelog.
- [ ] **S15.09** Adoptar versionado semántico.
- [ ] **S15.10** Verificar instalación documentada en Bazzite.
- [ ] **S15.11** Documentar instalación Linux genérica.
- [ ] **S15.12** Evaluar AppImage con prototipo medido.
- [ ] **S15.13** Evaluar Flatpak con prototipo medido.
- [ ] **S15.14** Publicar una release solo con autorización explícita.

**Criterio de salida:** un tercero puede instalar un artefacto siguiendo solo el
README, sin depender del checkout.

## Sección 16 — Open source readiness

- [x] **S16.01** Crear README profesional y honesto sobre el estado actual.
- [ ] **S16.02** Añadir demo y capturas correspondientes a funciones reales.
- [ ] **S16.03** Crear `CONTRIBUTING.md`.
- [ ] **S16.04** Crear `CODE_OF_CONDUCT.md`.
- [ ] **S16.05** Crear `SECURITY.md` con canal de reporte.
- [ ] **S16.06** Crear issue template de bug.
- [ ] **S16.07** Crear issue template de feature.
- [ ] **S16.08** Crear PR template con checks relevantes.
- [ ] **S16.09** Documentar diagrama C4 de contexto.
- [ ] **S16.10** Documentar diagrama C4 de contenedores.
- [ ] **S16.11** Documentar diagrama C4 de componentes.
- [ ] **S16.12** Completar ADR de límites hexagonales.
- [ ] **S16.13** Completar ADR de SQLite/filesystem.
- [ ] **S16.14** Completar ADR de ingestión FFmpeg.
- [ ] **S16.15** Completar ADR de providers.
- [ ] **S16.16** Completar ADR local-first.
- [ ] **S16.17** Documentar licencias de todos los fixtures.
- [ ] **S16.18** Crear `NOTICE` para código/dependencias reutilizadas.
- [ ] **S16.19** Auditar secretos y archivos ignorados antes de abrir el repo.
- [ ] **S16.20** Hacer público el repositorio solo con autorización explícita.

**Criterio de salida:** el repositorio está listo para recibir contribuciones
externas, con evidencias reales y sin material privado.

---

## Hitos

- **Skeleton ejecutable:** Sección 1 completa.
- **MVP local:** Secciones 1–6 y 10 completas.
- **Providers extensibles demostrados:** Secciones 9, 11 o 12 según prioridad,
  manteniendo al menos dos implementations bajo contract tests.
- **Release instalable:** Sección 15 completa.
- **Apertura pública:** Sección 16 completa y autorización explícita del dueño.

Los hitos no sustituyen los checkboxes: se declaran alcanzados solo cuando todos
sus IDs obligatorios están verificados.
