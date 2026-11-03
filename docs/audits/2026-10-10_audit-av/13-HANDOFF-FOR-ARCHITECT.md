# 13 · Handoff para el arquitecto

Este documento permite entender VOZ sin conocer la conversación ni el histórico de sesiones. Las cifras son verificadas salvo que se indique. Los informes citados están en esta misma carpeta.

## 1. Estado real del proyecto

- **Qué es**: transcripción local de audio y video largos (clases, entrevistas, reuniones). Monolito modular FastAPI + SQLite + React. Datos en XDG, nada sale del equipo salvo que el usuario active un proveedor cloud.
- **Versión**: 0.1.0, sin release pública. Repositorio privado en GitHub.
- **Git**: `main` = `origin/main` = `1186908` (2026-10-03). 42 commits. Árbol limpio. 84 commits de un solo autor con correo `noreply`.
- **Calidad**: ruff, format, pyright estricto, eslint, tsc, vitest y build reproducible pasan. Pytest: 1612 pasados, 3 opt-in omitidos. Vitest: 543 pasados. CI de `main` verde en Linux, Windows y macOS.
- **Arquitectura**: 160 módulos, 0 violaciones de capa, 0 ciclos (`evidencia/import_graph.py`).
- **Usuario principal**: el propietario, en Bazzite con RTX 4060. Hay datos reales en `~/.local/share/voz/` (no tocados por esta auditoría).

Detalle: `01-EXECUTIVE-SUMMARY.md`, `02-REPOSITORY-INVENTORY.md`.

## 2. Qué funciona

Verificado en esta auditoría:
- Tests y checks de calidad (`10`).
- Arranque del servidor en loopback con XDG aislado; `GET /api/health` responde `ok`.
- Home renderiza en escritorio 1280 px y en teléfono 390 px (`evidencia/`).
- Build del frontend reproduce el bundle versionado byte a byte.
- Auditoría de secretos del historial completo: 0 HIGH.

Verificado en ROADMAP y HANDOFF (no re-ejecutado aquí, en hardware del propietario):
- ASR local faster-whisper `turbo` y `large-v3` en GPU, con RTF y WER medidos sobre audio sintético (BENCH-002).
- Diarización sherpa-onnx real (DIAR-SHERPA-002).
- Glosario y perfil `academic` con VAD en GPU (QUALITY-CORE-001/002).
- Importación desde la caché de Buzz por hardlink (MODELS-BUZZ-001).
- Cancelación, recuperación tras reinicio y checkpoints (ASR-RECOVERY-001).

## 3. Qué está roto o es frágil

Ningún P0. Los P1 están en `11-TECHNICAL-DEBT.md`:

| ID | Problema | Dónde |
|---|---|---|
| AV-P1-01 | Acceso directo de escritorio con rutas absolutas al checkout; no portable | `infrastructure/desktop_shortcut.py:126-137` |
| AV-P1-02 | API local sin validación de `Host` (riesgo de DNS rebinding); parcial | `bootstrap.py:238`; ADR-0006:81 |
| AV-P1-03 | Worker de jobs descarta excepciones sin log | `application/job_runner.py:312-324` |
| AV-P1-04 | HANDOFF, ROADMAP y CHANGELOG desfasados respecto al v3 | `.ai/HANDOFF.md`, `ROADMAP.md`, `CHANGELOG.md` |
| AV-P1-05 | Filas de segmento en blanco tras seek (según HANDOFF; no verificado aquí) | `components/SegmentList.tsx` |

## 4. Qué no se verificó

- Transcripción real con modelo descargado en esta sesión (no se descargaron modelos; se respetó la regla de no descargar).
- Benchmarks GPU propios (no se ejecutaron).
- Proveedores cloud contra servicio real (no se usó ninguna API de pago).
- Windows y macOS a mano (solo CI).
- Acceso directo: instalación desde la UI y eliminación.
- Wayland y KDE: no se probó la sesión gráfica del propietario.
- Auditoría de dependencias Python (`pip-audit` no instalado).
- Cobertura de tests: no hay herramienta configurada.
- Playback del audio y volumen 300 % en navegador.

## 5. Qué se añadió fuera del plan original

No aparecen en `VOZ_PLAN_MAESTRO.md` (búsqueda por palabra clave: Material 0, Carbon 0, biblioteca 0, icono/escritorio 0):

- Piel Material 3 seleccionable, y Carbon como sistema principal.
- Home con biblioteca, renombrar y eliminar proyectos.
- Rutas por hash con atrás/adelante.
- Recalcular hablantes sin re-transcribir.
- Acceso directo de escritorio creado desde Ajustes.
- Lanzadores de doble clic para Windows, macOS y Linux.
- Botón de apagado desde la UI.
- Volumen hasta 300 %, exportación con vista previa, progreso con ETA.
- PWA instalable (fase 0 de un plan Tauri que no está implementado).
- Glosario por proyecto, perfiles de calidad, cola de revisión, `voz bench` con WER/CER.

Detalle: `02-REPOSITORY-INVENTORY.md`.

## 6. Arquitectura que conviene conservar

- Puertos estructurales (`Protocol`) y suite de contrato común por proveedor (`tests/contract`).
- Un único composition root (`bootstrap.create_app`).
- Un único worker de jobs con checkpoints y `recover()` al arranque.
- Diarización en subproceso por el GIL (`infrastructure/diarization/worker.py`): **precedente para TTS**.
- Cancelación por token, consultada en varios puntos del ASR.
- Contrato de error `{"detail": {"code", "message"}}`.
- Originales inmutables; derivados en directorios separados.
- Cloud solo por selección explícita, sin fallback.

No recomiendo reescribir nada. Las mejoras son locales (`03`, `11`).

## 7. Qué cambiar para introducir TTS

Orden recomendado (detalle en `12-PROPOSED-ROADMAP.md`, sección 3):

1. Puerto `SpeechSynthesisProvider` en `application/ports/`, sin implementación.
2. Entidad de síntesis y almacenamiento de audio en XDG, con hash y metadatos; la API nunca devuelve rutas del host.
3. Registro de proveedores TTS igual que el de ASR.
4. Adaptador en subproceso con protocolo por pipes, como la diarización.
5. Entorno Python aislado para cada familia de proveedor.
6. Contrato común de pruebas con transporte falso.
7. UI: pantalla de síntesis, reproducción, consentimiento para voces clonadas.

No meter torch en el entorno principal: ADR-0007 lo evitó deliberadamente.

## 8. Opciones KittenTTS viables

Detalle en `07-KITTENTTS-RESEARCH.md`.

| Opción | Viable | Condición |
|---|---|---|
| KittenTTS 0.8 (nano int8 ~25 MB, micro 41 MB, mini 80 MB; ONNX; CPU) | **Sí, como primer adaptador** | En subproceso; fijar commit y hash de wheel (no hay releases); licencia de pesos a confirmar en la release |
| KittenTTS 2 (1,7 B, PyTorch según HF; 947 MiB o 506 MiB con `emb4`) | **Solo con condiciones** | Entorno aislado con torch; **licencia de pesos bloquea distribución** |
| KittenTTS 2 en edge o CPU ligera | No | Requiere GPU ~8 GB o CPU ~6 GB RAM según el README |

Cifras de rendimiento publicadas: solo A100. No hay cifras de CPU públicas. Medir en el hardware objetivo antes de comprometer nada.

## 9. Licencias que condicionan la integración

| Componente | Licencia | Condición |
|---|---|---|
| Código KittenTTS y `kittenml` | Apache-2.0 | Conservar avisos en `NOTICE` |
| Pesos KittenTTS 2 | Stellon Labs Community License | **Uso comercial gratuito solo hasta 1 000 000 USD de ingresos anuales o financiación acumulada**; por encima, licencia separada; redistribución con atribución; concesión revocable (según análisis secundario); texto completo no leído |
| Modelo de speaker-embedding de KittenTTS 2 | MIT | Permisiva |
| Pesos KittenTTS 0.8 | Metadato HF Apache-2.0; el README de GitHub no declara | Verificar en la release |
| `vibe` (referencia de app) | MIT | Se puede estudiar y adaptar con atribución |
| FFmpeg | Según la distribución | Ya gestionado con descarga fijada por SHA |
| sherpa-onnx, faster-whisper, whisper.cpp | No revisadas en esta auditoría (whisper.cpp: MIT según su README) | Revisar `NOTICE` y las licencias de cada dependencia antes de distribuir |

**Decisión del propietario**: no se puede incluir KittenTTS 2 en un instalador ni en un release público sin revisar el texto completo de la licencia y, si hay uso comercial, sin una licencia con Stellon Labs.

## 10. Riesgos del rename VOZ → AV

Detalle en `09-RENAME-MIGRATION.md`.

- Alcance: ≈2 859 líneas con "voz"; ≈1 400 con imports del paquete; 27 variables `VOZ_*`; rutas XDG; base de datos; formato JSON `voz.transcript`.
- Recomendación: estrategia **B** (marca y comando, con alias `voz`), sin mover datos ni cambiar formato.
- Riesgo de datos: `~/.local/share/voz/voz.sqlite3` y medios. Una migración de rutas sin prueba puede perderlos.
- Riesgo de nombre: "AV" es una sigla muy común. No verificado si hay conflicto de marca; requiere búsqueda propia.
- Dependencia: AV-P1-01 (el acceso directo ya usa rutas absolutas).

## 11. Tareas que deben preceder a la implementación

1. Actualizar HANDOFF, ROADMAP y CHANGELOG (AV-P1-04). Sin esto, cualquier agente parte de datos falsos.
2. Validación de `Host` (AV-P1-02) y log del worker (AV-P1-03). Son las dos correcciones que afectan a la base sobre la que se añade TTS.
3. Acceso directo portable (AV-P1-01).
4. Reproducir AV-P1-05 con una transcripción sintética.
5. Aislamiento XDG en tests (AV-P2-10): sin esto, los tests de TTS pueden escribir en los datos reales.
6. ADR de decisión sobre TTS (subproceso y entorno aislado) y ADR de rename (AV-D-01).
7. ADR sobre Tauri, o declararlo fuera de alcance (AV-P2-14).

## 12. Decisiones que necesitan aprobación del propietario

| # | Decisión | Por qué no la puede tomar un agente |
|---|---|---|
| D1 | ¿Se usará KittenTTS 2 y para qué (personal, investigación o comercial)? | Determina si la licencia de Stellon Labs aplica y si hace falta un contrato |
| D2 | ¿Se acepta la estrategia B de rename y el nombre "AV" después de una búsqueda de disponibilidad? | Marca y nombre público |
| D3 | ¿Se publica el repositorio y se hace una primera release? | S15.14 y S16.20 requieren autorización explícita (ROADMAP) |
| D4 | ¿Se acepta el coste de firma y notarización para macOS y Windows? | Requiere presupuesto |
| D5 | ¿Se aprueba un corte de seguridad para AV-P1-02 y AV-P2-01 (validación de `Host` y advertencia LAN)? | Cambia el comportamiento visible |
| D6 | ¿Se aprueba ejecutar benchmarks GPU y descargar modelos para medir TTS y STT? | La misión prohíbe descargas grandes y benchmarks GPU sin autorización; AGENTS.md exige no instalar modelos en bootstrap ordinario |
| D7 | ¿Se aprueba una prueba real de proveedores cloud con clave del propietario? | Implica gasto y envío de audio a un tercero |
| D8 | ¿Se aprueba cambiar la versión de `source-map-js` (AV-P2-08)? | Toca dependencias |

## 13. Referencias a los otros documentos

| Documento | Contenido |
|---|---|
| `01-EXECUTIVE-SUMMARY.md` | Estado general, fortalezas, prioridades |
| `02-REPOSITORY-INVENTORY.md` | Git, estructura, matriz de funcionalidades, lo añadido fuera del plan |
| `03-ARCHITECTURE-AUDIT.md` | Capas, concurrencia, errores, observabilidad, duplicación |
| `04-STT-AUDIT.md` | Pipeline STT, providers, modelos, GPU, cancelación, recuperación |
| `05-UI-UX-AUDIT.md` | Pantallas, accesibilidad, responsividad, rendimiento, capturas |
| `06-LINUX-PACKAGING-AUDIT.md` | Lanzadores, acceso directo, instalación, XDG |
| `07-KITTENTTS-RESEARCH.md` | KittenTTS 0.8 y 2, licencias, opciones de aislamiento, adaptador |
| `08-TINYML-EDGE-FEASIBILITY.md` | Clases de hardware, tecnologías, benchmarks propuestos |
| `09-RENAME-MIGRATION.md` | Inventario de "voz", estrategias A/B/C, recomendación |
| `10-TESTS-QUALITY-SECURITY.md` | Comandos, resultados, CI, seguridad, dependencias |
| `11-TECHNICAL-DEBT.md` | Registro de deuda con IDs, severidad, evidencia y pruebas de aceptación |
| `12-PROPOSED-ROADMAP.md` | Roadmap preliminar con checkboxes |
| `evidencia/` | Logs de pytest y vitest, script de dependencias, capturas de la Home |

## Nota final de método

- Todo lo marcado como "verificado" se reprodujo con un comando o se leyó en el código con número de línea.
- Las fuentes externas (KittenTTS, whisper.cpp, microWakeWord, vibe) se consultaron el 2026-10-10. Las cifras que no vienen de fuente primaria están marcadas como secundarias.
- No se modificó ningún archivo del repositorio. Los informes están en `.ai/audit-av/`, ignorado por Git.
