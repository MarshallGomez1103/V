# ADR-0012: Nested folders inside a project

- Status: Proposed
- Date: 2026-10-28
- Owners: V maintainers
- Scope: how recordings (and therefore their transcripts) are organized inside a
  project: the folder tree, its storage, migration, HTTP contract and library UI.
  Nothing in this ADR exists in the code yet; everything it describes is
  **planned**.
- Related: [ADR-0001](0001-modular-monolith.md) (boundaries),
  [ADR-0002](0002-sqlite-persistence.md) (SQLite, Alembic, XDG),
  [ADR-0003](0003-ffmpeg-ingestion.md) (immutable originals)
- Diagrams: [containers](../architecture/02-contenedores.md),
  [components](../architecture/03-componentes.md)

## Context

A person with many recordings (for example a language course split into
cuts, classes and topics) needs to group them. Today the library is a flat list
with one row per project, ordered by recent activity
(`src/voz/application/library.py`, `ListLibrary`;
`src/voz/infrastructure/persistence/library.py`, `SqliteLibraryReader`).

Facts that shape the decision:

- **A project already can hold many recordings.** `media_assets.project_id` and
  `transcription_jobs.media_asset_id` are plain foreign keys
  (`src/voz/infrastructure/persistence/schema.py`, tables `media_assets` and
  `transcription_jobs`), the upload route takes a `project_id`
  (`src/voz/interfaces/api/media.py`, `create_media_router`) and deleting a
  project erases its whole directory
  (`src/voz/application/projects.py`, `DeleteProject`).
- **The product treats a project as one recording.** The import screen creates a
  new project per file (`apps/web/src/components/NewProjectCard.tsx`) and the
  library shows the project's latest recording and job
  (`src/voz/infrastructure/persistence/library.py`, `SqliteLibraryReader`). So
  the data model allows a "project that contains recordings" and the UI does not
  expose it yet.
- **Files must not move.** Originals and derivatives live under
  `projects/<project>/originals/` and `.../derivatives/`
  ([ADR-0002](0002-sqlite-persistence.md)); they are immutable
  ([ADR-0003](0003-ffmpeg-ingestion.md)).
- **Speech synthesis is not project-scoped.** `synthesis_jobs` has no
  `project_id` (`src/voz/infrastructure/persistence/schema.py`, table
  `synthesis_jobs`).
- SQLite runs with `foreign_keys=ON`
  (`src/voz/infrastructure/persistence/database.py`) and every schema change
  goes through Alembic with an automatic backup of a database that is behind
  head (`src/voz/infrastructure/persistence/migrate.py`, `upgrade_to_head`).

Decisions already taken and not reopened here: folders are
**nested** (project, then folders, then subfolders); each recording lives in one
folder or at the project root; folders and recordings can be moved and renamed;
the migration is a normal SQLite migration with a backup.

## Decision

### 1. Vocabulary and scope

- A **project** in this ADR is the existing `Project`. A folder tree belongs to one
  project; there is no folder outside a project.
- A **recording** is the existing `MediaAsset`. The filing unit is the media
  asset: its jobs, transcript, speakers and segments follow it, because they all
  reference it. Nothing is stored on the transcript.
- Folders are **virtual**. They are rows, never directories. No file is moved,
  copied or renamed when a folder is created, renamed, moved or deleted, so
  immutable originals stay untouched and no host path is involved.
- **Moves happen inside one project.** Moving a recording to another project
  would require moving its files on disk; it is out of scope.

### 2. Data model

New table `folders` (migration `0012_project_folders`) and one new nullable column:

| Column | Type | Rule |
| --- | --- | --- |
| `folders.id` | `String(36)` | Primary key, UUID. |
| `folders.project_id` | `String(36)` | Not null, foreign key to `projects.id` `ON DELETE CASCADE`, indexed. |
| `folders.parent_id` | `String(36)` | Null means the project root; foreign key to `folders.id` `ON DELETE CASCADE`. |
| `folders.name` | `Text` | Not null; the trimmed name as typed. |
| `folders.name_key` | `Text` | Not null; `casefold(NFC(name))`, the uniqueness key. |
| `folders.created_at` | `String(40)` | Not null, ISO 8601 with time zone, like the other tables. |
| `media_assets.folder_id` | `String(36)` | Null means the project root; foreign key to `folders.id` `ON DELETE SET NULL`, indexed. |

Constraints:

- `CHECK (parent_id IS NULL OR parent_id != id)`.
- **Unique name per parent.** SQLite treats `NULL` values as distinct in a unique
  index, so root-level duplicates would slip through a single
  `UNIQUE (parent_id, name_key)`. Two partial unique indexes are used instead:
  `UNIQUE (project_id, name_key) WHERE parent_id IS NULL` and
  `UNIQUE (parent_id, name_key) WHERE parent_id IS NOT NULL`. Names are
  compared case-insensitively and after Unicode normalization, so "Corte 1" and
  "corte 1" collide.
- **Same project.** A folder's parent and a recording's folder must belong to the
  recording's or folder's own project. This is enforced in the use case (the
  composite foreign key that would express it cannot be added to an existing
  SQLite table without rebuilding `media_assets`).
  **ponytail:** use-case enforcement; ceiling: a composite
  `(project_id, folder_id)` foreign key through a table rebuild if a second
  writer ever appears.

Why the delete actions are what they are: deleting a project already cascades to
`media_assets` and now also to `folders`. A self-referencing `RESTRICT` could
fail halfway through that cascade, so the tree uses `CASCADE`. The emptiness rule
below is enforced by the use case, so the database `CASCADE` is only reached by
project deletion. `media_assets.folder_id` uses `SET NULL` as a safety net: if a
bug ever removed a folder row, the recording would reappear at the root, never
disappear.

### 3. Limits

- **Maximum depth: 5 levels.** A root-level folder has depth 1. The usual
  case (course, cut, class, topic) needs about 4; 5 leaves room for one
  extra level. A bound is needed because the tree is rendered in the UI and
  walked in memory, and unbounded nesting only produces unusable breadcrumbs.
- **Maximum 500 folders per project.** A hand-organized library does not reach
  it, and it keeps "load the whole tree" a single cheap query.
- Names: 1 to 120 characters after trimming, no control characters (same rules as
  project names in `src/voz/application/projects.py`, `normalize_project_name`). A folder name may
  contain `/`: names never become paths.
- Order: folders are listed by `name_key`, then `id`. There is no manual
  ordering.

The tree is validated in memory: the use case loads the project's folders (at
most 500 rows) and checks cycles and depth in Python. No recursive SQL is used.
Create, rename and move run in one transaction so the checks and the write see
the same tree.

### 4. Operations and rules

- **Create** in a parent (or the root): name valid, unique among siblings, parent
  in the same project, resulting depth at most 5, folder count below the limit.
- **Rename**: same name rules; a rename that changes only the case is allowed.
- **Move a folder**: the new parent must not be the folder itself or one of its
  descendants, must be in the same project, and the deepest descendant must still
  fit within depth 5 after the move. The name must be free in the destination.
- **Move a recording**: to any folder of its own project or to the root. Allowed
  while a job is running: folders do not affect files.
- **Delete a folder: reject if it is not empty.** A folder with subfolders or
  recordings answers 409 `folder_not_empty` and nothing changes. The person moves
  or deletes the contents first. Moving the contents to the root automatically
  was considered and rejected: it silently reorganizes a library the person
  built by hand and cannot be undone with a single action. Rejecting is
  predictable and matches how `DELETE /api/projects/{id}` already refuses while
  work is active (`src/voz/interfaces/api/projects.py`, `project_busy`). Deleting
  a folder deletes no file and no transcript.
- **Delete a project**: unchanged; it removes its folders with it.

### 5. HTTP contract

All paths are under `/api`. Errors use the existing
`{"detail": {"code", "message"}}` shape and carry no paths. Identifiers are UUIDs.

| Method and path | Body | Success | Notes |
| --- | --- | --- | --- |
| `GET /projects/{project_id}/folders` | none | 200 `{"folders": [Folder]}` | Flat list; the client builds the tree. |
| `POST /projects/{project_id}/folders` | `{"name", "parent_id"?}` | 201 `Folder` | `parent_id` absent or `null` means root. |
| `PATCH /folders/{folder_id}` | `{"name"?, "parent_id"?}` | 200 `Folder` | At least one field. `"parent_id": null` moves to the root; an absent key leaves it unchanged. |
| `DELETE /folders/{folder_id}` | none | 204 | Requires the header `X-VOZ-Action: delete-folder`, like other destructive routes. |
| `PUT /media/{media_asset_id}/folder` | `{"folder_id": uuid or null}` | 200 `{"media_asset_id", "folder_id"}` | Moves a recording. |
| `GET /projects/{project_id}/recordings` | none | 200 `{"recordings": [Recording]}` | Every recording of the project with `folder_id`; the client filters by folder. |

`Folder` is `{"id", "project_id", "parent_id", "name", "depth", "created_at"}`.
`Recording` is `{"media_asset_id", "folder_id", "filename", "media_type",
"duration_ms", "created_at", "latest_job"}`, where `latest_job` has the same
shape as in `GET /api/library`. `GET /api/library` keeps its shape and gains
`recording_count` (an additive field).

Stable error codes:

| Code | Status | When |
| --- | --- | --- |
| `project_not_found` | 404 | Unknown project (existing code). |
| `folder_not_found` | 404 | Unknown folder. |
| `media_asset_not_found` | 404 | Unknown recording (existing code). |
| `folder_name_invalid` | 422 | Blank, too long or with control characters. |
| `folder_name_taken` | 409 | A sibling already has that name. |
| `folder_too_deep` | 422 | The result would exceed 5 levels. |
| `folder_cycle` | 422 | Moving a folder under itself or a descendant. |
| `folder_project_mismatch` | 422 | Parent folder or target folder belongs to another project. |
| `folder_limit_reached` | 409 | The project already has 500 folders. |
| `folder_not_empty` | 409 | Delete refused. |
| `folder_delete_forbidden` | 403 | Missing `X-VOZ-Action` header. |

### 6. Layers

- Domain: `Folder` entity (`src/voz/domain/entities/folder.py`), no framework
  imports, with the name rules.
- Application: `FolderRepository` port; use cases `CreateFolder`, `RenameFolder`,
  `MoveFolder`, `DeleteFolder`, `ListFolders`, `MoveRecording`, `ListRecordings`
  in `src/voz/application/folders.py`; they depend on ports only.
- Infrastructure: `SqliteFolderRepository` and the schema in
  `src/voz/infrastructure/persistence/`; a read model for recordings next to the
  library reader.
- Interfaces: `src/voz/interfaces/api/folders.py` as a thin router, mounted in
  `src/voz/bootstrap.py` with the other routers.

### 7. Migration and rollback

- Migration `0012_project_folders` creates `folders` and its two partial unique
  indexes and adds `media_assets.folder_id`. Existing rows get `NULL`, that is,
  every existing recording stays at the root of its project: no data is moved or
  rewritten.
- On the first start after the upgrade, `upgrade_to_head` copies the database
  with SQLite's online backup API into the state directory's `backups` folder
  before migrating and keeps the five most recent copies
  (`src/voz/infrastructure/persistence/migrate.py`, `KEEP_BACKUPS`). If the copy
  fails, nothing is migrated.
- `downgrade()` drops the index, the column and the table. It is for tests and
  for development: the application never downgrades on its own.
- **Rollback procedure:** stop V, replace `voz.sqlite3` with the backup named
  `voz-<previous revision>-<timestamp>.sqlite3`, start the previous version.
  Folders created after the upgrade are lost; recordings, transcripts and files
  are unaffected because nothing on disk changed.
- `op.add_column` with a foreign key can fail on SQLite; the migration is written
  and tested on a populated database for both directions, using Alembic batch
  mode if needed. It is an implementation detail to confirm, not a design
  change. This is a database schema change and needs maintainer approval before
  release.

### 8. User interface

Planned behaviour, using the existing Carbon components and the English and
Spanish catalogs:

- **Home** keeps one card per project and shows the recording count.
- **Project view** (new): a breadcrumb, a folder tree on the left and the
  recordings of the selected folder on the right. The tree uses Carbon's
  `TreeView` (present in the installed `@carbon/react`), which provides the
  ARIA tree roles and arrow-key navigation; "All recordings" and "Project root"
  are the first entries.
- **Create and rename**: a button "New folder" and an inline rename; `F2` renames
  the focused folder and `Delete` asks for confirmation. Errors from the
  contract above are shown with messages from the i18n catalogs.
- **Move**: by menu and keyboard only. A recording row has an overflow menu
  "Move to..." that opens a dialog with the same tree as a single-selection
  picker (disabling folders that would exceed the depth limit and the folder's
  own subtree); the same dialog moves a folder. Drag and drop is not part of this
  decision: a pointer-only gesture cannot be the only way to move something.
- **Import** gains a destination: a new project, or an existing project and
  folder.
- Focus returns to the moved item's new position and the change is announced to
  assistive technology.

### 9. What is not done

- No cross-project moves and no copying of recordings.
- No folder for speech synthesis results (`synthesis_jobs` is not
  project-scoped).
- No sharing, permissions, colors, icons, tags or manual ordering.
- No folder-aware export or search in this ADR (a later change can add a filter
  to the library).
- No filesystem mirror of the tree.
- No automatic folder creation from file names.

## Positive consequences

- One table and one nullable column: small diff, reversible, and no file or
  existing row changes.
- Rows for existing libraries stay valid: everything is at the root.
- The same bounded tree check serves the API, the UI picker and tests.
- Because folders are virtual, they cost nothing on disk and are safe on every
  supported platform.

## Costs and limits

- The library home must stop assuming one recording per project, and the import
  flow must be able to add a recording to an existing project. Both are product
  changes beyond the folders themselves.
- Case-insensitive uniqueness rejects names that differ only in case.
- Cross-project organization needs re-importing the recording.
- The same-project rule lives in the use case, not in the schema.
- Deleting a populated folder takes two steps by design.

## Alternatives considered

### A new top-level entity above projects

A `workspace` or `collection` that contains projects, keeping one recording per
project. Rejected: it adds a fourth level of vocabulary, needs a second
tree-of-containers decision, and the existing project already holds many
recordings.

### Folders as directories on disk

Rejected: moving or renaming would touch immutable originals, expose host paths
and behave differently per platform
([ADR-0002](0002-sqlite-persistence.md), [ADR-0003](0003-ffmpeg-ingestion.md)).

### Materialized path or closure table

Storing the full path string or all ancestor pairs makes subtree queries cheap.
Rejected: with at most 500 folders per project the whole tree is read and checked
in memory, and a path column must be rewritten for the entire subtree on every
rename or move.

### Move to the root on delete

Rejected for the reasons in section 4.

### Tags or labels instead of a tree

Rejected: nested folders were the requirement, and tags do not express
"inside this course, inside this cut".

### Moving transcripts instead of recordings

Rejected: a transcript is derived from a job of a recording, and a recording can
have several jobs. Filing the recording keeps one source of truth.

## Current evidence (2026-10-28)

| Requirement | Code or test |
| --- | --- |
| A project holds several recordings | `src/voz/infrastructure/persistence/schema.py` (`media_assets.project_id`, `transcription_jobs.media_asset_id`); upload takes a project id in `src/voz/interfaces/api/media.py` (`create_media_router`) |
| The library assumes one recording per project | `src/voz/infrastructure/persistence/library.py` (`SqliteLibraryReader`) |
| Migrations back up first | `src/voz/infrastructure/persistence/migrate.py` (`backup_database`, `upgrade_to_head`) |
| `foreign_keys=ON` | `src/voz/infrastructure/persistence/database.py` |
| Folder tables, routes, UI | **planned**, none exist |

## Verification

This decision is respected when:

- the migration upgrades and downgrades a populated database, with
  `foreign_keys=ON`, and deleting a project that has nested folders and
  recordings succeeds;
- every rule in section 4 has a failing-first test at the use-case level and a
  contract test for its error code;
- no response contains an absolute path and no file under the data directory
  changes when a folder is created, renamed, moved or deleted;
- the UI can create, rename, move and delete a folder using only the keyboard,
  in English and Spanish, with focus and announcements verified;
- the library home still lists projects that never received a recording.

**Review criterion:** if recordings must move between projects, or the tree needs
more than 500 folders or sharing, replace this ADR instead of stretching it.
