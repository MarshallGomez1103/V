# 12 · Resumen ejecutivo

**Proyecto:** V · `https://github.com/<propietario>/V` · rama `main` · HEAD `96284c53bc628dac330b222c4fde78ff3db9e2c9` · auditoría estática del 2026-10-21.

Clasificación de las afirmaciones:
- **[O]**: observado en código.
- **[D]**: documentado, sin comprobar.
- **[I]**: inferido.
- **[H]**: hipótesis sin reproducir.

Cada punto remite al informe detallado (`01`–`08`, `09` matriz, `10` STT, `11` contradicciones).

## 1. Arquitectura encontrada
- **[O] Monolito modular hexagonal real, no solo declarado.**
  - `src/voz/domain` importa solo la biblioteca estándar (`01` §1).
  - `src/voz/application` no importa infraestructura, interfaces ni frameworks: 0 coincidencias de `voz.infrastructure`, `fastapi`, `sqlalchemy`, `numpy`, `sherpa`, `ctranslate2`… (`02` §1).
  - Los adaptadores implementan puertos `Protocol` y la composición está en `src/voz/bootstrap.py`.
- **[O] Persistencia:** SQLite (WAL, `synchronous=FULL`) con SQLAlchemy Core y Alembic, un repositorio por agregado (`05` §1).
- **[O] Ejecución:** dos runners en hilo (transcripción y síntesis) con un `ComputeSlot` FIFO compartido y una `AdmissionGate` (`05` §1, §4).
- **[O] Motores:**
  - STT: faster-whisper, whisper.cpp y sherpa-onnx en local; OpenAI, ElevenLabs y OpenAI-compatible en la nube.
  - Diarización: sherpa-onnx offline.
  - TTS: sherpa-onnx (Piper/Kitten/Kokoro, un proceso hijo por fragmento) y OpenAI-compatible (`03`, `04`).
- **[O] Interfaz:** FastAPI con `host_guard`, token opcional y SSE por sondeo. React 19 con Carbon (piel M3 opcional) e i18n en/es, en una SPA sin store global (`06`, `07`).

## 2. Fortalezas principales
- Reglas de dependencia hexagonales respetadas en dominio y aplicación [O].
- Cancelación cooperativa con token, protegida por lock frente a escrituras del worker. Pruebas de carreras con reloj inyectado, sin `sleep` (`05` §4, `08` §4) [O].
- Originales de medio inmutables (hard link de solo lectura), escrituras atómicas y `safe_fs` con `dir_fd` (`05` §5) [O].
- Descarga de modelos fijada por tamaño y SHA-256, extracción sin `extractall` y publicación atómica (`04` §1) [O].
- Claves con permisos 0600 y `repr` oculto. Consentimiento STT en la nube fallando cerrado de punta a punta (`04` §5) [O].
- Contratos reutilizables por puerto en las pruebas, y CI en tres sistemas operativos con arranque en frío de los lanzadores (`08` §2, §6b) [O].

## 3. Defectos demostrados (estáticamente)
- **Seguridad (alta):**
  - Al editar `base_url` sin reenviar la clave, la clave se envía al host nuevo (TTS_CLOUD-01).
  - Los endpoints de nube aceptan `http://` (TTS_CLOUD-02).
  - Los procesos hijos heredan el entorno completo con las claves y cargan pesos no confiables sin límites (TTS_CLOUD-03).
- **Consentimiento incompleto (media):** TTS en la nube sin consentimiento por trabajo en el servidor. Los trabajos en la nube se reanudan sin reconfirmar (APPLICATION-02 = TTS_CLOUD-04, TTS_CLOUD-05).
- **Invariantes:**
  - `reopen_for_diarization` salta la tabla de transiciones (DOMAIN-02).
  - CANCELLING no bloquea la admisión de otro trabajo sobre el mismo medio (persistence_jobs-02).
  - `display_name` sin la regla de caracteres seguros (DOMAIN-03).
- **Errores y UX:**
  - Fallos silenciados en el workspace (FRONTEND-03).
  - Textos fijos en español en una UI en inglés (FRONTEND-05).
  - FFmpeg ≠0 clasificado siempre como «medio corrupto» (SPEECH-03).

## 4. Riesgos de producción [H salvo que se indique]
- Dos workers y un engine liberado tras un `stop()` con timeout (persistence_jobs-04).
- Apagado bloqueable con SSE o descargas abiertas (INTERFACES-03).
- Procesos nietos huérfanos en POSIX (persistence_jobs-05; [O] `kill_tree` no mata el grupo).
- Memoria lineal con la duración en síntesis (persistence_jobs-03, [O] acumulación) y respuestas cloud leídas sin tope (`04` §4).
- Sin `pytest-timeout` y con pruebas de tiempo real de márgenes fijos (QUALITY-03).
- La CI no audita dependencias ni secretos (QUALITY-01 [O]). Además, en el repositorio público están desactivados secret scanning y Dependabot.
- Peticiones simples de origen cruzado alcanzan rutas con efectos cuando no hay token (INTERFACES-01).

## 5. Problemas de diseño
- **Duplicación estructural** entre `JobRunner` y `SynthesisRunner` (ciclo de vida, cola, `_save`) con divergencias reales (`05` §3). Dos transportes HTTP cloud con contratos distintos y tres validadores de rutas relativas (`04` §3). Catorce funciones de mensaje de error en el frontend (`07` §1).
- **Lógica de negocio en routers:** ETA, consentimiento, filtros y plazos (INTERFACES-02). La aplicación traduce a HTTP (APPLICATION-04).
- **Vocabulario de proveedor en el dominio.** `ModelCapability` mezcla hardware y capacidad (DOMAIN-05).
- **Snapshot de ejecución no vinculante** (APPLICATION-01).
- **Componentes con varias responsabilidades.** No se juzga solo por el tamaño: `ModelManager.tsx`, `SegmentList.tsx` y `Workspace.tsx` (`07` §1).
- **ADR-0005** tiene vencido su disparador de revisión (seis proveedores STT). La documentación de arquitectura está desactualizada (`11` §C).

## 6. Brechas de pruebas
- Sin prueba de:
  - cancelación entre escritura del WAV y COMPLETED;
  - CANCELLING seguido de crear;
  - edición aceptada de URL con clave;
  - rechazo de `http://`;
  - entorno de los hijos;
  - nietos en POSIX.
- `ResizeObserver` es un no-op en las pruebas: la virtualización no se ejerce (`07` §6). `App.e2e.test.tsx` corre en jsdom.
- Skips silenciosos (`tests/packaging/test_wheel_contents.py:24`). Sin cobertura medida y sin bloqueo de red en las pruebas (`08`).
- Las cifras de 3131/808 pruebas no son reproducibles en estático (`11` §A).

## 7. Dependencias e impedimentos para el STT en tiempo real (detalle en `10`)
- Puerto `TranscriptionProvider` por lotes (`BinaryIO` completo), sin contrato de streaming. ADR-0005 §7 ya exige un contrato aparte.
- Ningún motor con inferencia incremental cableada. whisper.cpp y sherpa cargan el modelo en cada llamada. La diarización es solo offline.
- Dominio sin sesión ni parcial/final. Identidad de segmento por índice; `TranscriptionJob` y `Transcript` atados a un `media_asset_id`.
- Sin captura de micrófono en la UI. Sin canal de subida incremental. uvicorn 0.52.4 sin librería WebSocket en `uv.lock`, de modo que adoptarla es una dependencia nueva.
- `ComputeSlot` FIFO sin prioridad: una sesión esperaría tras un trabajo largo. El runtime ASR se libera a los 60 s.
- La cola durable no sirve para sesiones en vivo: reencola al arrancar y usa chunks de 30 min.

## 8. Decisiones que necesitan aprobación del propietario
1. Transporte de audio en vivo: WebSocket (dependencia nueva), subida HTTP en streaming o segmentos cortos con `seq`.
2. Motor local de streaming y si corre en proceso o en un worker.
3. Política del `ComputeSlot` para sesiones en vivo (prioridad, slot propio o rechazo).
4. Persistencia de la sesión: efímera o `Transcript` al cerrar, y qué no se guarda nunca (audio y parciales por defecto).
5. Consentimiento cloud por sesión (revocable, con caducidad), por trabajo en TTS y al reanudar.
6. Si los endpoints de nube deben exigir `https`, y si cambiar de host borra la clave.
7. Si `Permissions-Policy: microphone=(self)` se mantiene antes de que exista el flujo de consentimiento.
8. Revisión de ADR-0005 antes de S17.01.

## 9. Referencias
- `01_INFORME_DOMAIN.md` · `02_INFORME_APPLICATION.md` · `03_INFORME_SPEECH.md` · `04_INFORME_TTS_CLOUD.md`
- `05_INFORME_PERSISTENCE_JOBS.md` · `06_INFORME_INTERFACES.md` · `07_INFORME_FRONTEND.md` · `08_INFORME_QUALITY.md`
- `09_MATRIZ_TRAZABILIDAD.md` (40 hallazgos) · `10_STT_REALTIME_READINESS.md` (16 dimensiones)
- `11_CONTRADICCIONES_Y_LIMITACIONES.md` (con la segunda lectura de los ADR) · `13_INVENTARIO_ARCHIVOS.md` (904 archivos)

## 10. Limitaciones
- Auditoría estática: nada ejecutado. Los comportamientos en tiempo de ejecución son hipótesis.
- 552 de 904 archivos se revisaron solo superficialmente y 79 se omitieron (estilos, catálogos, binarios); ver `11` §E.
- La revisión central validó automáticamente la existencia de las 1056 citas de los informes investigación y comprobó a mano 15 evidencias clave.
- Única excepción de red: lectura del estado de CI en GitHub. Algunas evidencias de `06` provienen de código de terceros instalado localmente.
- Los IDs `S17.01`–`S17.05` no se modificaron. No se redactó ningún ADR ni plan de implementación.
