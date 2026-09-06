# ADR-0004: ASR local con modelos explícitos y chunks recuperables

- Estado: Aceptada
- Fecha: 2026-09-05
- Responsables: mantenedores de VOZ
- Alcance: primer provider ASR local y recuperación de trabajos largos

## Contexto

VOZ necesita integrar Faster Whisper sin convertir Internet, CUDA o una cache
externa en requisitos implícitos. También debe procesar grabaciones largas sin
perder los chunks ya confirmados tras cancelar o cerrar la aplicación. El
contrato común no puede exponer tipos de Faster Whisper, CTranslate2, paths del
host ni flags propios del motor.

## Decisión

Faster Whisper es un adapter de infraestructura bajo `TranscriptionProvider`.
El adapter recibe un descriptor abierto de audio y resuelve exclusivamente una
instalación local exacta; nunca entrega un nombre remoto al runtime. Se instancia
con `local_files_only=True` y traduce salida, idioma, cancelación y fallos a tipos
canónicos de application.

Los modelos se representan mediante `ModelDescriptor`, cuya procedencia
instalable contiene tanto repositorio fuente como revisión fijada. La instalación
es una operación separada que exige confirmación explícita, usa
`huggingface_hub.snapshot_download` con esa revisión y publica una copia con
manifest bajo el directorio XDG de datos. Los metadatos de descarga viven bajo
el directorio XDG de cache. Importar VOZ, construir el provider o transcribir no
inicia descargas.

La revisión instalable debe ser un SHA de commit Git completo, hexadecimal y de
40 caracteres; ramas y tags mutables no forman una identidad recuperable. La
identidad de almacenamiento y caché incluye provider, model, source y revision.
El provider conserva como máximo un engine activo para no retener a la vez los
perfiles `fast` y `quality` en VRAM, y serializa su inicialización concurrente.
El composition root fija el provider al descriptor exacto con el que resolvió
device y compute; no puede reutilizar esa decisión con otro modelo o perfil.

`faster-whisper` se distribuye como el extra opcional `asr-local`; el arranque
básico no carga su runtime ni CUDA. La revisión fijada y el manifest son la
evidencia inicial de procedencia. Checksums adicionales y administración
avanzada del catálogo pertenecen a la Sección 8.

Los perfiles `fast` y `quality` serán descriptores canónicos resueltos a una
decisión observable de device/compute. Un fallback de CUDA a CPU nunca será
silencioso.

El orquestador divide la duración normalizada en chunks ordenados con offsets
globales y overlap pequeño. El adapter de audio abre un WAV PCM físico acotado a
cada chunk para no decodificar la grabación completa repetidamente. El provider
produce offsets locales y application los convierte una sola vez al timeline
global. Cada chunk se convierte en unidad recuperable. La confirmación de sus
segmentos, idioma solicitado y detectado, checkpoint y progreso del job ocurre
en una única transacción SQLite. Al reanudar, solo se omiten chunks cuya
confirmación completa existe para el mismo job, plan, provider, model, source,
revision e idioma solicitado.

El checkpoint conserva por separado la fracción completada de ASR y el progreso
global monotónico del job. Así, una etapa ASR que comienza con progreso previo
puede reanudarse sin confundir ambos espacios de progreso.

## Consecuencias positivas

- El modo offline no depende de resolución remota durante la transcripción.
- Una instalación identifica exactamente fuente y revisión.
- Faster Whisper y futuros providers comparten resultado, errores y cancelación.
- El cierre de VOZ no invalida chunks ya confirmados.
- Memoria y decodificación quedan acotadas por el tamaño del chunk.
- Dominio y application no importan SDKs de ASR.

## Costes y límites

- Instalar el extra y un modelo sigue siendo una acción separada del bootstrap.
- La disponibilidad real de CUDA depende del driver y runtime del equipo; hasta
  ejecutar una prueba opt-in, el camino GPU se rotula experimental.
- Una revisión fijada aporta reproducibilidad de procedencia, pero no sustituye
  un checksum publicado; la verificación ampliada queda para Model Manager.
- El overlap requiere una política determinista para no duplicar segmentos.

## Fuentes upstream

- Faster Whisper permite cargar un directorio local y ofrece
  `local_files_only`: <https://github.com/SYSTRAN/faster-whisper>
- Hugging Face documenta `snapshot_download` con `revision` y `cache_dir`:
  <https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download>
- CTranslate2 expone los compute types soportados por device:
  <https://opennmt.net/CTranslate2/python/ctranslate2.get_supported_compute_types.html>

## Verificación

Esta decisión se considera aplicada cuando:

- construir/usar el adapter sin modelo no produce red ni descarga;
- una instalación no confirmada falla antes de construir el downloader;
- el manifest conserva provider, modelo, source y revision exactos;
- el adapter transforma timestamps a milisegundos y preserva texto e idioma;
- fallos y cancelación se traducen a códigos estables sin paths privados;
- los perfiles y fallback son observables mediante pruebas deterministas;
- reabrir SQLite recupera chunks confirmados sin repetirlos.
- la suite contractual se ejecuta sobre el adapter y existe un smoke real
  opt-in que nunca selecciona ni descarga modelos por sí mismo.
