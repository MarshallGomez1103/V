# Changelog

Todos los cambios relevantes de VOZ se documentan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto adopta
[versionado semántico](https://semver.org/lang/es/) con las reglas de
[docs/release.md](docs/release.md). Mientras la versión sea `0.x`, un cambio
menor puede romper compatibilidad.

## [Unreleased]

Todavía no existe ninguna release publicada: la versión del árbol es `0.1.0`
(`pyproject.toml` y `voz.__version__`) y nadie ha etiquetado ni publicado
artefactos. Lo siguiente es lo que ya existe en el repositorio.

### Añadido

- CLI `voz` (Typer): arranca el servidor local en `127.0.0.1:8765` y abre el
  navegador salvo `--no-browser`; `voz doctor` (`--json`, `--redact`) revisa
  FFmpeg/ffprobe, puerto, rutas XDG, disco, runtime ASR y GPU sin cargar modelos.
- Aplicación web local servida por la propia API (React + Vite; el bundle
  compilado viaja dentro del wheel): proyectos, subida de audio/vídeo, elección
  de motor, pantalla de job con progreso por SSE, lista de segmentos virtualizada,
  reproductor del original con seek sincronizado, waveform con zoom, búsqueda y
  edición de segmentos con autoguardado y control de conflictos.
- Ingestión segura con FFmpeg: original inmutable con SHA-256, validación por
  streams, normalización a mono 16 kHz, cancelación y limpieza de temporales,
  comprobación de espacio en disco.
- Transcripción local por chunks con checkpoints SQLite, cancelación entre chunks
  y reanudación de jobs interrumpidos al arrancar; adapter Faster Whisper opcional
  (extra `asr-local`, incluye los wheels CUDA 12 `nvidia-cublas-cu12` y
  `nvidia-cudnn-cu12` en Linux).
- Persistencia SQLite (WAL) con migraciones Alembic aplicadas al arrancar
  (`0001` a `0004`), datos bajo los directorios XDG.
- Exportación por HTTP a TXT, Markdown, SRT, VTT y JSON canónico `voz.transcript`
  v1 (con variantes por hablante y con timestamps).
- Paquetería: wheel y sdist reproducibles con `uv build`
  (`scripts/check-reproducible-build.sh`), `scripts/checksums.sh` para
  `SHA256SUMS`, comprobación de instalación con `uv tool install`
  (`scripts/check-install.sh`), CI con job de empaquetado y
  [guía de instalación en Linux](docs/install/linux.md).
- Documentación: ADR 0001-0006, diagramas C4, contratos de `docs/api/`,
  `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `NOTICE` y licencias de fixtures.
- Windows, macOS y Linux con doble clic: `Iniciar-Windows.bat`,
  `Iniciar-Mac.command` e `Iniciar-Linux.sh` instalan `uv` si falta y arrancan
  VOZ; FFmpeg/ffprobe se descargan una vez si faltan (fijados por commit y
  SHA-256); rutas nativas en Windows y macOS y sistema de archivos portable
  (`safe_fs`). Guía en [docs/install/windows-macos.md](docs/install/windows-macos.md).
- Un segundo doble clic reutiliza el VOZ que ya está abierto en lugar de lanzar
  otro servidor.
- Botón **Cerrar servidor** (`POST /api/shutdown`) y acceso directo de escritorio
  (`GET/POST /api/desktop-shortcut`), ambos protegidos con cabecera anti-CSRF.
- VOZ instalable como aplicación desde Chrome/Edge (PWA: manifiesto e iconos
  propios), primera fase del [plan de empaquetado con Tauri](docs/packaging/tauri-plan.md).
- Interfaz nueva con IBM Carbon Design System: UI Shell, temas White/Gray
  10/90/100 y automático, 8 acentos, español e inglés (i18n es/en), tooltips en
  términos técnicos e IBM Plex empaquetada en local (el bundle no carga nada de
  Internet).
- Editor de transcripción: hablante a la izquierda, línea de tiempo de hablantes
  con cursor sincronizado, panel de propiedades y lista virtualizada.
- Progreso por etapa (Preparando, Transcribiendo, Hablantes, Guardando) con
  tiempo transcurrido, ETA y texto en vivo (`GET /api/jobs/{id}/preview`); el
  texto ya se puede leer mientras se calculan los hablantes. `POST /api/jobs`
  acepta `prompt` (instrucciones de estilo). Migración `0008`.
- Home con biblioteca de transcripciones (`GET /api/library`) y enlace propio por
  transcripción (`#/t/<id>`, `#/nueva`, `#/modelos`, `#/proveedores`): Atrás y
  recargar reabren el mismo trabajo. Contrato en [docs/api/library.md](docs/api/library.md).
- Renombrar (`PATCH /api/projects/{id}`) y eliminar proyectos
  (`DELETE /api/projects/{id}`, borra también sus archivos de medios; 409
  `project_busy` si hay un job en curso).
- Recalcular hablantes sin volver a transcribir
  (`POST /api/transcripts/{id}/rediarize`), con umbral de agrupación medido,
  fusión de hablantes muy pequeños y `talk_ms`/`first_ms` por hablante; panel de
  hablantes con tiempo de habla, filtro y muestra de audio.
- La cola de revisión salta al segmento y al audio.
- Exportar con vista previa: diálogo con formato, "Incluir tiempos", "Agrupar por
  hablante" y primeras líneas del resultado antes de descargar.
- Reproductor con volumen hasta 300 %, selector de velocidad y atajos de teclado.
- Piel **Material 3** como sistema de diseño alternativo, seleccionable en
  Ajustes junto a Carbon (colores desde el acento elegido, Roboto Flex local);
  evaluación en [docs/design/material3.md](docs/design/material3.md).

### Cambiado

- El build de hatch ignora `.gitignore` y lista explícitamente lo que empaqueta:
  los patrones amplios (`transcript.*`) hacían que el wheel omitiera
  `voz/domain/entities/transcript.py` y `voz` no arrancara al instalarlo.

### Limitaciones conocidas

- La transcripción con Faster Whisper real es **experimental**: el flujo completo
  está probado con un motor determinista de pruebas; el smoke con un modelo real
  es opt-in y todavía no forma parte de la verificación.
- CUDA es experimental hasta ejercitarlo en hardware real.
- Solo Bazzite (Fedora Atomic) se ha usado como entorno de desarrollo verificado;
  otras distribuciones Linux no se han probado.
- Sin diarización automática de hablantes, sin word alignment, sin proveedores
  cloud, sin AppImage/Flatpak.
