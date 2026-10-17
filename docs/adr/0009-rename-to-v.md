# ADR-0009: Rename the product to V with backward compatibility

- Status: Accepted
- Date: 2026-10-11
- Owners: V maintainers
- Scope: public product name, CLI command, user-facing brand strings and
  project metadata; explicitly **not** internal identifiers or user data
  (Programa V slices V1-01 to V1-11)
- Related: [ADR-0002](0002-sqlite-persistence.md) (SQLite and XDG layout),
  [ADR-0006](0006-local-first-privacy.md) (local-first, user data stays put)

## Context

The project started as **VOZ**, a local transcriber. Its scope is growing into
a local voice harness: any speech-to-text or text-to-speech model the user
chooses, downloaded and run on their own hardware. The public name is now **V**
(subtitle "Local Voice AI"), with repository `MarshallGomez1103/V`.

The old name is spread across the tree (figures from `git grep`, excluding the
compiled bundle in `src/voz/static`):

- about 2,900 lines mention "voz"; about 1,400 of them are package imports or
  paths (`from voz`, `src/voz`, `voz-transcriber`);
- 27 distinct `VOZ_*` environment variables;
- user data lives under `~/.local/share/voz/` (database `voz.sqlite3`,
  `projects/`, `models/`, `uploads/`, `waveforms/`), plus `~/.cache/voz/` and
  `~/.config/voz/` (`APPLICATION_DIRECTORY` in `src/voz/infrastructure/paths.py`,
  `DATABASE_FILENAME` in `src/voz/bootstrap.py`);
- exported JSON files carry `"format": "voz.transcript"`, version 1
  (`CANONICAL_FORMAT` in `src/voz/application/export/json_canonical.py`).

Some of these names are visible to users (UI, README, launchers, command name);
others are contracts with data already on disk. Renaming the latter without a
tested migration risks losing the user's projects, models and exported files,
and gives the end user nothing they would notice.

A known conflict: `v` is also the compiler binary of the V programming language
(vlang). A user with vlang installed may have another `v` earlier in `PATH`.

## Decision

Rename what users see; keep every internal identifier and every on-disk
contract unchanged (strategy B of the rename analysis).

1. **Product name:** **V**, subtitle "Local Voice AI". Repository:
   `github.com/MarshallGomez1103/V`.
2. **CLI:** the primary command is `v`. `voz` stays as an alias for the same
   entry point, at least until the first public release. Because `v` collides
   with the vlang compiler, `voz doctor` warns when another `v` shadows ours in
   `PATH` (slice V1-02). `voz` remains the unambiguous fallback.
3. **Changed:**
   - UI and brand strings, page `<title>`, PWA manifest (`name`,
     `short_name`), icon;
   - launchers: new English names (`Start-V-Windows.bat`,
     `Start-V-macOS.command`, `start-v-linux.sh`) that run `v`; the existing
     `Iniciar-*` launchers stay as thin wrappers for one release;
   - desktop entry name (`Name=V`);
   - README and documentation, which move to English from V-1 onwards;
   - `pyproject.toml`: `authors = [{ name = "V contributors" }]`, description
     and `[project.urls]` pointing at the new repository.
4. **Unchanged on purpose:**
   - Python package `voz` (`src/voz`, all imports);
   - distribution name `voz-transcriber` (to be revisited before the first
     public release);
   - XDG directories named `voz/` and the database file `voz.sqlite3`;
   - export format identifier `voz.transcript`, version 1;
   - environment variables `VOZ_*`, with **no** `V_*` alias: a single-letter
     prefix collides too easily with unrelated variables;
   - Flatpak identity was deferred at this decision date; the packaging
     update below records the new identifier separately.
5. **History is not rewritten.** Past CHANGELOG entries and existing ADRs keep
   the VOZ name in their historical text.
6. **Any future full internal migration** (package, XDG paths, database file,
   format id, environment variables) requires its own ADR with a tested,
   reversible data migration and a backup step.

## Consequences

### Positive

- Users see one consistent brand and get the new command without any change to
  their data, scripts or exported files.
- Zero data-loss risk: nothing on disk is moved or renamed.
- The change is small and easy to revert; no mass search-and-replace over
  imports and tests.
- Old JSON exports keep validating, and old scripts using `voz` or `VOZ_*`
  keep working.

### Costs and limits

- Two names coexist: the product is V, while the package, data folders,
  environment variables and format id still say `voz`. Documentation must
  explain this once, clearly.
- `v` can be shadowed by vlang or other tools; the doctor check mitigates but
  does not prevent it, and `voz` must remain documented as the fallback.
- The `Iniciar-*` wrappers and the `voz` alias are extra surface to maintain
  until they are removed.
- The distribution name `voz-transcriber` no longer matches the product; this
  is deferred, not solved.

## Alternatives considered

| Alternative | Why it was not chosen |
| --- | --- |
| A. Rename only brand and repository; keep `voz` as the command | Low risk, but users would see "V" in the UI and type `voz` in the terminal; brand confusion in the medium term |
| **B. Rename brand and command, keep `voz` as alias and all internals (chosen)** | Changes what users see without touching their data or export format; lets the next phase be decided with real usage |
| C. Full internal migration (package, XDG paths, database, format id, env vars, command) in one go | High cost (about 1,400 import lines, path and database migration, backup and migration tests), real risk of losing the owner's data, breaks already-exported JSON, and adds nothing the end user notices |

Variant rejected within B: accepting `V_*` alongside `VOZ_*`. A one-letter
prefix such as `V_` is too likely to clash with unrelated variables in a user's
environment.

## Compatibility table

| Surface | Before | After this ADR | Compatibility |
| --- | --- | --- | --- |
| Product name | VOZ | V ("Local Voice AI") | Historical text keeps VOZ |
| Repository | `MarshallGomez1103/voz` | `MarshallGomez1103/V` | GitHub redirects the old URL |
| CLI command | `voz` | `v` | `voz` alias kept at least until the first public release |
| Python package | `voz` | `voz` | Unchanged |
| Distribution | `voz-transcriber` | `voz-transcriber` | Unchanged; revisit before first release |
| Data directories | `~/.local/share/voz/`, `~/.cache/voz/`, `~/.config/voz/` | same | Unchanged; no data moved |
| Database file | `voz.sqlite3` | `voz.sqlite3` | Unchanged |
| Export format id | `voz.transcript` v1 | `voz.transcript` v1 | Unchanged; existing exports stay valid |
| Environment variables | `VOZ_*` | `VOZ_*` | Unchanged; no `V_*` alias |
| Launchers | `Iniciar-Windows.bat`, `Iniciar-Mac.command`, `Iniciar-Linux.sh` | `Start-V-Windows.bat`, `Start-V-macOS.command`, `start-v-linux.sh` | `Iniciar-*` kept as wrappers for one release |
| Desktop entry | `Name=VOZ` | `Name=V` | Regenerated by the app (V1-05) |
| UI, `<title>`, PWA manifest | VOZ | V | Display only |
| `authors` in `pyproject.toml` | `VOZ contributors` | `V contributors` | Metadata only |
| Project URLs | `.../voz` | `.../V` | Metadata only |
| Flatpak app id | `dev.voz.Voz` (provisional) | `io.github.marshallgomez1103.v` (V10-04) | Separate Flatpak data namespace; no automatic migration |
| CHANGELOG history and ADR-0001 to ADR-0008 | VOZ | VOZ | Not rewritten |

## Implementation snapshot (2026-10-11)

This ADR records a decision; the implementation lands in later slices and is
**planned** until then.

| Item | Code or slice |
| --- | --- |
| Data directory name | `src/voz/infrastructure/paths.py` (`APPLICATION_DIRECTORY = "voz"`) |
| Database file name | `src/voz/bootstrap.py` (`DATABASE_FILENAME = "voz.sqlite3"`) |
| Export format id | `src/voz/application/export/json_canonical.py` (`CANONICAL_FORMAT`) |
| `v` command, `voz` alias, vlang warning | done, V1-02 (`pyproject.toml` `[project.scripts]`, `voz doctor` check `comando v`) |
| Brand in the UI | **planned**, V1-03 |
| New launchers and wrappers | **planned**, V1-04 |
| Desktop entry `Name=V` | **planned**, V1-05 |
| English README and docs | **planned**, V1-06 to V1-09 |
| `authors` and project URLs | done, V1-10 and V1-11 (`pyproject.toml`) |

## Flatpak identity (2026-10-16)

The V packaging recipes use `io.github.marshallgomez1103.v` consistently in the
manifest, metainfo, desktop entry and icon. This identifier names an application;
it does not create a website or change the loopback server address.

Flatpak assigns each application its own XDG namespace. The new identifier has
separate storage from the prototype `dev.voz.Voz`. No existing data is moved or
deleted, and the internal `voz/` directory names remain unchanged. Packaging
staging is tested locally; complete package builds and native Windows/macOS
verification remain pending.

## Verification

This decision is respected when:

- `APPLICATION_DIRECTORY`, `DATABASE_FILENAME` and `CANONICAL_FORMAT` keep
  their current values;
- no code reads a `V_*` environment variable;
- after V1-02, both `v` and `voz` start the same entry point, and
  `voz doctor` reports a foreign `v` earlier in `PATH`;
- no slice moves, renames or deletes files under the user's `voz/` data
  directories;
- any change to the items above comes with a new ADR and a tested data
  migration.
