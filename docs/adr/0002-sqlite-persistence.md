# ADR-0002: SQLite con mapeo explícito y migraciones Alembic

- Estado: Aceptada
- Fecha: 2026-09-02
- Responsables: mantenedores de VOZ
- Alcance: persistencia local inicial

## Contexto

VOZ necesita que proyectos, medios, transcripciones, hablantes y jobs sobrevivan
al cierre de la aplicación. El producto se ejecuta para una persona en una sola
máquina y no necesita un servidor de base de datos. Al mismo tiempo, el dominio
no debe depender de SQLAlchemy ni adoptar detalles de tablas como reglas de
negocio.

Los jobs largos también requieren escrituras incrementales y lecturas
concurrentes desde la UI. La evolución del esquema debe ser reproducible y no
puede depender de crear tablas implícitamente en cada arranque.

## Decisión

La primera implementación persistente utilizará SQLite mediante SQLAlchemy 2,
con migraciones versionadas en Alembic y `journal_mode=WAL` activado por cada
conexión del adapter.

- El archivo predeterminado será `~/.local/share/voz/voz.db`, resuelto por el
  módulo XDG existente.
- Los contratos de repositories vivirán en `application/ports` y trabajarán con
  entidades del dominio.
- Tablas, metadata y conversión fila-entidad vivirán exclusivamente en
  `infrastructure/persistence`.
- Las entidades del dominio no serán modelos ORM y no importarán SQLAlchemy.
- La migración inicial será la fuente autoritativa del esquema distribuido.
- Las pruebas podrán crear un engine SQLite temporal sin escribir datos en el
  checkout ni en los directorios XDG reales.
- Cada operación de repository tendrá un límite transaccional explícito. Una
  futura unidad de trabajo podrá coordinar varias operaciones si aparece un caso
  de uso que lo necesite.

## Consecuencias positivas

- No hay servicio externo que instalar o administrar.
- WAL permite que las lecturas locales continúen mientras se confirman
  escrituras cortas.
- El dominio puede probarse sin base de datos.
- Los adapters pueden sustituirse sin cambiar los casos de uso.
- Alembic deja una ruta auditable para evolucionar el esquema.

## Costes y límites

- SQLite sigue siendo almacenamiento de un solo equipo, no multiusuario remoto.
- Hay conversión explícita entre filas y entidades.
- Las operaciones síncronas no deben ejecutarse en el event loop durante jobs
  pesados; la capa de aplicación deberá enviarlas a un worker cuando aplique.
- WAL crea archivos auxiliares `-wal` y `-shm`, que son datos de ejecución y no
  pertenecen a Git.

## Alternativas consideradas

### Postgres

Rechazado para la primera versión. Añade instalación, credenciales y un proceso
externo sin aportar valor al caso local de un usuario.

### ORM dentro del dominio

Rechazado. Acoplaría invariantes y tests centrales al ciclo de vida de
SQLAlchemy y dificultaría sustituir la persistencia.

### Crear tablas automáticamente sin migraciones

Rechazado como mecanismo de distribución. Puede ser útil en fixtures de tests,
pero no registra cómo evoluciona una base existente.

## Verificación

La decisión se considera implementada cuando:

- ningún módulo bajo `domain` importa SQLAlchemy;
- los ports no exponen `Session`, tablas ni expresiones SQL;
- la migración inicial crea todas las tablas de la Sección 2;
- una conexión nueva reporta `journal_mode=wal` cuando el archivo lo permite;
- repositories reconstruyen entidades equivalentes después de cerrar y abrir
  otro engine sobre el mismo archivo;
- las pruebas usan rutas temporales y no crean `voz.db` en el repositorio.
