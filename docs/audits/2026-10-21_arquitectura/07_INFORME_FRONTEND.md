### INFORME — frontend

**Metadatos:** fecha 2026-10-21 · HEAD 96284c5 · rutas revisadas: `apps/web/src/` (236 archivos, 35.349 líneas según files_frontend.tsv) · alcance: estático (sin build, sin tests, sin navegador, sin red) · límites: SCSS y catálogos i18n no abiertos uno a uno; tests solo contados por grep.
**Cobertura:** asignados 236 · superficial 141 · profunda 40 · omitidos 55 · ~5.800 líneas profundas (archivos completos) · dependencias principales: react 19.2.7, @carbon/react 1.117.0, @material/material-color-utilities 0.4.0, vite 8, vitest 4 + jsdom (`apps/web/package.json`). No hay dependencias de audio ni de captura.

#### 1. Responsabilidades y dependencias
- Organización: SPA sin store global, enrutado por hash (`apps/web/src/hooks/useRoute.ts:6-30`, `lib/navigation.ts`). `App.tsx` monta Inicio (`Library`), Nueva (`NewTranscription`, siempre montada y oculta, `App.tsx:186-199`), Trabajo (`Workspace` lazy, `key={route.jobId}`, `App.tsx:201-204`), Voz (síntesis), Modelos y Proveedores (estas dos se montan en la primera visita y luego quedan ocultas, `App.tsx:75-88`).
- Estado: por vista y por hook. Estado de servidor en `useLibrary`, `useJobEvents`, `useJobPreview`, `useModelTasks`, `useServerStatus`. Reproducción: `currentMs` en estado React (`Workspace.tsx:100`) más un store externo (`lib/playhead.ts:6-33`) que leen `WordText` y `SpeakerTimeline`. Borradores: `SegmentDraftStore` fuera de React (`hooks/useSegmentDrafts.ts:48`). Idioma y tema: stores externos con `useSyncExternalStore` (`i18n/i18n.ts:36-64`, `theme/appearance.ts:254`).
- Persistencia en localStorage: `voz.lang`, `voz.theme`, `voz.accent`, `voz.design`, `voz.speak.choice`. Sin secretos. Las claves de proveedor viven solo en estado (`ProvidersSettings.tsx:40`) y se borran tras guardar (`:51`).
- Componentes con demasiadas responsabilidades (líneas):
  - `ModelManager.tsx` 803: tabla, dos diálogos (`DownloadDialog` :152, `DeleteDialog` :218), polling vía `useModelTasks` (:628), avisos e instalación.
  - `SegmentList.tsx` 714: carga, virtualización propia, búsqueda, autoscroll, foco, filtro por hablante y estados de error (`TranscriptView` :265-600).
  - `SpeakersPanel.tsx` 509: CRUD de hablantes, fusión, recálculo y diálogo (`RecalcDialog` :453).
  - `CompatibleEndpoints.tsx` 466: lista, formulario y prueba de conexión (`EndpointForm` :52, `EndpointRow` :228); 18 `useState` en el componente exportado.
  - `Library.tsx` 462: tabla, búsqueda, renombrar y borrar.
  - `Workspace.tsx` 427: orquesta dos `useJobEvents`, `useJobPreview`, borradores, seek, playhead, hablantes, recálculo y layout de tres columnas (unas 25 llamadas de hooks).
  - `AddModelDialog.tsx` 353: 23 `useState`, subida, revisión, instalación y polling.
  - `JobScreen.tsx` 369: cálculo de etapas y tiempos, textos de error y acciones.
- Duplicación:
  - Medición de duración de grabación: `Workspace.tsx:110-126` y `NewTranscription.tsx:61-78` (mismo parche).
  - Seguimiento SSE con instantánea HTTP: `hooks/useJobEvents.ts:21-63` y `hooks/useSynthesisEvents.ts:26-77`. Solo el de síntesis tiene `retry` (`:29-31`).
  - Dos sondeos de tareas de modelo a la vez con el diálogo de alta abierto: `ModelManager.tsx:628` y `AddModelDialog.tsx:65`.
  - Dos comprobaciones de salud: `App.tsx:65` (`useServerStatus`, cada 5 s) y `components/HealthStatus.tsx:25-36`.
  - XHR de subida duplicado: `api/media.ts:51-119` y `api/customModels.ts:124-143`.
  - `isAbortError` reimplementado en `TranscriptionOptionsSelector.tsx:107-108`, `HealthStatus.tsx:33`, `SegmentList.tsx:640` y `api/synthesis.ts:240`, aunque `api/errors.ts:34` ya lo exporta.
  - Formato: `NewProjectCard.tsx:59` (`formatFileSize`) frente a `lib/formatBytes.ts:6`; `lib/waveformGeometry.ts:152` (`formatClock`) frente a `lib/formatTime.ts`.
  - Estados terminales: literal `['COMPLETED','FAILED','CANCELLED']` en `App.tsx:146`, frente a `PROCESSABLE_STATES` (`api/jobs.ts:21`).
  - Catorce funciones `messageOf/errorMessage/describeError/errorText` repartidas por componentes (p. ej. `SpeakersPanel.tsx:61`, `Library.tsx:55`, `ModelManager.tsx:101`, `ProvidersSettings.tsx:27`, `NewProjectCard.tsx:73`).
  - Comentario obsoleto: `api/jobs.ts:3` dice «duplicado con api/jobEvents.ts»; `jobEvents.ts` solo reexporta.
  - Prop sin llamador: `JobScreen.tsx:26,222` (`loading`). `Workspace.tsx:304-313` no la pasa, así que las ramas de `JobScreen.tsx:233` y `:237` no se alcanzan desde aquí.

#### 2. Arquitectura hexagonal
- Comprobado, correcto: el frontend solo consume HTTP (`apps/web/src/api/*`). No aparecen rutas de host en tipos ni en la UI; `api/desktopShortcut.ts:31` descarta `path` a propósito. No hay URL externas en el código (solo texto de ejemplo en `i18n/messages/endpoints.ts:22`). No hay `dangerouslySetInnerHTML`.
- Sospecha (no es violación comprobada): la UI conoce detalles de motor. `ModelManager.tsx:81` (`'faster-whisper:turbo'`) y `:97` (`provider_id === 'faster-whisper'`); `AddModelDialog.tsx:25` (`FAMILIES`) y campos de archivo tipo sherpa (`:53-56`). Un motor nuevo tocaría la UI.
- Sospecha de política duplicada: `api/providers.ts:206` (`isLoopbackUrl`) decide en el cliente si un endpoint es «cloud» y exige consentimiento (`CompatibleEndpoints.tsx:67`). La autoridad debe ser el servidor (no verificado en el backend).

#### 3. Diseño y mantenibilidad
- Tamaño: ver 1. Es mezcla de responsabilidades (varios componentes y diálogos por archivo), no un SRP roto solo por tamaño.
- Acoplamiento de tiempo: `Workspace.tsx:158-164` (`handleTimeUpdate`) pone `setCurrentMs` en cada `timeupdate`, y `currentMs` se pasa a `SegmentList` (`:335`) y a `MediaPanel` (`:366`). Así se re-renderiza la lista y la forma de onda, aunque exista el store de playhead para evitarlo (hipótesis de coste: medir con rendimiento).
- Lint: 4 `eslint-disable react-hooks/exhaustive-deps` en `SegmentList.tsx:374,385,416,423`.
- Texto sin i18n: `api/jobEvents.ts:49` y `:63-65`. Llega a la UI por `useJobEvents.error` → `JobScreen.tsx:236` y `:328`. Con la interfaz en inglés se muestra español.
- Código muerto: ninguna exportación sin uso fuera de tests (búsqueda por grep, aproximada). Excepción: la prop `loading` de arriba.

#### 4. Concurrencia, errores, carga, cancelación y edición
- Patrón sano: `AbortController` en cada efecto de carga (`useJobEvents.ts:37-55`, `Waveform.tsx:118-138`); cierre de `EventSource` en cleanup (`api/jobEvents.ts:30-70`); un PUT en vuelo por segmento (`hooks/useSegmentDrafts.ts:172-229`); `AudioContext` de boost solo bajo demanda y cerrado al desmontar (`AudioPlayer.tsx:119-126`).
- Errores silenciados: `useJobEvents.ts:46` ignora el fallo de la instantánea. `Workspace.tsx:246-248` muestra «cargando» mientras `events.error === null`; si el servidor cae al abrir un trabajo, el spinner queda indefinido salvo que el banner de `App.tsx:161-165` lo tape. `Workspace.tsx:308` ignora el fallo de `cancelJob` sin feedback.
- Subida sin cancelación: `NewProjectCard.tsx` no tiene control para cancelar; el `AbortController` solo se aborta al desmontar (`:97-101`, `:130-131`). `NewTranscription` no se desmonta al cambiar de vista (`App.tsx:186-199`), así que la subida sigue en segundo plano, y la fase `uploading` deshabilita el envío (`:107`). Comportamiento en navegador: hipótesis.
- Proyecto huérfano (hipótesis): el proyecto se crea antes de subir el medio (`NewProjectCard.tsx:134-139`). Si la subida falla o se aborta, queda un proyecto sin medio hasta reintentar.
- Borradores: sin vaciado al desmontar. `Workspace` se remonta con `key={route.jobId}` (`App.tsx:204`); los timers de autosave siguen vivos sin UI ni aviso, porque `beforeunload` solo cubre el cierre de página (`useSegmentDrafts.ts:240-248`). Hipótesis a verificar.
- Edición: borradores por id, debounce de 800 ms (`useSegmentDrafts.ts:10`, `:84-88`), conflicto con «usar mi versión» o «descartar» (`SegmentEditor.tsx:98-128`), Escape revierte (`SegmentEditor.tsx:72-76`).
- Autoscroll: `SegmentList.tsx:552-575` pausa con rueda, táctil, arrastre de barra o teclas de scroll; se reanuda con foco en un campo editable o con el botón «Seguir» (`:394-417`, `:538-549`). `LivePreview.tsx:52` sigue el final con un umbral de 24 px.
- Virtualización: alturas medidas con `ResizeObserver` en `SegmentList.tsx:316-350`; el resto se estima con la media. Ver FRONTEND-02.
- Sondeo: `useJobPreview` cada 1,5 s con backoff de 3 s y sin tope (`hooks/useJobPreview.ts:6`, `:71`); `seen` crece sin límite (`:37`). Se consulta en cualquier estado procesable sin transcript (`Workspace.tsx:95`), aunque el comentario dice «TRANSCRIBING» (`useJobPreview.ts:23-24`).
- Scroll: `SegmentList.tsx:559-561` llama `setScrollTop` en cada evento sin `requestAnimationFrame`.
- Sincronización audio–timeline–transcripción:
  - `AudioPlayer` emite `onTimeUpdate` en `timeupdate` y `seeked`, en ms enteros (`AudioPlayer.tsx:182-189`) → `Workspace.handleTimeUpdate` (`:158-164`) → `playhead.set` (`lib/playhead.ts:17-25`).
  - `SegmentList` resalta con `findActiveIndex` (`lib/activeSegment.ts`) y sigue con scroll; `WordText` resalta palabras con store externo (`WordText.tsx:81-92`, `lib/activeWord.ts`); `SpeakerTimeline` pinta el cursor (`SpeakerTimeline.tsx:45-57`).
  - Seek: `useSeek` incrementa un nonce (`hooks/useSeek.ts:20-23`) → efecto del reproductor (`AudioPlayer.tsx:103-116`). Clic en la forma de onda → `onSeek` (`Waveform.tsx:238-241`).
  - Duración: `AudioPlayer` usa `audio.duration` si existe (`AudioPlayer.tsx:128-133`), mientras la forma de onda y la línea de tiempo usan `duration_ms` del backend (`Waveform.tsx:116`, `Workspace.tsx:375`). Posible desfase del cursor al final (hipótesis).
  - Resolución: depende de la frecuencia de `timeupdate` del navegador; no hay bucle `requestAnimationFrame` (hipótesis: resaltado de palabra con resolución limitada). El fin de una muestra solo se comprueba en `timeupdate` (`AudioPlayer.tsx:185`), así que puede sobrepasarse (hipótesis).

#### 5. Seguridad y privacidad
- Sin secretos en almacenamiento del navegador (ver 1). Claves de proveedor solo en estado React (`ProvidersSettings.tsx:40`, `:51`).
- Consentimiento cloud: el inicio exige consentimiento (`NewTranscription.tsx:106`); `cloud_consent: true` solo se envía con opción cloud (`:93`); el consentimiento queda ligado a la opción elegida (`TranscriptionOptionsSelector.tsx:122-156`). Correcto en cliente; la garantía real depende del servidor (no verificado).
- La decisión de loopback en cliente (ver 2) debe comprobarla el servidor (revisión de seguridad).
- Sin fuga de rutas del host en la UI (ver 2).

#### 6. Pruebas y evidencias (nada ejecutado)
- 76 archivos `*.test.ts(x)` y unos 668 casos (conteo por grep de `it(`/`test(`). Muchos prueban funciones puras de `lib/` (`virtualRows`, `waveformGeometry`, `activeWord`, `timeline`).
- Huecos:
  - `test/setup.ts:29-41` sustituye `ResizeObserver` por un no-op. Ningún test ejerce la medición real de filas (`SegmentList`) ni de la forma de onda (`Waveform`).
  - No hay pruebas de captura, porque no existe captura.
  - `App.e2e.test.tsx` corre en jsdom (`apps/web/vite.config.ts:30`); no hay Playwright ni CDP en el repo.
  - `AudioPlayer.test.tsx:102-121` dispara `timeupdate` a mano; no hay pruebas de frecuencia real.
  - `eslint-disable` en `SegmentList.tsx` (ver 3).

#### 7. Preparación para STT en tiempo real
- Captura existente: NO. Búsqueda de `getUserMedia`, `MediaRecorder`, `AudioWorklet`, `navigator.mediaDevices` y `createScriptProcessor` en `apps/web/src`: 0 coincidencias. `AudioContext` aparece solo en `AudioPlayer.tsx:37-48`, `:100` y `:205-213`, para reproducción y ganancia por encima del 100 %.
- Soporte de APIs de captura: ninguno. Solo detección de `AudioContext`/`webkitAudioContext` (`AudioPlayer.tsx:41-48`) y `createMediaElementSource` para el boost (`:211`). Sin polyfill ni detección de MediaRecorder o AudioWorklet.
- Hooks existentes que NO sirven para micrófono: `useJobEvents` y `useJobPreview` (estado de trabajos en servidor), `useSpeakSample` y `useSynthesisEvents` (síntesis), `useSeek` más `AudioPlayer` (reproducción de archivo desde `/api/media/{id}/original`, `AudioPlayer.tsx:65-67`).
- Patrones reutilizables: suscripción con cierre (`useJobEvents.ts:21-63`); store externo de alta frecuencia (`lib/playhead.ts`, `WordText.tsx:81-92`); `useNow` (`hooks/useNow.ts`) para contadores; `useServerStatus` (`hooks/useServerStatus.ts:6`, dos fallos seguidos antes de avisar) para detectar caída.
- Pregunta abierta: estrategia de PCM con tasa de muestreo controlada. Opciones para un ADR, sin recomendación todavía:
  - (a) `AudioContext({ sampleRate })` con `AudioWorklet` que convierte Float32 a PCM16 y remuestrea si el navegador ignora la tasa (leer `ctx.sampleRate`). El módulo del worklet debe servirse como archivo estático; con el build de Vite hay que comprobarlo. Soporte entre navegadores: no verificado.
  - (b) `MediaRecorder` (normalmente Opus en WebM): sin PCM ni tasa controlada; el servidor tendría que decodificar (latencia y dependencia del códec).
  - (c) `ScriptProcessorNode`: obsoleto según la documentación de los navegadores; no se recomienda.
- Contexto seguro: `getUserMedia` exige contexto seguro. `127.0.0.1` y `localhost` lo son; el modo LAN con IP no lo sería (hipótesis técnica, verificar en el navegador objetivo). Decisión para arquitectura.
- Transporte: no hay WebSocket en el frontend, y el proxy de desarrollo solo cubre `/api` sin `ws: true` (`apps/web/vite.config.ts:21-27`). Un canal bidireccional exige cambiar esa configuración.
- Parciales y finales sin saltos: hoy `LivePreview` muestra solo segmentos confirmados, con clave `start:end:text` (`LivePreview.tsx:57`, `useJobPreview.ts:20-21`). Un cambio de texto en el mismo segmento duplicaría la fila (hipótesis según el contrato del backend). Al aparecer el transcript se intercambia `LivePreview` por `SegmentList` (`Workspace.tsx:326-358`). Recomendación: id estable por enunciado, reemplazo in situ del parcial y medición por id, no por índice (FRONTEND-02).
- Latencia, permisos, silencio, reconexión y pérdida de señal: no hay UI ni textos (búsqueda de micro, permiso, silencio y latencia: 0). Reutilizables: `Notice` (`components/Notice.tsx`), `Busy`, región `role="status"` (`HealthStatus.tsx:61`), reintento como en `useSynthesisEvents.ts:29-31`. Medidas: `AudioContext.baseLatency`/`outputLatency` (no miden la entrada); silencio con `AnalyserNode` (hipótesis); estado de permiso con `navigator.permissions` (no en todos los navegadores; no verificado).
- Ubicación: el `Workspace` actual es de trabajos guardados. Decidir con arquitectura si la captura va en una vista nueva.

#### 8. Accesibilidad, i18n y diseño
- Sistema real: Carbon (42 archivos importan `@carbon/react`). M3 es una piel opcional bajo `[data-design='m3']` (`theme/appearance.ts:32`, `:160`; `styles/m3/_components.scss` tiene 84 líneas con `cds--`). Carbon es el valor por defecto (`appearance.ts:101`). Sin piel M3 no hay regresión; con M3 la piel depende de clases internas de Carbon, lo que acopla a su versión.
- Accesibilidad a favor: `Waveform.tsx:297-309` (`role="slider"` con valuenow y valuetext), `WordText.tsx:157-158` (roving tabindex), `SegmentList.tsx:193-194` (`aria-posinset` y `aria-setsize`), etiquetas i18n en `SpeakerTimeline`.
- Accesibilidad en contra: cada palabra es `role="button"` (`WordText.tsx:157-160`), con muchos nodos interactivos. `SegmentEditor.tsx:79-97` cambia de estado sin región viva; solo el conflicto usa `role="alert"` (`:98`).
- i18n: catálogo tipado `[es, en]` (`i18n/messages.ts:13-17`, `i18n/i18n.ts:5-7`); el compilador garantiza paridad. Pluralización en `i18n.ts:104-111`. Fallo: ver 3 (`api/jobEvents.ts`).

#### 9. Reutilización sin acoplar el motor
- Reutilizable tal cual: `lib/playhead.ts`, `lib/activeWord.ts`, `lib/activeSegment.ts`, `lib/timeline.ts`, `lib/virtualRows.ts`, `lib/scrollDelta.ts`, `lib/waveformGeometry.ts` (sin DOM), `i18n/*`, `Notice`, `Busy`, `Panel`, `Hint`, `useNow`, `useServerStatus`.
- Reutilizable con cambios menores: `WordText` (necesita palabras y playhead), `SpeakerTimeline` (segmentos y playhead), `LivePreview` (forma `PreviewSegment`), `AudioPlayer` (ya acepta `src`; la URL por defecto está fija en `AudioPlayer.tsx:65-67`).
- Acoplados a la API actual: `Waveform` (`api/waveform.ts`), `SegmentList` (`getSegments`), `useJobEvents` (`/api/jobs/{id}/events`), `NewProjectCard` (`uploadMedia`).

#### 10. Top 5 hallazgos
| ID | Severidad | Hallazgo | Evidencia | Impacto | Recomendación |
|---|---|---|---|---|---|
| FRONTEND-01 | alta | No existe captura de micrófono en el navegador ni detección de sus APIs | Búsqueda sin resultados de getUserMedia, MediaRecorder, AudioWorklet, mediaDevices; `AudioPlayer.tsx:37-48, 205-213` | Bloquea el STT en vivo desde la UI | Decidir en ADR la estrategia PCM (a/b), el transporte y el contexto seguro; no reutilizar `useJobEvents` ni `AudioPlayer` para captura |
| FRONTEND-02 | media | Virtualización medida por índice, sin reinicio al filtrar; ningún test ejerce ResizeObserver real | `SegmentList.tsx:98-113, 284, 307-310, 316-350`; `test/setup.ts:29-41` (hipótesis: saltos de alturas al filtrar o editar) | Saltos de scroll y alturas erróneas | Medir con una transcripción real (rendimiento); clave por `segment.id`; test con medición simulada |
| FRONTEND-03 | media | Fallo de la instantánea y de la cancelación silenciados; el spinner queda sin error | `useJobEvents.ts:46`; `Workspace.tsx:246-248, 308` | El usuario no ve el fallo al abrir o al cancelar | Mostrar error y reintento como en `useSynthesisEvents`; feedback de cancelación |
| FRONTEND-04 | media | Subida sin cancelación en la UI; proyecto huérfano posible tras un fallo (hipótesis) | `NewProjectCard.tsx:97-101, 130-155`; `App.tsx:186-199` | No se puede detener una subida larga; biblioteca con proyectos vacíos | Decidir la UX de cancelar y la política de limpieza del proyecto |
| FRONTEND-05 | media | Textos en español sin i18n llegan a la UI en inglés | `api/jobEvents.ts:49, 63-65` → `JobScreen.tsx:236, 328` | Incumple la paridad en/es | Usar códigos estables con `translateCode`; prueba con locale `en` |

#### 11. No verificado
- No se ejecutó ningún test, build, lint ni navegador. Los conteos de tests y líneas son estáticos.
- Comportamiento real: frecuencia de `timeupdate`, `ResizeObserver`, `EventSource`, soporte por navegador de AudioWorklet, MediaRecorder y permisos.
- Contrato del backend: si `after_ms` es inclusivo (`api/preview.ts`, `useJobPreview.ts:51`), si la vista previa recibe revisiones de texto, y si el servidor aplica el consentimiento cloud y la regla de loopback.
- Los 55 omitidos (SCSS y catálogos i18n) y el contenido detallado de 76 tests.
- Hipótesis marcadas en el texto: pérdida de borradores al desmontar, proyecto huérfano, saltos de alturas al filtrar, coste de re-render por `timeupdate`, desfase de duración entre reproductor y forma de onda.
