# Licencias de los fixtures de prueba

Este documento inventaria todos los archivos de fixtures presentes en
`tests/fixtures/` a la fecha de esta edición, su procedencia y su licencia.
Sirve como registro público de S16.17 del [roadmap](../ROADMAP.md).

Solo se documenta lo que puede verificarse directamente en el repositorio
(archivos existentes, su README de procedencia y las pruebas que los
consumen). Cuando un dato no puede verificarse desde el repositorio, este
documento lo marca explícitamente como "procedencia por confirmar" en lugar
de asumirlo.

## Inventario

A la fecha de esta edición, `tests/fixtures/` contiene un único conjunto de
fixtures: `tests/fixtures/media/`, descrito con detalle en
[`tests/fixtures/README.md`](../tests/fixtures/README.md), que es la fuente
autoritativa de este inventario. Este documento resume y no reemplaza ese
archivo.

### `tests/fixtures/media/` — tono sintético de 440 Hz

Los seis archivos de este directorio contienen la misma onda senoidal
matemática de 440 Hz, 0.25 segundos, un canal, generada a 16 kHz. No
contienen voz, datos personales, ni grabaciones de terceros.

| Archivo | Formato | Codec de audio | Bytes |
| --- | --- | --- | ---: |
| `synthetic-tone.wav` | WAV | `pcm_s16le` | 8,044 |
| `synthetic-tone.mp3` | MP3 | `mp3` (libmp3lame) | 1,296 |
| `synthetic-tone.m4a` | M4A | `aac` | 2,290 |
| `synthetic-tone.ogg` | OGG | `vorbis` | 3,622 |
| `synthetic-tone.opus` | OGG | `opus` | 867 |
| `synthetic-tone.webm` | WebM | `opus` | 1,264 |

SHA-256 de cada archivo (manifiesto de integridad):

| Archivo | SHA-256 |
| --- | --- |
| `synthetic-tone.wav` | `d959e7258ec4ad502f79a133bee06ccfcd2eac7e7c4ef5040c4829f8c29915ee` |
| `synthetic-tone.mp3` | `8ca7afa2af2e68dde5d8a97abb6a86aef7bc210b040763835cd28df7d5ab0b7d` |
| `synthetic-tone.m4a` | `860592365328e72edc49fb5930b76246437fd121efc78a9fc421bd927217fab3` |
| `synthetic-tone.ogg` | `d9d96e65b0fb292a53868f6a412dcc4ade47e30586bae10822802263823017fd` |
| `synthetic-tone.opus` | `3255e94afd95eb8fd68d7072a8d4386db400cd0b776f8d55428a4746227186f7` |
| `synthetic-tone.webm` | `b673d57f775551995b9d7519c4c0d31372567e5b6c25ce70abbdc69c517cd063` |

**Cómo se generaron:** con FFmpeg 8.1.2, a partir de la fuente `lavfi`
`sine=frequency=440:sample_rate=16000:duration=0.25`, usando `+bitexact` y
eliminación de metadata para que la compilación sea reproducible con la misma
versión de FFmpeg. Los comandos exactos usados para cada formato están
documentados en
[`tests/fixtures/README.md`](../tests/fixtures/README.md#provenance-and-license).
Para `.opus` y `.webm`, Opus se decodifica a su reloj fijo de códec de 48 kHz
aunque la fuente se generó a 16 kHz; es el comportamiento esperado del codec,
no un error de generación.

**Licencia:** datos de prueba originales de los colaboradores de VOZ,
generados localmente con la herramienta `sine` de FFmpeg. No se descargó ni
adaptó ningún medio externo. Se distribuyen bajo la misma
[licencia MIT](../LICENSE) del repositorio.

**Uso en pruebas:** el manifiesto de tamaños y hashes se verifica
automáticamente en [`test_media_fixtures.py`][test-media-fixtures], que
además comprueba con `ffprobe` real que cada archivo expone el contenedor y
codec esperados. Otras pruebas que consumen estos fixtures incluyen:

- `tests/contract/test_media_probe_port.py`
- `tests/integration/application/test_import_media_sqlite.py`
- `tests/integration/application/test_normalize_imported_media.py`
- `tests/integration/audio/test_ffmpeg_media_normalizer_integration.py`
- `tests/integration/audio/test_ffprobe_media_probe.py`
- `tests/integration/test_media_upload_api.py`

[test-media-fixtures]: ../tests/integration/media/test_media_fixtures.py

## Fixtures fuera de `tests/fixtures/`

No se encontraron otros directorios de fixtures binarios en `tests/` a la
fecha de esta edición (búsqueda por nombre de archivo y por referencias a
`fixtures/media` desde el código de pruebas). Si una futura sección del
roadmap añade fixtures adicionales (por ejemplo audio con voz sintética para
diarización o alignment), este documento debe actualizarse en la misma
edición que los añade, siguiendo el mismo formato: nombre, formato, cómo se
generó y licencia. Hasta entonces, cualquier fixture nuevo que no aparezca
aquí tiene **procedencia por confirmar**.

## Regla para nuevos fixtures

Según [AGENTS.md](../AGENTS.md) y [CONTRIBUTING.md](../CONTRIBUTING.md), no se
deben usar grabaciones privadas como fixtures de prueba. Un nuevo fixture de
audio/video debe:

- generarse de forma sintética y reproducible (por ejemplo con
  `ffmpeg -f lavfi`), o provenir de una fuente cuya licencia permita
  explícitamente su redistribución en un repositorio MIT;
- documentarse en este archivo con su procedencia, comando de generación y
  licencia, antes o en la misma edición en que se agrega al repositorio;
- si su licencia de origen no es MIT ni de dominio público, este documento
  debe indicar la licencia exacta y cualquier atribución requerida, y esa
  atribución debe reflejarse también en `NOTICE`.
