## Resumen

Describe brevemente qué cambia este pull request y por qué.

## IDs del roadmap tocados

Indica los IDs exactos de `ROADMAP.md` (`S<sección>.<número>`), entre uno y
tres, correspondientes a una sola porción vertical:

-

## Checklist

### Proceso (AGENTS.md / CONTRIBUTING.md)

- [ ] Leí `AGENTS.md` y los ADR relevantes para este cambio.
- [ ] Registré la asignación (IDs exactos) en la tabla de "Trabajo activo" de
      `ROADMAP.md` antes de implementar.
- [ ] `ROADMAP.md` quedó actualizado (checkbox, estado y último logro
      verificable) en la misma edición que este cambio, solo después de
      verificar el resultado.

### Comprobaciones backend ejecutadas

- [ ] `uv sync --all-groups`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`
- [ ] No aplica (este cambio no toca backend/CLI).

### Comprobaciones frontend ejecutadas

- [ ] `npm ci` (en `apps/web`)
- [ ] `npm run lint`
- [ ] `npm run typecheck`
- [ ] `npm run test`
- [ ] `npm run build`
- [ ] No aplica (este cambio no toca `apps/web`).

### Privacidad y alcance

- [ ] No incluye grabaciones, transcripciones o datos privados reales.
- [ ] No incluye modelos, pesos, medios generados, bases de datos, caches ni
      contenido de `.ai/`.
- [ ] No incluye claves API, tokens ni secretos.
- [ ] Este cambio no modifica más de una porción vertical del roadmap.

### Arquitectura y regresión

- [ ] Añadí o actualicé una ADR en `docs/adr/` (marca "no aplica" si el
      cambio no es una decisión de arquitectura durable).
- [ ] No aplica (no es un cambio de arquitectura durable).
- [ ] Si este PR corrige un bug, agregué una prueba de regresión.
- [ ] No aplica (este PR no corrige un bug).

## Riesgos conocidos / seguimientos pendientes

Describe cualquier limitación, caso no cubierto o trabajo de seguimiento que
quede fuera de este PR.
