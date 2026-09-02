# ADR-0001: Monolito modular local con arquitectura hexagonal

- Estado: Aceptada
- Fecha: 2026-09-01
- Responsables: mantenedores de VOZ
- Alcance: arquitectura inicial del producto

## Contexto

VOZ será una aplicación local-first para importar audio o video, ejecutar
transcripciones largas, editar resultados sincronizados y exportarlos. En una
misma máquina compartirá GPU, filesystem, base de datos y ciclo de vida. La
primera versión necesita una instalación sencilla, funcionamiento sin Internet
después de descargar modelos y capacidad de incorporar distintos proveedores de
transcripción y diarización.

El trabajo pesado debe ejecutarse sin bloquear la interfaz y debe poder guardar
progreso recuperable. Sin embargo, separar la aplicación en servicios
independientes desde el inicio agregaría puertos, despliegues, serialización,
observabilidad distribuida y nuevos modos de fallo sin aislar recursos físicos:
todos seguirían compitiendo por la misma GPU y el mismo disco.

La variación que sí conviene aislar está entre el dominio y los mecanismos
externos: FastAPI, SQLite, FFmpeg, motores ASR, proveedores cloud y la interfaz
web.

## Decisión

VOZ se implementará inicialmente como un **monolito modular local** con
**arquitectura Clean/Hexagonal** y un **pipeline interno asíncrono de jobs**.

Las dependencias apuntan hacia el núcleo:

```text
Web UI / CLI / API
        |
        v
Application use cases
        |
        v
Domain

Infrastructure adapters implement application/domain ports
```

Se establecen estas fronteras:

- **Domain:** entidades, value objects, reglas e invariantes sin dependencias de
  frameworks.
- **Application:** casos de uso, puertos y coordinación del pipeline.
- **Infrastructure:** adaptadores de persistencia, filesystem, FFmpeg, modelos,
  ASR, diarización y observabilidad.
- **Interfaces:** API HTTP, CLI y traducción entre contratos externos e internos.
- **Web UI:** cliente del contrato HTTP/eventos; no conoce rutas del host ni
  detalles de proveedor.

Los proveedores externos implementarán contratos comunes, por ejemplo
`TranscriptionProvider`, `DiarizationProvider` y `AlignmentProvider`. La
selección y construcción de adaptadores ocurrirá en un composition root.

Las operaciones largas se modelarán como jobs con estado explícito, progreso,
cancelación, errores tipados y checkpoints cuando corresponda. Para progreso de
servidor a navegador se preferirá SSE; WebSocket solo se añadirá si aparece una
necesidad bidireccional concreta.

SQLite y el filesystem son decisiones iniciales de infraestructura, no
dependencias del dominio. Los datos de ejecución respetarán XDG Base Directory y
se mantendrán fuera del checkout.

## Consecuencias positivas

- Una instalación y un proceso local son suficientes para la primera versión.
- El dominio se puede probar sin cargar GPU, FFmpeg, FastAPI o clientes cloud.
- Cambiar Faster Whisper por whisper.cpp no requiere modificar el dominio.
- Añadir un proveedor cloud no obliga a rediseñar la representación canónica del
  transcript ni la UI central.
- La persistencia y los providers pueden evolucionar mediante puertos y
  adaptadores.
- Se conservan checkpoints y eventos de progreso sin introducir infraestructura
  distribuida.
- El despliegue local, el diagnóstico y la privacidad son más comprensibles.

## Costes y límites

- Las fronteras modulares dependen de disciplina y pruebas; no las impone una
  frontera de proceso.
- Una tarea que bloquee el event loop puede afectar toda la aplicación. El
  trabajo de CPU/GPU debe ejecutarse mediante workers/procesos apropiados.
- Un fallo del proceso puede interrumpir todos los módulos, por lo que la
  persistencia incremental y la recuperación son requisitos reales.
- SQLite no pretende cubrir uso multiusuario distribuido.
- El composition root debe evitar acoplar casos de uso a implementaciones
  concretas.

## Alternativas consideradas

### Microservicios desde v1

Rechazada. Multiplica despliegue, comunicación, observabilidad y recuperación,
pero no separa la GPU ni mejora el caso de un usuario local.

### Integración directa con el proceso o GUI de Buzz

Rechazada como arquitectura central. Buzz puede ser referencia y su cache puede
integrarse mediante un adaptador opcional, pero sus detalles internos no serán
el contrato de VOZ.

### Aplicación de escritorio Electron/Tauri desde el inicio

Pospuesta. Primero se validará el flujo web local servido por `voz`. Un wrapper
de escritorio puede evaluarse después sin cambiar el núcleo.

### Event Sourcing o CQRS completo

Rechazados para v1. Comandos y consultas separados a nivel de casos de uso,
junto con checkpoints de jobs, cubren las necesidades conocidas con menor
complejidad.

## Reglas de cumplimiento

Esta decisión se considera respetada cuando:

- `domain` no importa paquetes de frameworks o proveedores;
- casos de uso dependen de ports y no de SQL/FFmpeg/SDKs concretos;
- routers no contienen reglas de negocio;
- la UI no recibe rutas absolutas del host;
- los proveedores pasan contract tests comunes;
- el proceso funciona offline con modelos ya instalados;
- los jobs largos persisten progreso recuperable.

Cambiar estas reglas requiere una nueva ADR que sustituya explícitamente esta
decisión.
