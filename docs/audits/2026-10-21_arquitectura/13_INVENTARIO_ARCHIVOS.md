# 13 · Inventario de archivos versionados

HEAD `96284c5` · 904 archivos (`git ls-files`). Columnas: ruta relativa · área propietaria · líneas · nivel de inspección declarado por la investigación propietaria (`profunda`, `superficial`, `omitido` con motivo). Los archivos de la revisión central (documentación general, plantillas de GitHub, capturas, licencias) son **contexto**: se leyeron solo las partes citadas en los informes y no se auditaron como código.

| Ruta | Área | Líneas | Nivel |
|---|---|---:|---|
| `.gitattributes` | revisión central | 8 | contexto |
| `.github/ISSUE_TEMPLATE/bug_report.md` | revisión central | 49 | contexto |
| `.github/ISSUE_TEMPLATE/config.yml` | revisión central | 12 | contexto |
| `.github/ISSUE_TEMPLATE/feature_request.md` | revisión central | 42 | contexto |
| `.github/ISSUE_TEMPLATE/security_contact.md` | revisión central | 12 | contexto |
| `.github/pull_request_template.md` | revisión central | 44 | contexto |
| `.github/workflows/ci.yml` | informe_quality | 125 | profunda |
| `.github/workflows/launchers.yml` | informe_quality | 92 | profunda |
| `.github/workflows/release-dry-run.yml` | informe_quality | 59 | profunda |
| `.gitignore` | revisión central | 119 | contexto |
| `.python-version` | informe_quality | 1 | superficial |
| `AGENTS.md` | revisión central | 161 | contexto |
| `CHANGELOG.md` | revisión central | 186 | contexto |
| `CODE_OF_CONDUCT.md` | revisión central | 135 | contexto |
| `CONTRIBUTING.md` | revisión central | 192 | contexto |
| `LICENSE` | revisión central | 21 | contexto |
| `NOTICE` | revisión central | 120 | contexto |
| `README.md` | revisión central | 518 | contexto |
| `ROADMAP.md` | revisión central | 637 | contexto |
| `SECURITY.md` | revisión central | 165 | contexto |
| `Start-V-Windows.bat` | informe_quality | 34 | profunda |
| `Start-V-macOS.command` | informe_quality | 34 | profunda |
| `VOZ_PLAN_MAESTRO.md` | revisión central | 1340 | contexto |
| `alembic.ini` | informe_persistence_jobs | 39 | omitido — no revisado en esta pasada (configuración Alembic sin lógica de persistencia) |
| `apps/web/eslint.config.js` | informe_quality | 32 | profunda |
| `apps/web/index.html` | informe_quality | 20 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `apps/web/package-lock.json` | informe_quality | 4685 | superficial — solo cabecera y conteo de paquetes |
| `apps/web/package.json` | informe_quality | 41 | profunda |
| `apps/web/public/favicon.svg` | informe_quality | 4 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `apps/web/public/icon-192.png` | informe_quality | 10 | omitido — binario; solo tamaño en la lista |
| `apps/web/public/icon-512.png` | informe_quality | 40 | omitido — binario; solo tamaño en la lista |
| `apps/web/public/icon-maskable-512.png` | informe_quality | 40 | omitido — binario; solo tamaño en la lista |
| `apps/web/public/licenses/IBM-Plex-OFL.txt` | informe_quality | 93 | omitido — texto de licencia de terceros, sin lógica |
| `apps/web/public/licenses/Roboto-Flex-OFL.txt` | informe_quality | 93 | omitido — texto de licencia de terceros, sin lógica |
| `apps/web/public/licenses/Third-party-JavaScript.txt` | informe_quality | 4418 | omitido — texto de licencia de terceros, sin lógica |
| `apps/web/public/manifest.webmanifest` | informe_quality | 15 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `apps/web/src/App.e2e.test.tsx` | informe_frontend | 502 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/App.flows.test.tsx` | informe_frontend | 864 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/App.scss` | informe_frontend | 144 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/App.test.tsx` | informe_frontend | 203 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/App.tsx` | informe_frontend | 265 | profunda |
| `apps/web/src/api/customModels.test.ts` | informe_frontend | 143 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/customModels.ts` | informe_frontend | 186 | superficial |
| `apps/web/src/api/desktopShortcut.test.ts` | informe_frontend | 84 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/desktopShortcut.ts` | informe_frontend | 74 | superficial |
| `apps/web/src/api/errors.ts` | informe_frontend | 36 | superficial |
| `apps/web/src/api/exportDocument.ts` | informe_frontend | 66 | superficial |
| `apps/web/src/api/glossary.test.ts` | informe_frontend | 67 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/glossary.ts` | informe_frontend | 88 | superficial |
| `apps/web/src/api/health.ts` | informe_frontend | 32 | superficial |
| `apps/web/src/api/jobEvents.ts` | informe_frontend | 70 | profunda |
| `apps/web/src/api/jobs.test.ts` | informe_frontend | 163 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/jobs.ts` | informe_frontend | 323 | profunda — lectura parcial (rangos indicados en el informe) |
| `apps/web/src/api/library.test.ts` | informe_frontend | 103 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/library.ts` | informe_frontend | 185 | superficial |
| `apps/web/src/api/media.ts` | informe_frontend | 119 | profunda |
| `apps/web/src/api/models.test.ts` | informe_frontend | 294 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/models.ts` | informe_frontend | 333 | superficial |
| `apps/web/src/api/preview.ts` | informe_frontend | 47 | profunda |
| `apps/web/src/api/projects.ts` | informe_frontend | 97 | superficial |
| `apps/web/src/api/providers.test.ts` | informe_frontend | 146 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/providers.ts` | informe_frontend | 264 | superficial |
| `apps/web/src/api/qualityProfiles.test.ts` | informe_frontend | 64 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/qualityProfiles.ts` | informe_frontend | 120 | superficial |
| `apps/web/src/api/segments.test.ts` | informe_frontend | 113 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/segments.ts` | informe_frontend | 119 | superficial |
| `apps/web/src/api/shutdown.test.ts` | informe_frontend | 60 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/shutdown.ts` | informe_frontend | 51 | superficial |
| `apps/web/src/api/speakers.test.ts` | informe_frontend | 153 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/speakers.ts` | informe_frontend | 200 | superficial |
| `apps/web/src/api/synthesis.test.ts` | informe_frontend | 353 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/api/synthesis.ts` | informe_frontend | 383 | superficial |
| `apps/web/src/api/transcriptionOptions.ts` | informe_frontend | 212 | superficial |
| `apps/web/src/api/waveform.ts` | informe_frontend | 89 | profunda |
| `apps/web/src/components/AddModelDialog.scss` | informe_frontend | 46 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/AddModelDialog.test.tsx` | informe_frontend | 380 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/AddModelDialog.tsx` | informe_frontend | 353 | superficial |
| `apps/web/src/components/AppHeader.scss` | informe_frontend | 7 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/AppHeader.test.tsx` | informe_frontend | 43 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/AppHeader.tsx` | informe_frontend | 127 | superficial |
| `apps/web/src/components/AudioPlayer.scss` | informe_frontend | 141 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/AudioPlayer.test.tsx` | informe_frontend | 320 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/AudioPlayer.tsx` | informe_frontend | 413 | profunda |
| `apps/web/src/components/AutosaveStatus.scss` | informe_frontend | 28 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/AutosaveStatus.test.tsx` | informe_frontend | 69 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/AutosaveStatus.tsx` | informe_frontend | 47 | superficial |
| `apps/web/src/components/Busy.tsx` | informe_frontend | 9 | superficial |
| `apps/web/src/components/ClosedScreen.scss` | informe_frontend | 30 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ClosedScreen.tsx` | informe_frontend | 21 | superficial |
| `apps/web/src/components/CloudBadge.tsx` | informe_frontend | 14 | superficial |
| `apps/web/src/components/CompatibleEndpoints.test.tsx` | informe_frontend | 194 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/CompatibleEndpoints.tsx` | informe_frontend | 466 | superficial |
| `apps/web/src/components/DesktopShortcut.test.tsx` | informe_frontend | 125 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/DesktopShortcut.tsx` | informe_frontend | 148 | superficial |
| `apps/web/src/components/DiarizationOptions.scss` | informe_frontend | 53 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/DiarizationOptions.test.tsx` | informe_frontend | 182 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/DiarizationOptions.tsx` | informe_frontend | 285 | superficial |
| `apps/web/src/components/ExportDialog.scss` | informe_frontend | 63 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ExportDialog.tsx` | informe_frontend | 212 | superficial |
| `apps/web/src/components/GlossaryEditor.scss` | informe_frontend | 6 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/GlossaryEditor.test.tsx` | informe_frontend | 111 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/GlossaryEditor.tsx` | informe_frontend | 143 | superficial |
| `apps/web/src/components/HeaderMenus.scss` | informe_frontend | 191 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/HeaderMenus.tsx` | informe_frontend | 195 | superficial |
| `apps/web/src/components/HealthStatus.scss` | informe_frontend | 12 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/HealthStatus.tsx` | informe_frontend | 72 | superficial |
| `apps/web/src/components/Hint.scss` | informe_frontend | 26 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/Hint.test.tsx` | informe_frontend | 55 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/Hint.tsx` | informe_frontend | 56 | superficial |
| `apps/web/src/components/JobScreen.scss` | informe_frontend | 176 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/JobScreen.test.tsx` | informe_frontend | 354 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/JobScreen.tsx` | informe_frontend | 369 | superficial |
| `apps/web/src/components/Library.scss` | informe_frontend | 124 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/Library.test.tsx` | informe_frontend | 191 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/Library.tsx` | informe_frontend | 462 | superficial |
| `apps/web/src/components/LivePreview.scss` | informe_frontend | 46 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/LivePreview.test.tsx` | informe_frontend | 40 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/LivePreview.tsx` | informe_frontend | 73 | profunda |
| `apps/web/src/components/MediaPanel.scss` | informe_frontend | 5 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/MediaPanel.tsx` | informe_frontend | 104 | profunda |
| `apps/web/src/components/ModelManager.scss` | informe_frontend | 116 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ModelManager.test.tsx` | informe_frontend | 892 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/ModelManager.tsx` | informe_frontend | 803 | superficial |
| `apps/web/src/components/NewProjectCard.scss` | informe_frontend | 29 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/NewProjectCard.test.tsx` | informe_frontend | 296 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/NewProjectCard.tsx` | informe_frontend | 263 | profunda — lectura parcial (rangos indicados en el informe) |
| `apps/web/src/components/NewTranscription.test.tsx` | informe_frontend | 104 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/NewTranscription.tsx` | informe_frontend | 236 | profunda — lectura parcial (rangos indicados en el informe) |
| `apps/web/src/components/Notice.tsx` | informe_frontend | 61 | superficial |
| `apps/web/src/components/Panel.scss` | informe_frontend | 61 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/Panel.tsx` | informe_frontend | 55 | superficial |
| `apps/web/src/components/ProfileSelector.scss` | informe_frontend | 55 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ProfileSelector.test.tsx` | informe_frontend | 149 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/ProfileSelector.tsx` | informe_frontend | 166 | superficial |
| `apps/web/src/components/PropertiesPanel.scss` | informe_frontend | 46 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/PropertiesPanel.tsx` | informe_frontend | 118 | superficial |
| `apps/web/src/components/ProvidersSettings.scss` | informe_frontend | 38 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ProvidersSettings.test.tsx` | informe_frontend | 214 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/ProvidersSettings.tsx` | informe_frontend | 205 | superficial |
| `apps/web/src/components/ReviewQueue.scss` | informe_frontend | 57 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/ReviewQueue.test.tsx` | informe_frontend | 117 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/ReviewQueue.tsx` | informe_frontend | 165 | superficial |
| `apps/web/src/components/SegmentEditor.scss` | informe_frontend | 103 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SegmentEditor.test.tsx` | informe_frontend | 175 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SegmentEditor.tsx` | informe_frontend | 132 | profunda |
| `apps/web/src/components/SegmentList.scss` | informe_frontend | 204 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SegmentList.test.tsx` | informe_frontend | 545 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SegmentList.tsx` | informe_frontend | 714 | profunda |
| `apps/web/src/components/SegmentSpeakerSelect.scss` | informe_frontend | 31 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SegmentSpeakerSelect.test.tsx` | informe_frontend | 112 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SegmentSpeakerSelect.tsx` | informe_frontend | 68 | superficial |
| `apps/web/src/components/ServerBanner.tsx` | informe_frontend | 24 | superficial |
| `apps/web/src/components/ShutdownAction.tsx` | informe_frontend | 80 | superficial |
| `apps/web/src/components/SpeakHistory.scss` | informe_frontend | 66 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SpeakHistory.test.tsx` | informe_frontend | 284 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakHistory.tsx` | informe_frontend | 186 | superficial |
| `apps/web/src/components/SpeakResult.scss` | informe_frontend | 54 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SpeakResult.tsx` | informe_frontend | 169 | superficial |
| `apps/web/src/components/SpeakVoicePicker.cloud.test.tsx` | informe_frontend | 142 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakVoicePicker.test.tsx` | informe_frontend | 65 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakVoicePicker.tsx` | informe_frontend | 159 | superficial |
| `apps/web/src/components/SpeakWorkspace.flow.test.tsx` | informe_frontend | 644 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakWorkspace.history.test.tsx` | informe_frontend | 94 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakWorkspace.scss` | informe_frontend | 115 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SpeakWorkspace.test.tsx` | informe_frontend | 238 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakWorkspace.tsx` | informe_frontend | 364 | superficial |
| `apps/web/src/components/SpeakerTimeline.scss` | informe_frontend | 128 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SpeakerTimeline.test.tsx` | informe_frontend | 223 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakerTimeline.tsx` | informe_frontend | 203 | profunda |
| `apps/web/src/components/SpeakersPanel.scss` | informe_frontend | 94 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/SpeakersPanel.test.tsx` | informe_frontend | 380 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/SpeakersPanel.tsx` | informe_frontend | 509 | superficial |
| `apps/web/src/components/StyleInstructions.scss` | informe_frontend | 23 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/StyleInstructions.test.tsx` | informe_frontend | 55 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/StyleInstructions.tsx` | informe_frontend | 76 | superficial |
| `apps/web/src/components/TechTerms.tsx` | informe_frontend | 69 | superficial |
| `apps/web/src/components/TranscriptionOptionsSelector.scss` | informe_frontend | 82 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/TranscriptionOptionsSelector.test.tsx` | informe_frontend | 623 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/TranscriptionOptionsSelector.tsx` | informe_frontend | 422 | superficial |
| `apps/web/src/components/Waveform.scss` | informe_frontend | 76 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/Waveform.test.tsx` | informe_frontend | 350 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/Waveform.tsx` | informe_frontend | 333 | profunda |
| `apps/web/src/components/WordText.scss` | informe_frontend | 21 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/components/WordText.test.tsx` | informe_frontend | 106 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/WordText.tsx` | informe_frontend | 175 | profunda |
| `apps/web/src/components/Workspace.test.tsx` | informe_frontend | 263 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/components/Workspace.tsx` | informe_frontend | 427 | profunda |
| `apps/web/src/components/tableSort.ts` | informe_frontend | 15 | superficial |
| `apps/web/src/hooks/useCloudProviders.test.tsx` | informe_frontend | 107 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useCloudProviders.ts` | informe_frontend | 51 | superficial |
| `apps/web/src/hooks/useDiarizationModel.test.tsx` | informe_frontend | 135 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useDiarizationModel.ts` | informe_frontend | 171 | superficial |
| `apps/web/src/hooks/useJobEvents.test.tsx` | informe_frontend | 157 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useJobEvents.ts` | informe_frontend | 63 | profunda |
| `apps/web/src/hooks/useJobPreview.test.tsx` | informe_frontend | 96 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useJobPreview.ts` | informe_frontend | 84 | profunda |
| `apps/web/src/hooks/useLibrary.ts` | informe_frontend | 41 | profunda |
| `apps/web/src/hooks/useModelTasks.test.tsx` | informe_frontend | 156 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useModelTasks.ts` | informe_frontend | 103 | profunda |
| `apps/web/src/hooks/useNow.ts` | informe_frontend | 24 | profunda |
| `apps/web/src/hooks/useRoute.ts` | informe_frontend | 31 | profunda |
| `apps/web/src/hooks/useSeek.test.tsx` | informe_frontend | 35 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useSeek.ts` | informe_frontend | 26 | profunda |
| `apps/web/src/hooks/useSegmentDrafts.test.tsx` | informe_frontend | 328 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useSegmentDrafts.ts` | informe_frontend | 251 | profunda |
| `apps/web/src/hooks/useServerStatus.test.tsx` | informe_frontend | 93 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useServerStatus.ts` | informe_frontend | 68 | profunda |
| `apps/web/src/hooks/useSpeakSample.ts` | informe_frontend | 139 | superficial |
| `apps/web/src/hooks/useSynthesisEvents.test.tsx` | informe_frontend | 172 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/hooks/useSynthesisEvents.ts` | informe_frontend | 77 | profunda |
| `apps/web/src/i18n/i18n.test.ts` | informe_frontend | 135 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/i18n/i18n.ts` | informe_frontend | 135 | profunda |
| `apps/web/src/i18n/messages.ts` | informe_frontend | 31 | profunda |
| `apps/web/src/i18n/messages/addModel.ts` | informe_frontend | 60 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/endpoints.ts` | informe_frontend | 85 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/errors.ts` | informe_frontend | 329 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/job.ts` | informe_frontend | 181 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/library.ts` | informe_frontend | 205 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/models.ts` | informe_frontend | 150 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/shell.ts` | informe_frontend | 178 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/speak.ts` | informe_frontend | 277 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/speakHistory.ts` | informe_frontend | 16 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/transcribe.ts` | informe_frontend | 424 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/i18n/messages/workspace.ts` | informe_frontend | 186 | omitido — catálogo tipado por Pair; contenido no leído por archivo |
| `apps/web/src/lib/activeSegment.test.ts` | informe_frontend | 48 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/activeSegment.ts` | informe_frontend | 38 | profunda |
| `apps/web/src/lib/activeWord.test.ts` | informe_frontend | 45 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/activeWord.ts` | informe_frontend | 35 | profunda |
| `apps/web/src/lib/formatBytes.test.ts` | informe_frontend | 26 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/formatBytes.ts` | informe_frontend | 18 | superficial |
| `apps/web/src/lib/formatTime.ts` | informe_frontend | 32 | superficial |
| `apps/web/src/lib/media.ts` | informe_frontend | 5 | superficial |
| `apps/web/src/lib/modelOrder.test.ts` | informe_frontend | 20 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/modelOrder.ts` | informe_frontend | 19 | superficial |
| `apps/web/src/lib/navigation.test.ts` | informe_frontend | 60 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/navigation.ts` | informe_frontend | 87 | superficial |
| `apps/web/src/lib/playhead.test.ts` | informe_frontend | 21 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/playhead.ts` | informe_frontend | 33 | profunda |
| `apps/web/src/lib/qualityFlags.ts` | informe_frontend | 21 | superficial |
| `apps/web/src/lib/scrollDelta.test.ts` | informe_frontend | 25 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/scrollDelta.ts` | informe_frontend | 17 | profunda |
| `apps/web/src/lib/segmentSearch.test.ts` | informe_frontend | 77 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/segmentSearch.ts` | informe_frontend | 101 | superficial |
| `apps/web/src/lib/speakChoice.test.ts` | informe_frontend | 193 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/speakChoice.ts` | informe_frontend | 163 | superficial |
| `apps/web/src/lib/speakText.test.ts` | informe_frontend | 47 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/speakText.ts` | informe_frontend | 26 | superficial |
| `apps/web/src/lib/speakerTurns.test.ts` | informe_frontend | 48 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/speakerTurns.ts` | informe_frontend | 104 | superficial |
| `apps/web/src/lib/time.test.ts` | informe_frontend | 36 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/time.ts` | informe_frontend | 9 | superficial |
| `apps/web/src/lib/timeline.test.ts` | informe_frontend | 53 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/timeline.ts` | informe_frontend | 76 | profunda |
| `apps/web/src/lib/virtualRows.test.ts` | informe_frontend | 41 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/virtualRows.ts` | informe_frontend | 86 | profunda |
| `apps/web/src/lib/waveformGeometry.test.ts` | informe_frontend | 175 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/lib/waveformGeometry.ts` | informe_frontend | 157 | profunda |
| `apps/web/src/main.tsx` | informe_frontend | 21 | profunda |
| `apps/web/src/styles/_accent.scss` | informe_frontend | 74 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/_carbon.scss` | informe_frontend | 5 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/_shape.scss` | informe_frontend | 18 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/index.scss` | informe_frontend | 79 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/m3/_components.scss` | informe_frontend | 385 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/m3/_shape.scss` | informe_frontend | 22 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/m3/_tokens.scss` | informe_frontend | 208 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/m3/_type.scss` | informe_frontend | 69 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/styles/m3/index.scss` | informe_frontend | 6 | omitido — solo grep de cds-- y !important; estilos no leídos por archivo |
| `apps/web/src/test/setup.ts` | informe_frontend | 50 | profunda |
| `apps/web/src/theme/appearance.test.ts` | informe_frontend | 143 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/theme/appearance.ts` | informe_frontend | 271 | profunda |
| `apps/web/src/theme/m3.test.ts` | informe_frontend | 87 | superficial — solo conteo de casos y mocks globales (grep); no leído en detalle |
| `apps/web/src/theme/m3.ts` | informe_frontend | 100 | profunda |
| `apps/web/tsconfig.app.json` | informe_quality | 24 | profunda |
| `apps/web/tsconfig.json` | informe_quality | 7 | profunda |
| `apps/web/tsconfig.node.json` | informe_quality | 17 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `apps/web/vite.config.ts` | informe_quality | 39 | profunda |
| `docs/adr/0001-modular-monolith.md` | informe_quality | 215 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0002-sqlite-persistence.md` | informe_quality | 174 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0003-ffmpeg-ingestion.md` | informe_quality | 189 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0004-local-asr-and-recoverable-chunks.md` | informe_quality | 196 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0005-transcription-providers.md` | informe_quality | 161 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0006-local-first-privacy.md` | informe_quality | 172 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0007-local-diarization-sherpa-onnx.md` | informe_quality | 122 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0008-word-timestamps.md` | informe_quality | 113 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0009-rename-to-v.md` | informe_quality | 175 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0010-voice-engines-and-tts.md` | informe_quality | 311 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/0011-edge-lab.md` | informe_quality | 243 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/adr/README.md` | informe_quality | 32 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/README.md` | informe_quality | 63 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/authentication.md` | informe_quality | 87 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/export.md` | informe_quality | 83 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/jobs.md` | informe_quality | 504 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/library.md` | informe_quality | 117 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/models.md` | informe_quality | 458 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/openai-compat.md` | informe_quality | 111 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/projects.md` | informe_quality | 48 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/providers.md` | informe_quality | 178 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/segments.md` | informe_quality | 114 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/speakers.md` | informe_quality | 92 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/synthesis.md` | informe_quality | 161 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/transcription-options.md` | informe_quality | 119 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/api/waveform.md` | informe_quality | 58 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/architecture/01-contexto.md` | informe_quality | 72 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/architecture/02-contenedores.md` | informe_quality | 108 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/architecture/03-componentes.md` | informe_quality | 289 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/architecture/README.md` | informe_quality | 53 | segunda lectura (informe_adr_docs): decisión/afirmaciones frente al código |
| `docs/assets/screenshots/m3-accents-dark-es.png` | revisión central | 653 | contexto |
| `docs/assets/screenshots/m3-carbon-dark-es-workspace.png` | revisión central | 812 | contexto |
| `docs/assets/screenshots/m3-carbon-light-en-home.png` | revisión central | 168 | contexto |
| `docs/assets/screenshots/m3-m3-dark-es-settings.png` | revisión central | 381 | contexto |
| `docs/assets/screenshots/m3-m3-dark-es-workspace.png` | revisión central | 871 | contexto |
| `docs/assets/screenshots/m3-m3-light-en-home.png` | revisión central | 216 | contexto |
| `docs/assets/screenshots/m3-m3-light-en-settings.png` | revisión central | 266 | contexto |
| `docs/assets/screenshots/v-export.png` | revisión central | 474 | contexto |
| `docs/assets/screenshots/v-library-material3.png` | revisión central | 201 | contexto |
| `docs/assets/screenshots/v-model-import-url.png` | revisión central | 263 | contexto |
| `docs/assets/screenshots/v-models.png` | revisión central | 339 | contexto |
| `docs/assets/screenshots/v-speakers-playback.png` | revisión central | 148 | contexto |
| `docs/assets/screenshots/v-speech.png` | revisión central | 226 | contexto |
| `docs/assets/screenshots/v-workspace.png` | revisión central | 586 | contexto |
| `docs/benchmarks.md` | revisión central | 423 | contexto |
| `docs/buzz.md` | revisión central | 64 | contexto |
| `docs/demo.md` | revisión central | 130 | contexto |
| `docs/design/material3.md` | revisión central | 565 | contexto |
| `docs/development/setup-bazzite.md` | revisión central | 233 | contexto |
| `docs/diagnostics.md` | revisión central | 79 | contexto |
| `docs/edge-lab-benchmarks.md` | revisión central | 148 | contexto |
| `docs/edge-lab-results.md` | revisión central | 72 | contexto |
| `docs/edge-lab.md` | revisión central | 205 | contexto |
| `docs/fixtures-licenses.md` | revisión central | 108 | contexto |
| `docs/install/linux.md` | revisión central | 185 | contexto |
| `docs/install/windows-macos.md` | revisión central | 93 | contexto |
| `docs/licenses/models.md` | revisión central | 213 | contexto |
| `docs/models.md` | revisión central | 131 | contexto |
| `docs/packaging/appimage-flatpak.md` | revisión central | 220 | contexto |
| `docs/packaging/tauri-plan.md` | revisión central | 137 | contexto |
| `docs/privacy/elevenlabs.md` | revisión central | 76 | contexto |
| `docs/privacy/openai.md` | revisión central | 82 | contexto |
| `docs/quality-profiles.md` | revisión central | 101 | contexto |
| `docs/release.md` | revisión central | 69 | contexto |
| `docs/research/arm-linux-dependencies.md` | revisión central | 304 | contexto |
| `docs/research/voice-models.md` | revisión central | 244 | contexto |
| `docs/robustness.md` | revisión central | 89 | contexto |
| `docs/security/pre-release-audit.md` | revisión central | 139 | contexto |
| `docs/sherpa-onnx-asr.md` | revisión central | 71 | contexto |
| `docs/troubleshooting.md` | revisión central | 147 | contexto |
| `docs/web-quality.md` | revisión central | 103 | contexto |
| `docs/whisper-cpp.md` | revisión central | 123 | contexto |
| `migrations/env.py` | informe_persistence_jobs | 65 | superficial — solo líneas 21-59 (ejecución de migraciones, transacción, conexión inyectada) |
| `migrations/script.py.mako` | informe_persistence_jobs | 27 | omitido — no revisado en esta pasada (plantilla de nuevas revisiones) |
| `migrations/versions/0001_initial_schema.py` | informe_persistence_jobs | 318 | superficial — solo búsqueda de operaciones op.* (318 líneas sin leer) |
| `migrations/versions/0002_asr_checkpoints.py` | informe_persistence_jobs | 94 | superficial — solo búsqueda de operaciones op.* y cabecera de revisión |
| `migrations/versions/0003_job_selections.py` | informe_persistence_jobs | 44 | superficial — solo búsqueda de operaciones op.* |
| `migrations/versions/0004_segment_editing.py` | informe_persistence_jobs | 63 | superficial — solo búsqueda de op.* (migración con backup de tabla words y DROP TABLE) |
| `migrations/versions/0005_job_diarization.py` | informe_persistence_jobs | 41 | superficial — solo búsqueda de op.* (drop_column en batch_alter_table) |
| `migrations/versions/0006_segment_quality.py` | informe_persistence_jobs | 32 | superficial — solo búsqueda de op.* (drop_column sin batch en downgrade) |
| `migrations/versions/0007_project_glossary.py` | informe_persistence_jobs | 54 | superficial — solo búsqueda de op.* (drop_column en downgrade) |
| `migrations/versions/0008_job_stage_prompt.py` | informe_persistence_jobs | 63 | superficial — solo búsqueda de op.* (backfill con op.execute y drop_column) |
| `migrations/versions/0009_synthesis.py` | informe_persistence_jobs | 100 | superficial — solo búsqueda de operaciones op.* |
| `migrations/versions/0010_synthesis_request_hash.py` | informe_persistence_jobs | 72 | superficial — solo líneas de backfill y downgrade (hash en Python dentro de la migración) |
| `packaging/appimage/AppRun` | informe_quality | 8 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `packaging/appimage/build.sh` | informe_quality | 81 | superficial |
| `packaging/common/smoke.sh` | informe_quality | 109 | superficial |
| `packaging/common/v.desktop` | informe_quality | 10 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `packaging/common/v.svg` | informe_quality | 4 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `packaging/flatpak/build.sh` | informe_quality | 53 | superficial |
| `packaging/flatpak/io.github.marshallgomez1103.v.metainfo.xml` | informe_quality | 16 | superficial |
| `packaging/flatpak/io.github.marshallgomez1103.v.yml` | informe_quality | 31 | profunda |
| `packaging/icons/voz.ico` | informe_quality | 1 | omitido — binario; solo tamaño en la lista |
| `packaging/icons/voz.png` | informe_quality | 9 | omitido — binario; solo tamaño en la lista |
| `packaging/icons/voz.svg` | informe_quality | 4 | omitido — no leído en esta pasada (activo estático o de plataforma sin lógica) |
| `pyproject.toml` | informe_quality | 122 | profunda |
| `scripts/audit-secrets.sh` | informe_quality | 160 | superficial |
| `scripts/benchmark-checkpoints.py` | informe_quality | 699 | superficial |
| `scripts/benchmark-diarization.py` | informe_quality | 466 | superficial |
| `scripts/capture-screenshots.mjs` | informe_quality | 425 | superficial |
| `scripts/capture-screenshots.sh` | informe_quality | 199 | superficial |
| `scripts/check-install.sh` | informe_quality | 84 | profunda |
| `scripts/check-reproducible-build.sh` | informe_quality | 54 | profunda |
| `scripts/check-web-budget.py` | informe_quality | 174 | superficial |
| `scripts/checksums.sh` | informe_quality | 19 | superficial |
| `scripts/repro-segment-rows.mjs` | informe_quality | 161 | superficial |
| `scripts/seed_segment_rows.py` | informe_quality | 89 | superficial |
| `src/voz/__init__.py` | informe_interfaces | 3 | profunda |
| `src/voz/application/__init__.py` | informe_application | 1 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/admission.py` | informe_persistence_jobs | 32 | profunda |
| `src/voz/application/asr_device_selection.py` | informe_application | 90 | profunda |
| `src/voz/application/assign_speakers.py` | informe_application | 183 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/chunked_transcription.py` | informe_application | 238 | profunda |
| `src/voz/application/compatible_audio.py` | informe_application | 364 | profunda |
| `src/voz/application/compute_slot.py` | informe_persistence_jobs | 108 | profunda |
| `src/voz/application/create_transcription_job.py` | informe_application | 314 | profunda |
| `src/voz/application/diarization_cleanup.py` | informe_application | 82 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/diarization_reconcile.py` | informe_application | 103 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/edge_lab.py` | informe_application | 248 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/edit_segment.py` | informe_application | 49 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/estimate_cloud_cost.py` | informe_application | 101 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/evaluation.py` | informe_application | 98 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/__init__.py` | informe_application | 23 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/filenames.py` | informe_application | 42 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/grouping.py` | informe_application | 38 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/json_canonical.py` | informe_application | 241 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/markdown.py` | informe_application | 75 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/port.py` | informe_application | 64 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/service.py` | informe_application | 128 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/srt.py` | informe_application | 32 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/text.py` | informe_application | 61 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/timestamps.py` | informe_application | 21 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/export/vtt.py` | informe_application | 32 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/get_transcription_options.py` | informe_application | 195 | profunda |
| `src/voz/application/hardware_recommendation.py` | informe_application | 66 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/import_custom_model.py` | informe_application | 112 | profunda |
| `src/voz/application/import_external_model.py` | informe_application | 111 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/import_media.py` | informe_application | 203 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/job_runner.py` | informe_persistence_jobs | 819 | profunda |
| `src/voz/application/lab_comparison.py` | informe_application | 234 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/library.py` | informe_application | 47 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/model_keys.py` | informe_application | 24 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/model_manager.py` | informe_application | 324 | profunda |
| `src/voz/application/model_tasks.py` | informe_application | 423 | profunda |
| `src/voz/application/normalize_media.py` | informe_application | 83 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/__init__.py` | informe_application | 127 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/alignment.py` | informe_application | 50 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/cloud_providers.py` | informe_application | 12 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/compatible_audio.py` | informe_application | 71 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/compatible_endpoints.py` | informe_application | 207 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/custom_model_upload.py` | informe_application | 26 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/custom_models.py` | informe_application | 99 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/desktop_shortcut.py` | informe_application | 43 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/diarization.py` | informe_application | 162 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/diarization_availability.py` | informe_application | 25 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/disk_space.py` | informe_application | 73 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/external_models.py` | informe_application | 56 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/inference_audio.py` | informe_application | 48 | profunda |
| `src/voz/application/ports/library.py` | informe_application | 60 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/media_normalization.py` | informe_application | 118 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/media_probe.py` | informe_application | 126 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/media_storage.py` | informe_application | 93 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/model_installation.py` | informe_application | 173 | profunda |
| `src/voz/application/ports/project_deletion.py` | informe_application | 27 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/project_glossary.py` | informe_application | 22 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/provider_secrets.py` | informe_application | 35 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/repositories.py` | informe_application | 263 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/speech_synthesis.py` | informe_application | 205 | profunda |
| `src/voz/application/ports/synthesis_audio_storage.py` | informe_application | 69 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/synthesis_repositories.py` | informe_application | 65 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/transcription.py` | informe_application | 287 | profunda |
| `src/voz/application/ports/transcription_checkpoint.py` | informe_application | 139 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/ports/transcription_job_selection.py` | informe_application | 92 | profunda |
| `src/voz/application/ports/transcription_options.py` | informe_application | 43 | profunda |
| `src/voz/application/ports/waveform.py` | informe_application | 68 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/prepare_inference_audio.py` | informe_application | 56 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/progress_throttle.py` | informe_persistence_jobs | 29 | profunda |
| `src/voz/application/project_glossary.py` | informe_application | 75 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/projects.py` | informe_application | 141 | profunda |
| `src/voz/application/quality_flags.py` | informe_application | 145 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/quality_profiles.py` | informe_application | 170 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/recoverable_transcription.py` | informe_application | 317 | profunda |
| `src/voz/application/rediarize.py` | informe_application | 129 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/resource_requirements.py` | informe_application | 76 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/speaker_matching.py` | informe_application | 88 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/speakers.py` | informe_application | 180 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/__init__.py` | informe_application | 31 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/cancel_synthesis_job.py` | informe_application | 58 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/create_synthesis_job.py` | informe_application | 222 | profunda |
| `src/voz/application/synthesis/delete_synthesis_result.py` | informe_application | 50 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/errors.py` | informe_application | 31 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/list_synthesis_history.py` | informe_application | 51 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/synthesis/runner.py` | informe_persistence_jobs | 363 | profunda |
| `src/voz/application/synthesis_provider_registry.py` | informe_application | 103 | profunda |
| `src/voz/application/text_chunking.py` | informe_application | 236 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/transcription_provider_registry.py` | informe_application | 103 | profunda |
| `src/voz/application/tts_benchmark_metrics.py` | informe_application | 46 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/waveform_peaks.py` | informe_application | 57 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/whisper_cpp_fallback.py` | informe_application | 59 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/application/word_speakers.py` | informe_application | 62 | superficial — solo cabecera, imports, definiciones y usos (grep); sin lectura del cuerpo |
| `src/voz/bootstrap.py` | informe_interfaces | 910 | profunda |
| `src/voz/domain/__init__.py` | informe_domain | 1 | profunda |
| `src/voz/domain/entities/__init__.py` | informe_domain | 53 | profunda |
| `src/voz/domain/entities/_validation.py` | informe_domain | 43 | profunda |
| `src/voz/domain/entities/media_asset.py` | informe_domain | 87 | profunda |
| `src/voz/domain/entities/model_descriptor.py` | informe_domain | 156 | profunda |
| `src/voz/domain/entities/processing_profile.py` | informe_domain | 64 | profunda |
| `src/voz/domain/entities/project.py` | informe_domain | 34 | profunda |
| `src/voz/domain/entities/quality_profile.py` | informe_domain | 147 | profunda |
| `src/voz/domain/entities/segment.py` | informe_domain | 115 | profunda |
| `src/voz/domain/entities/speaker.py` | informe_domain | 106 | profunda |
| `src/voz/domain/entities/speaker_turn.py` | informe_domain | 56 | profunda |
| `src/voz/domain/entities/synthesis_job.py` | informe_domain | 204 | profunda |
| `src/voz/domain/entities/synthesis_request.py` | informe_domain | 84 | profunda |
| `src/voz/domain/entities/synthesized_audio.py` | informe_domain | 54 | profunda |
| `src/voz/domain/entities/transcript.py` | informe_domain | 51 | profunda |
| `src/voz/domain/entities/transcription_job.py` | informe_domain | 349 | profunda |
| `src/voz/domain/entities/voice.py` | informe_domain | 38 | profunda |
| `src/voz/domain/entities/word.py` | informe_domain | 39 | profunda |
| `src/voz/domain/filename_safety.py` | informe_domain | 19 | profunda |
| `src/voz/infrastructure/__init__.py` | informe_interfaces | 1 | profunda |
| `src/voz/infrastructure/_payload.py` | informe_persistence_jobs | 11 | profunda |
| `src/voz/infrastructure/artifact_download.py` | informe_tts_cloud | 190 | profunda |
| `src/voz/infrastructure/asr/__init__.py` | informe_speech | 15 | superficial — reexportaciones; solo cabecera |
| `src/voz/infrastructure/asr/catalog.py` | informe_speech | 226 | superficial — descriptores y catálogo; cabecera y funciones públicas, sin leer cada entrada |
| `src/voz/infrastructure/asr/faster_whisper.py` | informe_speech | 563 | profunda |
| `src/voz/infrastructure/asr/hardware.py` | informe_speech | 80 | profunda |
| `src/voz/infrastructure/asr/options.py` | informe_speech | 92 | superficial — solo el probe final; registro de modelos no leído |
| `src/voz/infrastructure/asr/runtime_cache.py` | informe_speech | 84 | profunda |
| `src/voz/infrastructure/asr/sherpa_onnx.py` | informe_speech | 326 | profunda |
| `src/voz/infrastructure/asr/sherpa_onnx_options.py` | informe_speech | 149 | superficial — probe leído; resolución de ficheros solo por cabecera |
| `src/voz/infrastructure/asr/sherpa_onnx_worker.py` | informe_speech | 220 | profunda |
| `src/voz/infrastructure/asr/system_resources.py` | informe_speech | 162 | superficial — lectura de GPU; memoria macOS y Windows solo por cabecera |
| `src/voz/infrastructure/asr/whisper_cpp.py` | informe_speech | 444 | profunda |
| `src/voz/infrastructure/asr/whisper_cpp_catalog.py` | informe_speech | 129 | superficial — constantes y catálogo; entradas no leídas una a una |
| `src/voz/infrastructure/asr/whisper_cpp_options.py` | informe_speech | 80 | superficial — probe con caché leído; resto por cabecera |
| `src/voz/infrastructure/audio/ffmpeg.py` | informe_speech | 583 | profunda |
| `src/voz/infrastructure/audio/ffmpeg_tools.py` | informe_speech | 223 | profunda |
| `src/voz/infrastructure/audio/ffprobe.py` | informe_speech | 307 | superficial — _run y carga de decodificadores leídos; parseo de streams solo por cabecera |
| `src/voz/infrastructure/audio/media_args.py` | informe_speech | 119 | profunda |
| `src/voz/infrastructure/audio/waveform_peaks.py` | informe_speech | 298 | profunda |
| `src/voz/infrastructure/buzz_cache.py` | informe_speech | 152 | profunda |
| `src/voz/infrastructure/cloud/__init__.py` | informe_tts_cloud | 1 | profunda |
| `src/voz/infrastructure/cloud/_errors.py` | informe_tts_cloud | 14 | profunda |
| `src/voz/infrastructure/cloud/catalog.py` | informe_tts_cloud | 97 | profunda |
| `src/voz/infrastructure/cloud/compatible_store.py` | informe_tts_cloud | 129 | profunda |
| `src/voz/infrastructure/cloud/elevenlabs_mapping.py` | informe_tts_cloud | 178 | superficial — solo cabecera, estructura y funciones públicas; mapeo de palabras y segmentos (líneas 80-178) no leído en detalle |
| `src/voz/infrastructure/cloud/elevenlabs_pricing.py` | informe_tts_cloud | 48 | profunda |
| `src/voz/infrastructure/cloud/elevenlabs_scribe.py` | informe_tts_cloud | 291 | profunda |
| `src/voz/infrastructure/cloud/elevenlabs_transport.py` | informe_tts_cloud | 173 | profunda |
| `src/voz/infrastructure/cloud/openai_compatible.py` | informe_tts_cloud | 514 | profunda |
| `src/voz/infrastructure/cloud/openai_fake.py` | informe_tts_cloud | 58 | profunda |
| `src/voz/infrastructure/cloud/openai_limits.py` | informe_tts_cloud | 98 | profunda |
| `src/voz/infrastructure/cloud/openai_transcription.py` | informe_tts_cloud | 423 | profunda |
| `src/voz/infrastructure/cloud/openai_transport.py` | informe_tts_cloud | 168 | profunda |
| `src/voz/infrastructure/cloud/provider_info.py` | informe_tts_cloud | 14 | profunda |
| `src/voz/infrastructure/constrained_process.py` | informe_persistence_jobs | 258 | profunda |
| `src/voz/infrastructure/custom_model_detection.py` | informe_tts_cloud | 118 | superficial — detect_download leído; detect_repository y _tts_families solo por grep de definiciones |
| `src/voz/infrastructure/custom_model_upload.py` | informe_tts_cloud | 310 | profunda |
| `src/voz/infrastructure/custom_model_worker.py` | informe_tts_cloud | 198 | profunda |
| `src/voz/infrastructure/custom_models.py` | informe_tts_cloud | 712 | profunda |
| `src/voz/infrastructure/desktop_shortcut.py` | informe_interfaces | 393 | profunda |
| `src/voz/infrastructure/diarization/__init__.py` | informe_speech | 13 | superficial — reexportaciones |
| `src/voz/infrastructure/diarization/availability.py` | informe_speech | 37 | superficial — lógica trivial leída casi entera |
| `src/voz/infrastructure/diarization/models.py` | informe_speech | 252 | superficial — instalación y descarga (área de seguridad); solo verificación de rutas |
| `src/voz/infrastructure/diarization/sherpa.py` | informe_speech | 449 | profunda |
| `src/voz/infrastructure/diarization/worker.py` | informe_speech | 54 | profunda |
| `src/voz/infrastructure/disk_space.py` | informe_tts_cloud | 36 | profunda |
| `src/voz/infrastructure/edge_lab_tts.py` | informe_tts_cloud | 160 | profunda |
| `src/voz/infrastructure/edge_lab_worker.py` | informe_speech | 273 | profunda |
| `src/voz/infrastructure/inference_audio.py` | informe_speech | 149 | profunda |
| `src/voz/infrastructure/media_storage.py` | informe_persistence_jobs | 553 | superficial — líneas 35-134 (importación de originales); resto sin leer |
| `src/voz/infrastructure/model_registry.py` | informe_tts_cloud | 285 | superficial — catálogo de capacidades y RoutingModelStore leídos; ManagedModelCatalog (líneas 110-184) no leído |
| `src/voz/infrastructure/model_storage.py` | informe_tts_cloud | 1024 | superficial — leídos install, fetch_custom_file, _fetch, _matches, publish_custom, remove, _files_intact; no leídos ASR download/import, _commit, _load_manifest, _registered_descriptors (líneas 300-489, 560-647, 800-943) |
| `src/voz/infrastructure/paths.py` | informe_persistence_jobs | 84 | superficial — líneas 60-84 (resolución XDG); resto por definiciones |
| `src/voz/infrastructure/persistence/_rows.py` | informe_persistence_jobs | 33 | superficial — solo definiciones |
| `src/voz/infrastructure/persistence/database.py` | informe_persistence_jobs | 57 | profunda |
| `src/voz/infrastructure/persistence/library.py` | informe_persistence_jobs | 168 | superficial — solo definiciones |
| `src/voz/infrastructure/persistence/migrate.py` | informe_persistence_jobs | 140 | profunda |
| `src/voz/infrastructure/persistence/project_glossaries.py` | informe_persistence_jobs | 65 | superficial — solo definiciones |
| `src/voz/infrastructure/persistence/repositories.py` | informe_persistence_jobs | 901 | superficial — líneas 94-107, 301-316, 510-525, 813-901 (jobs, segmentos, _save); resto por definiciones |
| `src/voz/infrastructure/persistence/schema.py` | informe_persistence_jobs | 365 | superficial — líneas 173-206, 295-340 (tablas de jobs, checkpoints, síntesis) y constraints por grep |
| `src/voz/infrastructure/persistence/synthesis.py` | informe_persistence_jobs | 240 | superficial — líneas 111-240 (repositorio de síntesis); helpers 1-110 por definiciones |
| `src/voz/infrastructure/persistence/transcription_checkpoints.py` | informe_persistence_jobs | 227 | superficial — líneas 124-227 (commit atómico y lectura); helpers JSON 1-123 por definiciones |
| `src/voz/infrastructure/persistence/transcription_job_selections.py` | informe_persistence_jobs | 293 | superficial — solo definiciones |
| `src/voz/infrastructure/process_tree.py` | informe_persistence_jobs | 33 | profunda |
| `src/voz/infrastructure/safe_fs.py` | informe_persistence_jobs | 289 | superficial — cabecera, líneas 166-175 y 250-289 (eliminación de árboles); resto por definiciones |
| `src/voz/infrastructure/secrets.py` | informe_tts_cloud | 179 | profunda |
| `src/voz/infrastructure/server_token.py` | informe_interfaces | 57 | profunda |
| `src/voz/infrastructure/synthesis_storage.py` | informe_tts_cloud | 314 | superficial — write y _int16_bytes leídos; open_for_reading, delete_job y _build_wav no leídos en detalle |
| `src/voz/infrastructure/tts/__init__.py` | informe_tts_cloud | 13 | profunda |
| `src/voz/infrastructure/tts/catalog.py` | informe_tts_cloud | 259 | profunda |
| `src/voz/infrastructure/tts/fake.py` | informe_tts_cloud | 145 | superficial — cabecera y voces; resto (render/cancelación) solo por grep; no cableado en producción |
| `src/voz/infrastructure/tts/families.py` | informe_tts_cloud | 380 | profunda |
| `src/voz/infrastructure/tts/installed_models.py` | informe_tts_cloud | 43 | profunda |
| `src/voz/infrastructure/tts/model_store.py` | informe_tts_cloud | 393 | profunda |
| `src/voz/infrastructure/tts/protocol.py` | informe_tts_cloud | 264 | profunda |
| `src/voz/infrastructure/tts/sherpa_provider.py` | informe_tts_cloud | 89 | profunda |
| `src/voz/infrastructure/tts/sherpa_worker.py` | informe_tts_cloud | 127 | profunda |
| `src/voz/infrastructure/tts/subprocess_provider.py` | informe_tts_cloud | 353 | profunda |
| `src/voz/interfaces/__init__.py` | informe_interfaces | 1 | profunda |
| `src/voz/interfaces/api/__init__.py` | informe_interfaces | 1 | profunda |
| `src/voz/interfaces/api/custom_model_uploads.py` | informe_interfaces | 135 | profunda |
| `src/voz/interfaces/api/desktop_shortcut.py` | informe_interfaces | 89 | profunda |
| `src/voz/interfaces/api/errors.py` | informe_interfaces | 18 | profunda |
| `src/voz/interfaces/api/export.py` | informe_interfaces | 63 | profunda |
| `src/voz/interfaces/api/health.py` | informe_interfaces | 23 | profunda |
| `src/voz/interfaces/api/host_guard.py` | informe_interfaces | 72 | profunda |
| `src/voz/interfaces/api/job_events.py` | informe_interfaces | 114 | profunda |
| `src/voz/interfaces/api/job_views.py` | informe_interfaces | 72 | profunda |
| `src/voz/interfaces/api/jobs.py` | informe_interfaces | 401 | profunda |
| `src/voz/interfaces/api/library.py` | informe_interfaces | 55 | superficial |
| `src/voz/interfaces/api/media.py` | informe_interfaces | 255 | profunda |
| `src/voz/interfaces/api/media_stream.py` | informe_interfaces | 79 | profunda |
| `src/voz/interfaces/api/model_tasks.py` | informe_interfaces | 110 | profunda |
| `src/voz/interfaces/api/models.py` | informe_interfaces | 114 | superficial |
| `src/voz/interfaces/api/openai_compat.py` | informe_interfaces | 441 | profunda |
| `src/voz/interfaces/api/projects.py` | informe_interfaces | 229 | superficial |
| `src/voz/interfaces/api/providers.py` | informe_interfaces | 351 | profunda |
| `src/voz/interfaces/api/quality_profiles.py` | informe_interfaces | 44 | profunda |
| `src/voz/interfaces/api/security_headers.py` | informe_interfaces | 46 | profunda |
| `src/voz/interfaces/api/segments.py` | informe_interfaces | 98 | profunda |
| `src/voz/interfaces/api/server_auth.py` | informe_interfaces | 147 | profunda |
| `src/voz/interfaces/api/shutdown.py` | informe_interfaces | 56 | profunda |
| `src/voz/interfaces/api/speakers.py` | informe_interfaces | 138 | profunda |
| `src/voz/interfaces/api/synthesis.py` | informe_interfaces | 472 | profunda |
| `src/voz/interfaces/api/transcription_options.py` | informe_interfaces | 33 | profunda |
| `src/voz/interfaces/api/waveform.py` | informe_interfaces | 49 | profunda |
| `src/voz/interfaces/cli/__init__.py` | informe_interfaces | 1 | profunda |
| `src/voz/interfaces/cli/bench.py` | informe_interfaces | 679 | superficial |
| `src/voz/interfaces/cli/diagnostics_bundle.py` | informe_interfaces | 176 | profunda |
| `src/voz/interfaces/cli/doctor.py` | informe_interfaces | 356 | superficial |
| `src/voz/interfaces/cli/lab.py` | informe_interfaces | 87 | superficial |
| `src/voz/interfaces/cli/lab_results.py` | informe_interfaces | 41 | superficial |
| `src/voz/interfaces/cli/main.py` | informe_interfaces | 428 | profunda |
| `src/voz/static/assets/AudioPlayer-Bu0_kVhD.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/AudioPlayer-CX3rvNFm.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/CloudBadge-BAnuMqvc.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/CloudBadge-Bt_bDSIZ.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ExportDialog-THDQkTqS.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ExportDialog-nou54xqH.js` | informe_interfaces | 3 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/Hint-CYmjQG8O.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/Hint-D88x-jGM.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexMono-Regular-Latin1-DYPusg7z.woff2` | informe_interfaces | 72 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexMono-Regular-Pi-DnS9d3y-.woff2` | informe_interfaces | 50 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexMono-SemiBold-Latin1-ChfWfxA6.woff2` | informe_interfaces | 70 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexMono-SemiBold-Pi-ITbxIV3a.woff2` | informe_interfaces | 58 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Italic-Latin1-D6ilVweT.woff2` | informe_interfaces | 89 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Italic-Pi-COJ9AKmU.woff2` | informe_interfaces | 32 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Light-Latin1-inJE14c2.woff2` | informe_interfaces | 88 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Light-Pi-Wq6RJxSB.woff2` | informe_interfaces | 19 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Regular-Latin1-BUjEsRx4.woff2` | informe_interfaces | 94 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-Regular-Pi-CkmElvWW.woff2` | informe_interfaces | 40 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-SemiBold-Latin1-CIhZjzyK.woff2` | informe_interfaces | 90 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/IBMPlexSans-SemiBold-Pi-CG8jxtIB.woff2` | informe_interfaces | 40 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/Modal-BaLwW5YN.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ModelManager-Bcj-GJx1.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ModelManager-DfS1ogiY.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ProvidersSettings-Bh3chZHq.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/ProvidersSettings-D4-zcybj.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/SelectItem-hT46X82l.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/SpeakWorkspace-CCz6xlz3.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/SpeakWorkspace-CqLYT7jm.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/TechTerms-CL2K81A_.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/TextInput-BbdYMjrB.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/Workspace-BAn34mNl.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/Workspace-C-D7q9J6.js` | informe_interfaces | 2 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/bucket-15-CvhFrBgo.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/errors-BIKxfg37.js` | informe_interfaces | 28 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/events-Dvd0VF5P.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/formatBytes-CDeSavCc.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/index-BDYYDYOF.js` | informe_interfaces | 13 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/index-Cf681eT-.css` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/m3-y9ruFiH9.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/roboto-flex-latin-wght-normal-n-dP9qr2.woff2` | informe_interfaces | 117 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/assets/rolldown-runtime-CbXtAM7H.js` | informe_interfaces | 1 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/favicon.svg` | informe_interfaces | 4 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/icon-192.png` | informe_interfaces | 10 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/icon-512.png` | informe_interfaces | 40 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/icon-maskable-512.png` | informe_interfaces | 40 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/index.html` | informe_interfaces | 35 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/licenses/IBM-Plex-OFL.txt` | informe_interfaces | 93 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/licenses/Roboto-Flex-OFL.txt` | informe_interfaces | 93 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/licenses/Third-party-JavaScript.txt` | informe_interfaces | 4418 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `src/voz/static/manifest.webmanifest` | informe_interfaces | 15 | superficial — bundle compilado: solo se verifica cómo se sirve (bootstrap.py:896-901) |
| `start-v-linux.sh` | informe_quality | 3 | profunda |
| `tests/conftest.py` | informe_quality | 119 | profunda |
| `tests/contract/elevenlabs_contract_fake.py` | informe_quality | 50 | superficial |
| `tests/contract/openai_compatible_fake.py` | informe_quality | 243 | superficial |
| `tests/contract/test_media_probe_port.py` | informe_quality | 63 | superficial |
| `tests/contract/test_openai_compatible.py` | informe_quality | 716 | superficial |
| `tests/contract/test_speech_synthesis_provider.py` | informe_quality | 271 | superficial |
| `tests/contract/test_transcription_provider.py` | informe_quality | 439 | superficial |
| `tests/e2e/test_cli_shutdown.py` | informe_quality | 70 | superficial |
| `tests/e2e/test_cli_smoke.py` | informe_quality | 65 | superficial |
| `tests/e2e/test_restart_during_job.py` | informe_quality | 289 | superficial |
| `tests/e2e/test_workspace_flow.py` | informe_quality | 346 | superficial |
| `tests/fixtures/README.md` | informe_quality | 40 | profunda |
| `tests/fixtures/asr/fake_sherpa_onnx_worker.py` | informe_quality | 68 | superficial |
| `tests/fixtures/media/synthetic-tone.m4a` | informe_quality | 5 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/media/synthetic-tone.mp3` | informe_quality | 10 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/media/synthetic-tone.ogg` | informe_quality | 15 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/media/synthetic-tone.opus` | informe_quality | 1 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/media/synthetic-tone.wav` | informe_quality | 141 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/media/synthetic-tone.webm` | informe_quality | 1 | omitido — binario; solo tamaño en la lista |
| `tests/fixtures/tts/fake_tts_worker.py` | informe_quality | 94 | superficial |
| `tests/fixtures/whisper_cpp/fake_whisper_cli.py` | informe_quality | 61 | superficial |
| `tests/fixtures/whisper_cpp/real_ojf_v1.9.4.json` | informe_quality | 548 | superficial |
| `tests/integration/application/test_assign_speakers.py` | informe_quality | 181 | superficial |
| `tests/integration/application/test_faster_whisper_real_opt_in.py` | informe_quality | 62 | profunda |
| `tests/integration/application/test_import_media_sqlite.py` | informe_quality | 215 | superficial |
| `tests/integration/application/test_job_runner.py` | informe_quality | 1083 | superficial |
| `tests/integration/application/test_job_runner_cancel_races.py` | informe_quality | 155 | profunda |
| `tests/integration/application/test_job_runner_diarization.py` | informe_quality | 677 | superficial |
| `tests/integration/application/test_job_runner_provider_speakers.py` | informe_quality | 343 | superficial |
| `tests/integration/application/test_job_runner_shutdown.py` | informe_quality | 177 | superficial |
| `tests/integration/application/test_local_asr_pipeline.py` | informe_quality | 130 | superficial |
| `tests/integration/application/test_normalize_imported_media.py` | informe_quality | 95 | superficial |
| `tests/integration/application/test_recoverable_transcription.py` | informe_quality | 570 | superficial |
| `tests/integration/application/test_rediarize.py` | informe_quality | 457 | superficial |
| `tests/integration/application/test_synthesis_runner.py` | informe_quality | 583 | superficial |
| `tests/integration/audio/test_ffmpeg_media_normalizer_integration.py` | informe_quality | 563 | superficial |
| `tests/integration/audio/test_ffmpeg_waveform_peaks_integration.py` | informe_quality | 160 | superficial |
| `tests/integration/audio/test_ffprobe_media_probe.py` | informe_quality | 55 | superficial |
| `tests/integration/audio/test_portable_backend.py` | informe_quality | 108 | superficial |
| `tests/integration/media/test_media_fixtures.py` | informe_quality | 129 | superficial |
| `tests/integration/persistence/test_atomic_writes.py` | informe_quality | 248 | superficial |
| `tests/integration/persistence/test_database.py` | informe_quality | 103 | superficial |
| `tests/integration/persistence/test_glossary_migration_0007.py` | informe_quality | 197 | superficial |
| `tests/integration/persistence/test_job_selection_diarization.py` | informe_quality | 170 | superficial |
| `tests/integration/persistence/test_job_with_selection_atomic.py` | informe_quality | 102 | superficial |
| `tests/integration/persistence/test_migration_backup.py` | informe_quality | 120 | superficial |
| `tests/integration/persistence/test_migrations.py` | informe_quality | 45 | superficial |
| `tests/integration/persistence/test_runtime_migrate.py` | informe_quality | 29 | superficial |
| `tests/integration/persistence/test_segment_quality.py` | informe_quality | 173 | superficial |
| `tests/integration/persistence/test_sqlite_job_selections.py` | informe_quality | 156 | superficial |
| `tests/integration/persistence/test_sqlite_repositories.py` | informe_quality | 523 | superficial |
| `tests/integration/persistence/test_sqlite_segment_editing.py` | informe_quality | 157 | superficial |
| `tests/integration/persistence/test_stage_prompt_migration_0008.py` | informe_quality | 168 | superficial |
| `tests/integration/persistence/test_synthesis_migration_0009.py` | informe_quality | 143 | superficial |
| `tests/integration/persistence/test_synthesis_migration_0010.py` | informe_quality | 115 | superficial |
| `tests/integration/persistence/test_synthesis_repositories.py` | informe_quality | 443 | superficial |
| `tests/integration/test_custom_models_default_wiring.py` | informe_quality | 453 | superficial |
| `tests/integration/test_desktop_shortcut_api.py` | informe_quality | 211 | superficial |
| `tests/integration/test_export_api.py` | informe_quality | 205 | superficial |
| `tests/integration/test_health_api.py` | informe_quality | 95 | superficial |
| `tests/integration/test_host_guard.py` | informe_quality | 110 | superficial |
| `tests/integration/test_job_events_api.py` | informe_quality | 340 | superficial |
| `tests/integration/test_jobs_api.py` | informe_quality | 661 | superficial |
| `tests/integration/test_jobs_diarization_api.py` | informe_quality | 449 | superficial |
| `tests/integration/test_jobs_memory_guard_api.py` | informe_quality | 61 | superficial |
| `tests/integration/test_library_projects_api.py` | informe_quality | 446 | superficial |
| `tests/integration/test_media_stream_api.py` | informe_quality | 208 | superficial |
| `tests/integration/test_media_upload_api.py` | informe_quality | 435 | superficial |
| `tests/integration/test_model_tasks_api.py` | informe_quality | 420 | superficial |
| `tests/integration/test_models_api.py` | informe_quality | 283 | superficial |
| `tests/integration/test_openai_compat_default_wiring.py` | informe_quality | 150 | superficial |
| `tests/integration/test_project_glossary_api.py` | informe_quality | 181 | superficial |
| `tests/integration/test_projects_api.py` | informe_quality | 156 | superficial |
| `tests/integration/test_providers_api.py` | informe_quality | 434 | superficial |
| `tests/integration/test_security_headers_default_wiring.py` | informe_quality | 27 | superficial |
| `tests/integration/test_segments_api.py` | informe_quality | 230 | superficial |
| `tests/integration/test_server_auth_wiring.py` | informe_quality | 57 | superficial |
| `tests/integration/test_sherpa_asr_default_wiring.py` | informe_quality | 121 | superficial |
| `tests/integration/test_shutdown_api.py` | informe_quality | 72 | superficial |
| `tests/integration/test_speakers_api.py` | informe_quality | 336 | superficial |
| `tests/integration/test_synthesis_api.py` | informe_quality | 332 | superficial |
| `tests/integration/test_transcription_options_api.py` | informe_quality | 118 | superficial |
| `tests/integration/test_tts_default_wiring.py` | informe_quality | 163 | superficial |
| `tests/integration/test_tts_models_api.py` | informe_quality | 258 | superficial |
| `tests/integration/test_waveform_api.py` | informe_quality | 168 | superficial |
| `tests/packaging/test_appimage_branding.py` | informe_quality | 195 | superficial |
| `tests/packaging/test_flatpak_branding.py` | informe_quality | 158 | superficial |
| `tests/packaging/test_packaging_smoke.py` | informe_quality | 197 | superficial |
| `tests/packaging/test_portable_launchers.py` | informe_quality | 122 | superficial |
| `tests/packaging/test_version_consistency.py` | informe_quality | 20 | superficial |
| `tests/packaging/test_wheel_contents.py` | informe_quality | 170 | superficial |
| `tests/unit/application/export/__init__.py` | informe_quality | 0 | superficial |
| `tests/unit/application/export/test_filenames.py` | informe_quality | 88 | superficial |
| `tests/unit/application/export/test_json_export.py` | informe_quality | 220 | superficial |
| `tests/unit/application/export/test_markdown_export.py` | informe_quality | 109 | superficial |
| `tests/unit/application/export/test_speaker_grouping.py` | informe_quality | 161 | superficial |
| `tests/unit/application/export/test_srt_vtt_export.py` | informe_quality | 93 | superficial |
| `tests/unit/application/export/test_text_export.py` | informe_quality | 90 | superficial |
| `tests/unit/application/export/test_timestamps.py` | informe_quality | 45 | superficial |
| `tests/unit/application/synthesis/conftest.py` | informe_quality | 62 | superficial |
| `tests/unit/application/synthesis/synthesis_support.py` | informe_quality | 107 | superficial |
| `tests/unit/application/synthesis/test_cancel_list_delete_synthesis.py` | informe_quality | 237 | superficial |
| `tests/unit/application/synthesis/test_create_synthesis_job.py` | informe_quality | 253 | superficial |
| `tests/unit/application/test_admission.py` | informe_quality | 418 | superficial |
| `tests/unit/application/test_asr_device_selection.py` | informe_quality | 78 | superficial |
| `tests/unit/application/test_chunked_transcription.py` | informe_quality | 157 | superficial |
| `tests/unit/application/test_compatible_audio.py` | informe_quality | 655 | superficial |
| `tests/unit/application/test_compute_slot.py` | informe_quality | 175 | superficial |
| `tests/unit/application/test_create_transcription_job.py` | informe_quality | 527 | superficial |
| `tests/unit/application/test_custom_model_staging_context.py` | informe_quality | 70 | superficial |
| `tests/unit/application/test_diarization_cleanup.py` | informe_quality | 75 | superficial |
| `tests/unit/application/test_diarization_port.py` | informe_quality | 145 | superficial |
| `tests/unit/application/test_diarization_reconcile.py` | informe_quality | 153 | superficial |
| `tests/unit/application/test_disk_space.py` | informe_quality | 139 | superficial |
| `tests/unit/application/test_edge_lab.py` | informe_quality | 127 | superficial |
| `tests/unit/application/test_edit_segment.py` | informe_quality | 102 | superficial |
| `tests/unit/application/test_estimate_cloud_cost.py` | informe_quality | 76 | superficial |
| `tests/unit/application/test_evaluation.py` | informe_quality | 68 | superficial |
| `tests/unit/application/test_get_transcription_options.py` | informe_quality | 270 | superficial |
| `tests/unit/application/test_get_waveform_peaks.py` | informe_quality | 102 | superficial |
| `tests/unit/application/test_hardware_recommendation.py` | informe_quality | 104 | superficial |
| `tests/unit/application/test_import_media.py` | informe_quality | 445 | superficial |
| `tests/unit/application/test_lab_comparison.py` | informe_quality | 248 | superficial |
| `tests/unit/application/test_library.py` | informe_quality | 10 | superficial |
| `tests/unit/application/test_model_manager.py` | informe_quality | 500 | superficial |
| `tests/unit/application/test_model_tasks.py` | informe_quality | 348 | superficial |
| `tests/unit/application/test_normalize_media.py` | informe_quality | 156 | superficial |
| `tests/unit/application/test_progress_throttle.py` | informe_quality | 13 | superficial |
| `tests/unit/application/test_project_glossary.py` | informe_quality | 100 | superficial |
| `tests/unit/application/test_projects.py` | informe_quality | 94 | superficial |
| `tests/unit/application/test_quality_flags.py` | informe_quality | 126 | superficial |
| `tests/unit/application/test_quality_profiles.py` | informe_quality | 74 | superficial |
| `tests/unit/application/test_repository_ports.py` | informe_quality | 106 | superficial |
| `tests/unit/application/test_speaker_matching.py` | informe_quality | 52 | superficial |
| `tests/unit/application/test_synthesis_provider_registry.py` | informe_quality | 70 | superficial |
| `tests/unit/application/test_text_chunking.py` | informe_quality | 256 | superficial |
| `tests/unit/application/test_transcription_provider_registry.py` | informe_quality | 171 | superficial |
| `tests/unit/application/test_tts_benchmark_metrics.py` | informe_quality | 82 | superficial |
| `tests/unit/application/test_whisper_cpp_fallback.py` | informe_quality | 58 | superficial |
| `tests/unit/application/test_word_speakers.py` | informe_quality | 87 | superficial |
| `tests/unit/application/test_word_timestamps.py` | informe_quality | 274 | superficial |
| `tests/unit/domain/test_entity_invariants.py` | informe_quality | 60 | superficial |
| `tests/unit/domain/test_filename_safety.py` | informe_quality | 40 | superficial |
| `tests/unit/domain/test_media_asset.py` | informe_quality | 116 | superficial |
| `tests/unit/domain/test_model_descriptor.py` | informe_quality | 151 | superficial |
| `tests/unit/domain/test_project.py` | informe_quality | 50 | superficial |
| `tests/unit/domain/test_quality_profile.py` | informe_quality | 75 | superficial |
| `tests/unit/domain/test_segment.py` | informe_quality | 224 | superficial |
| `tests/unit/domain/test_speaker.py` | informe_quality | 144 | superficial |
| `tests/unit/domain/test_speaker_turn.py` | informe_quality | 99 | superficial |
| `tests/unit/domain/test_synthesis_job.py` | informe_quality | 215 | superficial |
| `tests/unit/domain/test_synthesis_request.py` | informe_quality | 89 | superficial |
| `tests/unit/domain/test_synthesized_audio.py` | informe_quality | 79 | superficial |
| `tests/unit/domain/test_transcript.py` | informe_quality | 61 | superficial |
| `tests/unit/domain/test_transcription_job.py` | informe_quality | 450 | superficial |
| `tests/unit/domain/test_voice.py` | informe_quality | 30 | superficial |
| `tests/unit/domain/test_word.py` | informe_quality | 80 | superficial |
| `tests/unit/infrastructure/asr/conftest.py` | informe_quality | 11 | superficial |
| `tests/unit/infrastructure/asr/test_catalog.py` | informe_quality | 130 | superficial |
| `tests/unit/infrastructure/asr/test_cuda_preload.py` | informe_quality | 258 | superficial |
| `tests/unit/infrastructure/asr/test_faster_whisper.py` | informe_quality | 445 | superficial |
| `tests/unit/infrastructure/asr/test_faster_whisper_lifecycle.py` | informe_quality | 418 | superficial |
| `tests/unit/infrastructure/asr/test_faster_whisper_quality.py` | informe_quality | 204 | superficial |
| `tests/unit/infrastructure/asr/test_faster_whisper_words.py` | informe_quality | 241 | superficial |
| `tests/unit/infrastructure/asr/test_hardware.py` | informe_quality | 125 | superficial |
| `tests/unit/infrastructure/asr/test_nemo_transducer.py` | informe_quality | 208 | superficial |
| `tests/unit/infrastructure/asr/test_options.py` | informe_quality | 201 | superficial |
| `tests/unit/infrastructure/asr/test_sherpa_onnx.py` | informe_quality | 322 | superficial |
| `tests/unit/infrastructure/asr/test_sherpa_onnx_options.py` | informe_quality | 83 | superficial |
| `tests/unit/infrastructure/asr/test_sherpa_onnx_worker.py` | informe_quality | 124 | superficial |
| `tests/unit/infrastructure/asr/test_system_resources.py` | informe_quality | 160 | superficial |
| `tests/unit/infrastructure/asr/test_whisper_cpp.py` | informe_quality | 477 | superficial |
| `tests/unit/infrastructure/asr/test_whisper_cpp_catalog.py` | informe_quality | 108 | superficial |
| `tests/unit/infrastructure/asr/test_whisper_cpp_options.py` | informe_quality | 48 | superficial |
| `tests/unit/infrastructure/asr/test_whisper_cpp_real_format.py` | informe_quality | 72 | superficial |
| `tests/unit/infrastructure/audio/test_ffmpeg_tools.py` | informe_quality | 175 | superficial |
| `tests/unit/infrastructure/audio/test_ffprobe.py` | informe_quality | 238 | superficial |
| `tests/unit/infrastructure/audio/test_ffprobe_fuzz.py` | informe_quality | 362 | superficial |
| `tests/unit/infrastructure/audio/test_waveform_peaks_calc.py` | informe_quality | 112 | superficial |
| `tests/unit/infrastructure/cloud/test_cloud_errors.py` | informe_quality | 13 | superficial |
| `tests/unit/infrastructure/cloud/test_elevenlabs_isolation.py` | informe_quality | 63 | superficial |
| `tests/unit/infrastructure/cloud/test_elevenlabs_pricing.py` | informe_quality | 96 | superficial |
| `tests/unit/infrastructure/cloud/test_elevenlabs_scribe.py` | informe_quality | 678 | superficial |
| `tests/unit/infrastructure/cloud/test_provider_info.py` | informe_quality | 32 | superficial |
| `tests/unit/infrastructure/diarization/test_availability.py` | informe_quality | 39 | superficial |
| `tests/unit/infrastructure/diarization/test_diarization_models.py` | informe_quality | 263 | superficial |
| `tests/unit/infrastructure/diarization/test_sherpa_provider.py` | informe_quality | 528 | superficial |
| `tests/unit/infrastructure/persistence/test_persistence_rows.py` | informe_quality | 53 | superficial |
| `tests/unit/infrastructure/persistence/test_repositories.py` | informe_quality | 329 | superficial |
| `tests/unit/infrastructure/test_atomic_file_writes.py` | informe_quality | 269 | superficial |
| `tests/unit/infrastructure/test_buzz_cache.py` | informe_quality | 247 | superficial |
| `tests/unit/infrastructure/test_buzz_import.py` | informe_quality | 197 | superficial |
| `tests/unit/infrastructure/test_constrained_process.py` | informe_quality | 277 | superficial |
| `tests/unit/infrastructure/test_custom_model_detection.py` | informe_quality | 61 | superficial |
| `tests/unit/infrastructure/test_custom_model_upload.py` | informe_quality | 315 | superficial |
| `tests/unit/infrastructure/test_custom_models.py` | informe_quality | 1515 | superficial |
| `tests/unit/infrastructure/test_desktop_shortcut.py` | informe_quality | 512 | superficial |
| `tests/unit/infrastructure/test_edge_lab_tts.py` | informe_quality | 274 | superficial |
| `tests/unit/infrastructure/test_edge_lab_worker.py` | informe_quality | 269 | superficial |
| `tests/unit/infrastructure/test_inference_audio.py` | informe_quality | 83 | superficial |
| `tests/unit/infrastructure/test_infrastructure_payload.py` | informe_quality | 15 | superficial |
| `tests/unit/infrastructure/test_media_storage.py` | informe_quality | 1006 | superficial |
| `tests/unit/infrastructure/test_model_download.py` | informe_quality | 745 | superficial |
| `tests/unit/infrastructure/test_model_registry.py` | informe_quality | 305 | superficial |
| `tests/unit/infrastructure/test_model_storage.py` | informe_quality | 266 | superficial |
| `tests/unit/infrastructure/test_openai_cloud_opt_in.py` | informe_quality | 155 | superficial |
| `tests/unit/infrastructure/test_openai_transcription.py` | informe_quality | 541 | superficial |
| `tests/unit/infrastructure/test_process_tree.py` | informe_quality | 55 | superficial |
| `tests/unit/infrastructure/test_safe_fs.py` | informe_quality | 302 | superficial |
| `tests/unit/infrastructure/test_secrets.py` | informe_quality | 143 | superficial |
| `tests/unit/infrastructure/test_server_token.py` | informe_quality | 73 | superficial |
| `tests/unit/infrastructure/test_shutil_disk_space.py` | informe_quality | 44 | superficial |
| `tests/unit/infrastructure/test_synthesis_storage.py` | informe_quality | 400 | superficial |
| `tests/unit/infrastructure/test_tts_fake.py` | informe_quality | 72 | superficial |
| `tests/unit/infrastructure/tts/test_families.py` | informe_quality | 408 | superficial |
| `tests/unit/infrastructure/tts/test_protocol.py` | informe_quality | 208 | superficial |
| `tests/unit/infrastructure/tts/test_sherpa_worker.py` | informe_quality | 352 | superficial |
| `tests/unit/infrastructure/tts/test_subprocess_provider.py` | informe_quality | 374 | superficial |
| `tests/unit/infrastructure/tts/test_tts_catalog.py` | informe_quality | 142 | superficial |
| `tests/unit/infrastructure/tts/test_tts_model_store.py` | informe_quality | 416 | superficial |
| `tests/unit/test_api_errors.py` | informe_quality | 25 | superficial |
| `tests/unit/test_asr_bootstrap.py` | informe_quality | 160 | superficial |
| `tests/unit/test_asr_runtime_cache.py` | informe_quality | 227 | superficial |
| `tests/unit/test_bench_cli.py` | informe_quality | 318 | superficial |
| `tests/unit/test_benchmark_diarization.py` | informe_quality | 168 | superficial |
| `tests/unit/test_checkpoint_benchmark.py` | informe_quality | 327 | superficial |
| `tests/unit/test_cli.py` | informe_quality | 324 | superficial |
| `tests/unit/test_cli_server_auth.py` | informe_quality | 135 | superficial |
| `tests/unit/test_diagnostics_bundle.py` | informe_quality | 143 | superficial |
| `tests/unit/test_doctor.py` | informe_quality | 490 | superficial |
| `tests/unit/test_job_views.py` | informe_quality | 68 | superficial |
| `tests/unit/test_lab_cli.py` | informe_quality | 170 | superficial |
| `tests/unit/test_lab_results_cli.py` | informe_quality | 160 | superficial |
| `tests/unit/test_openai_compat_api.py` | informe_quality | 691 | superficial |
| `tests/unit/test_security_headers.py` | informe_quality | 195 | superficial |
| `tests/unit/test_server_auth.py` | informe_quality | 407 | superficial |
| `tests/unit/test_server_readiness_redirect.py` | informe_quality | 74 | superficial |
| `tests/unit/test_suite_portability.py` | informe_quality | 14 | superficial |
| `tests/unit/test_test_isolation.py` | informe_quality | 26 | superficial |
| `tests/unit/test_web_budget.py` | informe_quality | 151 | superficial |
| `tests/unit/test_xdg_paths.py` | informe_quality | 89 | superficial |
| `uv.lock` | informe_quality | 1092 | superficial — solo cabecera y conteo de paquetes |
