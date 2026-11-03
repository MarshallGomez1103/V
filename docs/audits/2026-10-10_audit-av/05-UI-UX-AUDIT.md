# 05 · Auditoría de frontend y experiencia de usuario

## Veredicto

La interfaz es **funcional, coherente y accesible en lo básico**. Usa IBM Carbon con tokens propios, tiene i18n es/en y estados vacíos con guía. Lo que falta: verificación en navegador de los flujos de revisión y audio, responsividad más allá de la pantalla de inicio, y un bundle principal de 752 KB que conviene dividir.

## Verificación en navegador (esta auditoría)

Herramienta: `chrome-headless-shell` de Playwright ya instalado en el equipo, servidor VOZ en puerto temporal 8799 con XDG aislado (base vacía). Servidor detenido después; puerto libre; la base real de el responsable no cambió (tamaño y mtime idénticos antes y después).

| Captura | Archivo | Resultado |
|---|---|---|
| Home, escritorio 1280×860 | `evidencia/home-desktop-1280.png` | Cabecera con Home, Transcribir, Modelos, Proveedores; estado "Available · Local API · 127.0.0.1 · v0.1.0"; tarjeta "Saved transcripts" con estado vacío, guía de 3 pasos y enlace a Modelos; botón primario "New transcription". Sin errores visibles. |
| Home, teléfono 390×844 | `evidencia/home-phone-390.png` | Menú colapsa a icono de hamburguesa; tarjeta a ancho completo; sin scroll horizontal visible. |

Limitación: el navegador estaba en inglés, así que la UI salió en inglés (la detección de idioma sigue el navegador). No se capturó la UI con transcripciones reales: no se importaron medios ni se usó la base de el responsable, por privacidad.

## Pantallas (según código y tests)

| Pantalla | Componente | Estado |
|---|---|---|
| Home / biblioteca | `components/Library.tsx` (`DataTable`, `TableToolbarSearch`, `Modal` para renombrar y eliminar) | Implementada; tests en `Library.test.tsx`; vacío verificado |
| Nueva transcripción (upload + motor + perfil) | `NewProjectCard.tsx`, `NewTranscription.tsx`, `TranscriptionOptionsSelector.tsx` | Implementada; XHR con progreso, errores por código |
| Job (progreso por etapa, ETA, cancelar) | `JobScreen.tsx`, `hooks/useJobEvents.ts` | Implementada; progreso por SSE |
| Workspace (forma de onda, reproductor, lista, búsqueda) | `Workspace.tsx`, `Waveform.tsx`, `AudioPlayer.tsx`, `SegmentList.tsx` | Implementada; virtualizada (`SegmentRow` memo, `lib/virtualRows.ts`) |
| Revisión de segmentos | `ReviewQueue.tsx` | Implementada; saltar al segmento: ver brecha abajo |
| Hablantes | `SpeakersPanel.tsx`, `SpeakerTimeline.tsx`, `SegmentSpeakerSelect.tsx` | Implementada; tiempo de habla, muestra, recalcular |
| Exportar | `ExportDialog.tsx` (`RadioTile`, `Toggle`, vista previa) | Implementada; la vista previa carga el texto real |
| Modelos | `ModelManager.tsx` (702 líneas) | Implementada; descarga con progreso, borrado tecleando el id |
| Proveedores cloud | `ProvidersSettings.tsx`, badge `CloudBadge.tsx` | Implementada; consentimiento obligatorio; sin mostrar claves |
| Ajustes | Menú de cabecera, `theme/appearance.ts`, `styles/m3/` | Carbon o Material 3, claro/oscuro, acentos |

## Accesibilidad — verificado por conteo

| Métrica | Resultado |
|---|---|
| Atributos `aria-*` en `src` (sin tests) | 125 |
| Atributos `role="..."` | 56 |
| Componentes que usan `aria-label` o `title` en controles de volumen | sí (`AudioPlayer.tsx:324,340,347`) |
| Atajos de teclado | espacio y ←/→ (5 s) en `AudioPlayer.tsx:149-162`; teclado en `WordText` y waveform (ROADMAP WAVEFORM-001) |
| Modal con foco | Carbon `Modal` (gestiona foco y Escape) |

No se hizo una auditoría con lector de pantalla ni axe; "accesible en lo básico" significa solo lo que el conteo y el código muestran.

## Responsividad — verificado por conteo y captura

- Reglas `@media` en todo `src`: **4**, en `JobScreen.scss`, `SegmentList.scss`, `styles/m3/_components.scss` e `index.scss`.
- Sin contenedores (`@container`): **0**.
- Home verificada a 390 px (captura). Workspace, Modelos, Exportar y Hablantes a ancho de teléfono: **no verificados**.

## Rendimiento

- Bundle principal `src/voz/static/assets/index-D57cQAlz.js`: **752 423 bytes** en un solo chunk. Vite avisa de chunks > 500 kB durante el build (verificado en esta auditoría).
- Chunk Material 3 separado y perezoso: `m3-y9ruFiH9.js`, 83 854 bytes.
- Virtualización de la lista de segmentos y memo por fila (ROADMAP TRANSCRIPT-VIEW-001: 10 000 segmentos, 2 renders por cambio).
- Forma de onda por streaming de FFmpeg (1 h WAV en 0,86 s y 70 MB RSS, según ROADMAP WAVEFORM-001).
- Fuentes IBM Plex y Roboto Flex empaquetadas localmente (funciona sin red).

Recomendación: cargar Modelos, Proveedores y Exportar con `lazy()` para reducir el chunk inicial. No ajustar `chunkSizeWarningLimit` como solución.

## Estados

| Estado | Evidencia |
|---|---|
| Vacío | Verificado: Home sin transcripciones con guía |
| Carga | Tests de hooks (`useServerStatus`, `useJobPreview`) y `Busy.tsx` |
| Error de servidor | `ServerBanner.tsx`, `ClosedScreen.tsx`; tests `App.flows.test.tsx` |
| Error de job | `JobScreen` con códigos estables; 409 `option_not_startable` verificado en vivo (ROADMAP UI-JOB-001) |
| Conflicto de edición | 409 resoluble en `useSegmentDrafts.ts` (tests) |
| Servidor cerrado | `ClosedScreen.tsx` y apagado desde UI |

## Navegación

- Rutas por hash (`lib/navigation.ts`): `#/`, `#/nueva`, `#/t/<jobId>`, `#/modelos`, `#/proveedores`. Atrás y adelante del navegador funcionan según tests (`navigation.test.ts`). Recargar `#/t/<id>` reabre el trabajo.
- Logo "VOZ" lleva a Home.

## Brecha abierta: filas de segmento en blanco

HANDOFF registra: "filas de segmento en blanco tras seek+autoscroll (visto solo en Chrome headless; content-visibility)". **No reproducido en esta auditoría** (no se cargó una transcripción). Es el defecto de UI más importante pendiente, porque afecta al flujo de revisión.

## Comparación con los objetivos originales (ElevenLabs como referencia de experiencia, no de identidad)

| Objetivo | Estado |
|---|---|
| Editor con forma de onda y segmentos | Cumplido |
| Edición de texto con autosave | Cumplido |
| Hablantes por color, línea de tiempo y muestra | Cumplido |
| Exportación con opciones visibles | Cumplido (v3) |
| Reproducción con velocidad y volumen | Cumplido (hasta 300 %) |
| Respuesta rápida en archivos largos | Parcial: virtualización y streaming sí; carga inicial de 752 KB no optimizada |
| Biblioteca con búsqueda y acciones | Cumplido |
| Responsive completo | No verificado fuera de Home |

No se recomienda copiar la identidad visual ni los recursos de ElevenLabs. La identidad actual (Carbon, IBM Plex) es propia del proyecto.

## Problemas de UI

| ID | Descripción | Severidad | Evidencia |
|---|---|---|---|
| UI-01 | Filas en blanco tras seek+autoscroll | P1 (no verificado) | HANDOFF |
| UI-02 | Solo 4 reglas `@media` | P2 | Conteo |
| UI-03 | Bundle inicial de 752 KB | P2 | Build |
| UI-04 | Glosario muestra ids crudos | P3 | HANDOFF |
| UI-05 | Sin verificación de navegación por teclado completa | P2 | Sin herramienta de a11y ejecutada |
