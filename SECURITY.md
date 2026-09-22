# Política de seguridad de VOZ

## Alcance

VOZ es una aplicación local-first: se instala y ejecuta en la máquina de una
sola persona, sirve por defecto en `http://127.0.0.1:8765` y no requiere una
cuenta ni un servicio remoto para funcionar (ver [README.md](README.md) y las
invariantes de producto en [AGENTS.md](AGENTS.md)). Esta política cubre el
código de este repositorio: la CLI `voz`, el servidor FastAPI local, el
frontend web y los adaptadores de infraestructura (FFmpeg, persistencia
SQLite, providers de transcripción).

Quedan fuera de alcance: proveedores cloud opcionales de terceros (su propia
seguridad depende de ese proveedor), el sistema operativo anfitrión, y
cualquier fork o distribución no oficial del proyecto.

## Qué se considera una vulnerabilidad

Ejemplos de lo que consideramos un reporte de seguridad válido para VOZ:

- exposición de rutas absolutas del host hacia la API o el frontend, en
  contra de la invariante de que la UI no debe conocer paths del sistema de
  archivos ([AGENTS.md](AGENTS.md));
- ejecución remota de código o de comandos a través de un archivo subido
  (por ejemplo, mediante el pipeline de ingestión FFmpeg o el probe de
  medios);
- path traversal o escritura fuera del directorio confiable de
  almacenamiento de medios (ver
  [ADR-0003](docs/adr/0003-ffmpeg-ingestion.md));
- fuga de datos privados del usuario: grabaciones, transcripciones, claves API
  o contenido de la base de datos local hacia un tercero, un log, o un
  endpoint no destinado a ese propósito;
- una API que quede accesible fuera de `127.0.0.1` sin que el usuario haya
  activado explícitamente una opción de exposición en LAN;
- una vulnerabilidad de dependencia (Python o npm) con una ruta de explotación
  real y conocida dentro de VOZ.

Lo siguiente normalmente **no** se trata como un incidente de seguridad, sino
como un bug funcional (repórtalo con la plantilla de bug del repositorio):
errores de UI sin impacto en confidencialidad/integridad/disponibilidad, o
fallas de una funcionalidad ya marcada como experimental en `ROADMAP.md`.

## Cómo reportar

VOZ todavía no publica una dirección de correo electrónico como canal de
reporte. Usa uno de estos canales privados:

1. **GitHub Security Advisories privadas** del repositorio (opción
   "Report a vulnerability" bajo la pestaña "Security" de GitHub), si tu
   acceso al repositorio la ofrece.
2. Si no tienes esa opción disponible, abre un **issue privado dirigido al
   mantenedor** usando la visibilidad restringida que ofrezca GitHub para
   colaboradores del repositorio.

No abras un issue público ni un pull request público que describa una
vulnerabilidad no divulgada, ni incluyas en el reporte grabaciones o datos
reales de otra persona.

Incluye en tu reporte, en la medida de lo posible:

- una descripción del problema y su impacto potencial;
- pasos para reproducirlo, incluyendo versión/commit del repositorio;
- si aplica, un fixture sintético que reproduzca el problema sin datos
  privados reales (VOZ no acepta grabaciones privadas como fixtures, ver
  [AGENTS.md](AGENTS.md)).

## Tiempos orientativos

Este es un proyecto sin release pública y sin equipo de seguridad dedicado;
estos tiempos son orientativos, no un compromiso contractual:

- confirmación de recepción del reporte: en un plazo de referencia de 7 días;
- evaluación inicial de severidad: en un plazo de referencia de 14 días desde
  la confirmación;
- corrección o mitigación: el plazo depende de la severidad y de la
  disponibilidad del mantenedor; se comunicará una estimación una vez
  evaluado el reporte.

## Versiones soportadas

VOZ no tiene todavía una release pública (ver Sección 15 y 16 de
[ROADMAP.md](ROADMAP.md)). Hasta la primera release, **solo la rama `main` es
soportada** para reportes y correcciones de seguridad. No existen versiones
etiquetadas ni un ciclo de mantenimiento de versiones anteriores.

| Versión | Soportada |
| --- | --- |
| `main` (checkout actual) | sí |
| cualquier fork o versión anterior a la primera release | no |

Cuando exista una primera release pública, esta tabla se actualizará para
reflejar qué versiones etiquetadas reciben parches de seguridad.
