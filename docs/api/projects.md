# Proyectos y glosario — S13.01

El alta y el listado de proyectos están documentados en `docs/api/jobs.md`
("Proyectos"). Aquí va el glosario por proyecto. Errores con la forma
`{"detail": {"code", "message"}}`; sin rutas del host.

## Glosario del proyecto

Lista corta de términos (nombres propios, siglas, vocabulario técnico) que
**sesga** al motor hacia esas palabras. Nunca reescribe el texto transcrito: lo
que el motor devuelve se guarda literal.

| Método y ruta | Request | Respuesta |
| --- | --- | --- |
| `GET /api/projects/{project_id}/glossary` | — | 200 `Glossary`; 404 `project_not_found` |
| `PUT /api/projects/{project_id}/glossary` | `{"terms": [str]}` | 200 `Glossary` ya normalizado; 404 `project_not_found`; 422 `glossary_invalid` |

```json
{
  "terms": ["Mitocondria", "VOZ"],
  "max_terms": 50,
  "max_term_length": 50,
  "applies_to": ["faster-whisper", "…"]
}
```

- `PUT` reemplaza la lista entera. Se recorta cada término, se descartan los
  vacíos y los duplicados exactos (se conserva el orden); `[]` borra el glosario.
- Límites: como máximo 50 términos de 50 caracteres, imprimibles (sin saltos de
  línea ni caracteres de control). Los límites caben en los del proveedor cloud
  más estricto. Si no se cumplen: 422 `glossary_invalid` y **no** se guarda nada
  (el glosario anterior se conserva).
- `applies_to` lista los ids de motor que usan el glosario; cualquier otro motor
  (p. ej. whisper.cpp) lo ignora. La UI lo dice.
- Persistencia: tabla `project_glossaries` (migración `0007_project_glossary`),
  una fila por proyecto, borrada en cascada con el proyecto.
- Al crear un job se copia el glosario vigente a su selección (`docs/api/jobs.md`),
  de modo que repetir ese job usa los mismos términos.

## Perfiles de calidad

`GET /api/quality-profiles[?language=es]` (solo lectura) devuelve
`{"default", "profiles": [{"name","label","description","parameters"}],
"recommendation": {"language","profile","measured","evidence","synthetic",
"unmeasured_profiles"}}`. `recommendation.profile` es `null` y `measured` es
`false` cuando no hay medición para el idioma (o no se indicó idioma): nunca se
inventa. Ver `docs/quality-profiles.md`.
