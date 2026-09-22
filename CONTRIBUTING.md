# Contribuir a VOZ

Gracias por tu interés en VOZ. Este documento resume el flujo de trabajo real
del repositorio para que una contribución externa siga las mismas reglas que
ya usan los agentes y mantenedores del proyecto.

> **Estado del proyecto:** VOZ todavía no tiene una release pública ni un
> proceso formal de aceptación de contribuciones externas. El repositorio de
> GitHub es privado. Esta guía documenta el flujo previsto para cuando el
> proyecto se abra (Sección 16 de [ROADMAP.md](ROADMAP.md)); si tienes acceso
> de colaborador hoy, síguela igual: es la misma que usan los agentes internos.

## 1. Antes de escribir código

1. Lee [AGENTS.md](AGENTS.md) completo. Contiene las reglas de arquitectura,
   privacidad, alcance y definición de hecho que se aplican a cualquier
   cambio, humano o generado por un agente.
2. Lee [ROADMAP.md](ROADMAP.md), en especial la sección "Convenciones" y la
   sección numerada que corresponda a lo que quieres trabajar.
3. Lee los [ADR](docs/adr/) relevantes para el área que vas a tocar. Un cambio
   arquitectónico durable requiere una ADR nueva o actualizada, no solo una
   discusión en el pull request.
4. Si existe `.ai/HANDOFF.md` en tu checkout, léelo: puede describir trabajo en
   curso que no está reflejado todavía en `ROADMAP.md`. Ese archivo es privado
   y transitorio; no se versiona ni se referencia desde documentación pública.

## 2. Elegir y registrar una asignación

- Selecciona **entre uno y tres IDs** del roadmap (`S<sección>.<número>`) que
  formen una sola porción vertical relacionada. No mezcles secciones sin
  relación en una misma asignación.
- Antes de implementar, registra la asignación en la tabla de "Trabajo activo"
  de la sección correspondiente en `ROADMAP.md`, con los IDs exactos y el
  estado `en curso`. Nadie más debe estar trabajando esos mismos IDs a la vez.
- Actualiza el checkbox, el estado de la fila y el último logro verificable
  **en la misma edición**, solo después de verificar el resultado. Código
  escrito pero no comprobado sigue pendiente.

## 3. Comandos de verificación

Ejecuta las comprobaciones que correspondan a las capas que tocaste. Los
comandos exactos, tomados de [AGENTS.md](AGENTS.md), son:

### Backend y CLI

```bash
uv sync --all-groups
uv run voz --no-browser
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

### Frontend

```bash
cd apps/web
npm ci
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
```

No instales Whisper ni descargues modelos de voz, no invoques proveedores de
pago, no publiques un paquete, no hagas push de commits ajenos a tu propia
rama y no alteres el sistema operativo anfitrión como parte de una
verificación ordinaria.

## 4. Reglas de privacidad y contenido excluido

Nunca incluyas en un commit o pull request:

- grabaciones, audio, video o transcripciones privadas, propias o de terceros;
- modelos de ASR/diarización descargados o sus pesos;
- archivos multimedia generados durante pruebas manuales;
- bases de datos SQLite, caches, o cualquier dato bajo rutas XDG de ejecución;
- claves API, tokens, archivos `.env` o cualquier otro secreto;
- el contenido de `.ai/` (contexto de sesión de agentes, transitorio y local).

Si necesitas un fixture de audio para pruebas, genera un fixture sintético
(por ejemplo con `ffmpeg -f lavfi`) y documenta su procedencia y licencia en
[docs/fixtures-licenses.md](docs/fixtures-licenses.md); no uses grabaciones
reales.

## 5. ADR para cambios durables

Si tu cambio introduce o modifica una decisión de arquitectura duradera
(límites entre capas, elección de framework, esquema de persistencia,
contrato de un provider, etc.), añade una ADR nueva en `docs/adr/` o actualiza
la existente, siguiendo el formato de las ADR ya presentes (contexto,
decisión, consecuencias, alternativas consideradas, verificación). No
documentes una decisión durable solo en la descripción del pull request.

## 6. Estilo de commits

Usa el formato `tipo(ámbito): resumen`, en minúsculas y en modo imperativo,
por ejemplo:

```text
feat(asr): agregar perfil de calidad para faster-whisper
fix(media-storage): evitar traversal en nombres inseguros
docs(adr): completar ADR de providers
test(jobs): cubrir cancelación durante reanudación
```

Tipos sugeridos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.
El ámbito es el módulo o capa afectada (por ejemplo `domain`, `media-storage`,
`jobs`, `frontend`, `adr`, `roadmap`).

## 7. Definición de hecho

Un ID del roadmap solo se considera terminado cuando se cumple todo lo
siguiente:

- el comportamiento mínimo completo de la porción elegida está implementado;
- el comportamiento nuevo tiene pruebas en el nivel adecuado;
- cada bug corregido tiene una prueba de regresión;
- el formateo, lint, chequeo de tipos y pruebas relevantes pasan;
- las rutas de fallo y cancelación están cubiertas cuando el cambio las
  introduce;
- el comportamiento visible para el usuario y los cambios de arquitectura
  quedan documentados;
- el resultado fue verificado ejecutando los comandos anteriores, no inferido
  de archivos generados;
- `ROADMAP.md` se actualiza únicamente después de verificar, en la misma
  edición que el estado de la asignación y el logro alcanzado.

Nunca marques un ID como completo porque el código fue escrito pero no
comprobado. Si una verificación no puede ejecutarse, deja el ID pendiente y
registra el bloqueo en la fila de asignación.

## 8. Pull requests

Usa la plantilla de pull request del repositorio
(`.github/pull_request_template.md`) y completa su checklist: IDs del roadmap
tocados, comandos ejecutados, ausencia de secretos/medios/`.ai/`, ADR si
aplica, prueba de regresión si corriges un bug, y actualización de
`ROADMAP.md` en la misma edición.

## 9. Reportar problemas

Para bugs y solicitudes de funcionalidad usa las plantillas de issue del
repositorio. Para una vulnerabilidad de seguridad, sigue el proceso descrito
en [SECURITY.md](SECURITY.md) en lugar de abrir un issue público.

## 10. Código de conducta

Toda interacción en este proyecto se rige por
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
