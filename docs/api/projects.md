# Projects and glossary — S13.01

Creating and listing projects is documented in [jobs.md](jobs.md) ("Projects");
renaming and deleting are in [library.md](library.md). This page covers the
per-project glossary. Errors have the shape `{"detail": {"code", "message"}}`;
no host paths. Common rules: [README.md](README.md).

## Project glossary

A short list of terms (proper names, acronyms, technical vocabulary) that
**biases** the engine toward those words. It never rewrites the transcribed
text: whatever the engine returns is stored literally.

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/projects/{project_id}/glossary` | — | 200 `Glossary`; 404 `project_not_found` |
| `PUT /api/projects/{project_id}/glossary` | `{"terms": [str]}` | 200 `Glossary`, already normalized; 404 `project_not_found`; 422 `glossary_invalid` |

```json
{
  "terms": ["Mitochondria", "V"],
  "max_terms": 50,
  "max_term_length": 50,
  "applies_to": ["faster-whisper", "…"]
}
```

- `PUT` replaces the whole list. Each term is stripped; empty terms and exact
  duplicates are dropped (order is kept); `[]` clears the glossary.
- Limits: at most 50 terms of 50 printable characters (no line breaks or control
  characters). The limits fit within those of the strictest cloud provider. If
  they are not met: 422 `glossary_invalid` and **nothing** is saved (the previous
  glossary is kept).
- `applies_to` lists the engine ids that use the glossary; any other engine (for
  example whisper.cpp) ignores it. The UI says so.
- Persistence: table `project_glossaries` (migration `0007_project_glossary`),
  one row per project, deleted by cascade with the project.
- When a job is created, the current glossary is copied into its selection
  ([jobs.md](jobs.md)), so repeating that job uses the same terms.

## Quality profiles

`GET /api/quality-profiles[?language=es]` (read-only) returns
`{"default", "profiles": [{"name","label","description","parameters"}],
"recommendation": {"language","profile","measured","evidence","synthetic",
"unmeasured_profiles"}}`. `recommendation.profile` is `null` and `measured` is
`false` when there is no measurement for the language (or no language was given):
a recommendation is never invented. See [quality-profiles.md](../quality-profiles.md).
