# C4 nivel 1: contexto del sistema

Roadmap: S16.09. Estado del código verificado contra `src/voz/bootstrap.py`,
`src/voz/interfaces/cli/main.py` y `src/voz/infrastructure/`.

VOZ es una aplicación local-first: una persona importa audio o video desde su
propio disco, lanza una transcripción y lee el resultado en el navegador. Todo
ocurre en su máquina; no hay cuenta, servidor remoto ni telemetría.

```mermaid
flowchart TB
    usuario(["Persona usuaria<br/>estudiante o profesional con grabaciones largas"])

    subgraph voz_sys["Sistema VOZ (una sola máquina, proceso local)"]
        voz["VOZ<br/>importa medios, transcribe y sirve el workspace web"]
    end

    ffmpeg["FFmpeg y ffprobe<br/>binarios del host: inspeccionan y normalizan audio"]
    fw["Faster Whisper<br/>librería Python opcional, extra asr-local"]
    hf["Hugging Face Hub<br/>solo al instalar un modelo, con confirmación explícita"]
    fs[("Filesystem del usuario<br/>archivos de origen y directorios XDG")]

    cloud["Providers cloud: OpenAI, ElevenLabs<br/>planificado, solo si el usuario los elige"]
    cpp["whisper.cpp<br/>planificado"]
    diar["Diarización pyannote<br/>planificado"]
    buzz["Cache de Buzz<br/>planificado, adapter opcional"]

    usuario -->|"navegador en 127.0.0.1 o CLI voz"| voz
    voz -->|"subprocess"| ffmpeg
    voz -->|"llamada en proceso, local_files_only"| fw
    voz -->|"lee y escribe datos propios"| fs
    voz -.->|"descarga puntual de modelo, opt-in"| hf

    voz -.-> cloud
    voz -.-> cpp
    voz -.-> diar
    voz -.-> buzz
```

## Actores

| Actor | Interacción real hoy |
| --- | --- |
| Persona usuaria | Ejecuta `voz` (abre `http://127.0.0.1:8765` en el navegador salvo `--no-browser`) o `voz doctor` para diagnosticar. Ver `src/voz/interfaces/cli/main.py`. |

No hay otros actores: no existen usuarios múltiples, roles ni autenticación
([SECURITY.md](../../SECURITY.md) describe el alcance de seguridad local).

## Sistemas externos

| Sistema | Uso hoy | Cuándo toca la red |
| --- | --- | --- |
| FFmpeg y ffprobe | `FfprobeMediaProbe` y `FfmpegMediaNormalizer` (`src/voz/infrastructure/audio/`) los invocan como subprocess. `voz doctor` verifica su presencia. | Nunca. |
| Faster Whisper | Único provider real: `FasterWhisperProvider` (`src/voz/infrastructure/asr/faster_whisper.py`). Es un extra opcional de `pyproject.toml`; sin él, el arranque básico funciona pero no se puede transcribir. | Nunca al transcribir: se construye con `local_files_only=True`. |
| Hugging Face Hub | `FileSystemModelStore.install` (`src/voz/infrastructure/model_storage.py`) usa `huggingface_hub.snapshot_download` con revisión fijada y confirmación explícita. Ningún endpoint HTTP ni comando CLI la invoca hoy (verificado con `grep`): es una API de infraestructura lista para el Model Manager (Sección 8). | Solo durante una instalación explícita. |
| Filesystem | Originales, derivados, base de datos, cachés temporales. Layout en [ADR-0002](../adr/0002-sqlite-persistence.md). | No aplica. |

## Planificado (no existe en el código)

- Providers cloud (OpenAI, ElevenLabs): Secciones 11 (OpenAI) y 12 (ElevenLabs) del
  [ROADMAP](../../ROADMAP.md). Deben ser opt-in por la regla de
  [ADR-0006](../adr/0006-local-first-privacy.md).
- whisper.cpp, WhisperX/alignment y diarización pyannote: Secciones 6, 7 y 9.
- Adapter opcional de cache de Buzz: [ADR-0001](../adr/0001-modular-monolith.md)
  lo permite, no hay código.

## Siguiente nivel

[C4-2 Contenedores](02-contenedores.md).
