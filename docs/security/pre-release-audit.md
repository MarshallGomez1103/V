# Repository security audit

Date: 2026-10-20. This updates the earlier S16.19 audit; its earlier counts and
release-readiness conclusions do not describe the current checkout.
The working tree, dependency-audit evidence and redistribution notices were
rechecked on 2026-10-21; the historical scan and focused tests below were not
repeated.

## Scope and result

The audit covered the Git index, existing tracked files, non-ignored new files,
and every blob reachable from local branches, remote-tracking references and
tags. The historical snapshot contained **118 commits, 3,587 objects and 2,076
blobs**. Ignored files were inventoried by name and filesystem metadata, without
reading their contents. Worktree registrations were inspected without changing
or pruning them.

[`scripts/audit-secrets.sh`](../../scripts/audit-secrets.sh) completed with
**0 HIGH and 44 REVIEW findings**. The REVIEW matches were inspected: they are
synthetic credentials, example URLs and invented host paths in tests, including
tests that verify redaction. A separate scan of reachable blobs found no
additional credential or personal-path candidate outside tests. These are
heuristic results, not a guarantee that the repository contains no secret or
vulnerability.

| Check | Observation |
| --- | --- |
| Private context | `.ai/` is ignored, absent from the index and absent from reachable history. References to private research were removed from public documentation and replaced with public sources where needed. |
| Credentials and private paths | Detected candidates were test literals; no actual credential or personal host path was identified in shipped source or documentation. Matched values are not reproduced here. |
| Models, recordings and databases | No model weights, private recording or runtime database was identified among the tracked and non-ignored files. Six documented synthetic tone files remain intentional fixtures. |
| Large blobs | No reachable historical blob exceeds 1 MiB. This is an inventory threshold, not a safe-file-size rule. |
| Symlinks | The current index contains no symlink. Local worktrees and their internal Git paths are not application deliverables. |
| Authorship | Reachable author and committer identities use one GitHub `noreply` identity. The public history exposes that attribution and the commit messages. |
| Binary assets | Fixtures have a size/hash/provenance manifest. PNG metadata was inspected separately; no personal-path, credential or GPS marker was identified. A contact-sheet review covered the 22 screenshots; no private path or credential was identified visually. Demo content is described in the README. This does not establish the provenance of every depicted name or waveform. |

## Exclusion corrections

The previous `!tests/fixtures/**` exception overrode secret, model and media
exclusions inside that directory. It now allows only the six synthetic media
files listed in [fixture licenses](../fixtures-licenses.md). Python helpers and
JSON fixtures remain ordinary source files; a new binary fixture requires an
explicit exception and documented provenance.

Additional exclusions cover the application's `secrets.toml`, common server-token
filenames, SQLite journal/WAL/SHM sidecars, binary model weights, AppDir trees,
AppImage files and Flatpak bundles. Flatpak reference and repository configuration
files remain eligible as source. Root-level `transcript.*`, `transcript-*` and
`transcript_*` exports are excluded without hiding the legitimate
`src/voz/domain/entities/transcript.py` module.

Forty-nine assertions checked representative excluded paths, legitimate source
and fixtures, and the index separately. No existing tracked file is hidden by
the resulting rules when checked with `git check-ignore --no-index`.
**An ignore rule never removes content already tracked or committed.** Forced
addition can bypass the rules; arbitrary filenames can also contain private data.

Font and JavaScript redistribution notices were also checked. The resulting
frontend includes the original IBM Plex and Roboto Flex OFL notices and a
JavaScript notice aggregate derived from the rendered-module graph (27 package
owners and injected-helper packages). Original upstream LICENSE/NOTICE text is
preserved; the aggregate is not a full dependency SBOM.

## Focused security verification

Manual code review covered server authentication, Host validation, response
headers, credential-file handling, bounded model uploads and model archive
extraction. The existing tests for these boundaries and synthetic-media
integrity completed with **301 passed, one deprecation warning**. They ran with
a temporary HOME/XDG environment, a separate network namespace, read-only source,
two CPU threads and no GPU. No live provider, downloaded model or personal data
was needed for these tests.

This focused review does not replace the full application checks or an
independent penetration test. Security reports for experimental features remain
in scope; a child-process model loader is not
an operating-system permission sandbox. See [SECURITY.md](../../SECURITY.md).

## Dependency advisory snapshot: 2026-10-20

The initial database queries identified three affected packages. They were
updated within their existing release lines, with no new dependency names:

| Package | Previous version | Patched version | Advisory and relevant scope |
| --- | --- | --- | --- |
| Mako | 1.4.1 | 1.4.2 | [GHSA-5639-2j2p-m4mx](https://github.com/sqlalchemy/mako/security/advisories/GHSA-5639-2j2p-m4mx): Windows template-path traversal. V uses Mako through Alembic's trusted migration templates; no attacker-controlled `TemplateLookup` route was identified. |
| certifi | 2026.7.22 | 2026.10.19 | [GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2): affected CA trust material. Relevant to optional model downloads through clients using certifi; an updated top-level package does not update copies vendored by other software. |
| Vite | 8.2.0 | 8.2.4 | [GHSA-698v-4r3x-3vcv](https://github.com/vitejs/launch-editor/security/advisories/GHSA-698v-4r3x-3vcv), [GHSA-r825-w8mm-5pxw](https://github.com/vitejs/launch-editor/security/advisories/GHSA-r825-w8mm-5pxw), [GHSA-587h-7wmj-h5pm](https://github.com/vitejs/launch-editor/security/advisories/GHSA-587h-7wmj-h5pm): development-server editor launching on Windows or WSL. This server is separate from V's packaged FastAPI runtime. |

After these changes, `npm audit --json --ignore-scripts` completed with exit
code 0 and **zero reported vulnerabilities**, including development dependencies.
An [OSV batch query](https://google.github.io/osv.dev/post-v1-querybatch/)
for **54 exact PyPI package versions in `uv.lock` returned zero matches**. Both
results were checked against the hashes of the current lockfiles.

These are database snapshots, not exploit-reachability analysis or a guarantee
against future advisories. The OSV query does not establish which distributions
are installed in an environment or inspect vendored copies inside pip,
ensurepip, an operating system or a portable artifact. Each final artifact
requires its own inventory and notices. The JavaScript notice aggregate was
refreshed against the installed Vite 8.2.4 originals; all 29 original notice files
for the 27 package owners/helpers were preserved exactly.

## Remaining checks

- Review the final staged diff, including newly generated assets and packaging
  notices, after all changes are finished. Repeat the scan on that exact state.
- Verify third-party redistribution notices in each binary artifact. The
  project's MIT license does not relicense dependencies, fonts or model weights.
- Repeat dependency database queries if the lockfiles or
  advisory data change; inspect installed and vendored distributions in each
  final artifact separately from the lockfile results above.
- Verify that GitHub Private Vulnerability Reporting is enabled in the
  repository settings. A security policy and issue template cannot activate it.
  Ordinary issues and attachments remain public; follow the
  [reporting and maintainer setup instructions](../../SECURITY.md#how-to-report).
- Review scope and permissions before pushing or releasing. This audit did not
  change remote settings or publish anything.

## Repeatable local checks

From the repository root:

```bash
bash scripts/audit-secrets.sh
bash scripts/audit-secrets.sh --tree-only
git ls-files .ai
git log --all --oneline -- .ai
git check-ignore -v .ai/
git ls-files --cached --others --exclude-standard
git diff --cached --check
```

Review every finding, including those classified REVIEW. The scanner's
expressions target recognizable formats and literal assignments; they miss
arbitrary passwords, obfuscated values and secrets embedded in binary payloads.
Reachable history is included; reflogs and unreachable objects are not, since
they are not sent by a normal push. Local ignored files are outside what a push
sends and were not content-scanned. Neither static analysis nor passing
tests proves complete security or authorizes a public release.
