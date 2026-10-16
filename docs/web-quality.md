# Web asset budgets

The shipped web bundle has fixed byte budgets. Run from the repository root:

```sh
.venv/bin/python scripts/check-web-budget.py
.venv/bin/python scripts/check-web-budget.py --json
```

The command uses only the Python standard library. It reads the existing bundle
without building, downloading or modifying files. To inspect another build:

```sh
.venv/bin/python scripts/check-web-budget.py --static-dir ./web-build --json
```

## Limits and measurement

One KiB is 1024 bytes. Both limits must pass; equality is allowed.

| Asset | Raw limit | Gzip limit |
| --- | ---: | ---: |
| Entry JavaScript | 400 KiB | 128 KiB |
| Entry CSS | 700 KiB | 80 KiB |
| ModelManager JavaScript chunk | 32 KiB | 12 KiB |

The entry JavaScript is the single module script referenced by `index.html`.
Entry CSS is the referenced `index.css` or `index-*.css` stylesheet; other
stylesheets are checked for existence but are not added to that byte budget.
The ModelManager chunk is resolved from its references in the entry JavaScript,
rather than selected from potentially stale files in the assets directory.
Missing or ambiguous entries fail validation.

Gzip sizes use `gzip.compress` at level 9 with `mtime=0`, independently for each
asset. This avoids timestamps and filenames in the measurement. Compressed
sizes can differ between Python/zlib versions; these values do not assert that
the HTTP server uses gzip.

## Measured shipped assets

Measurement on 2026-10-16 using the commands above returned `web_budget_ok`
(exit code 0):

| Asset under `src/voz/static/` | Raw bytes | Gzip bytes |
| --- | ---: | ---: |
| `assets/index-Bmpdm_nz.js` | 382,914 | 113,016 |
| `assets/index-BtSYZahh.css` | 650,882 | 67,426 |
| `assets/ModelManager-BZ_iwJI-.js` | 24,473 | 7,907 |

These are measurements of the existing shipped files, not of a newly generated
build. Rerun the command after replacing the bundle.

## Validation and exit codes

The checker validates `index.html` and all its `src`, `href` and `poster`
references, plus the selected ModelManager JavaScript references. Referenced
files must exist and resolve inside the static directory, including after
symlink resolution. Remote URLs, protocol-relative URLs, traversal, percent
escapes, backslashes and base URL overrides are rejected. Local paths may be
relative or start with `/` to refer to the static root.

The checker does not recursively parse JavaScript imports, CSS URLs or the web
manifest. ModelManager discovery follows the emitted `ModelManager-*.js` naming
contract; a different bundler naming scheme requires updating discovery.

| Exit code | JSON status | Meaning |
| --- | --- | --- |
| 0 | `ok` | All three assets meet both limits. |
| 1 | `budget_exceeded` | At least one raw or gzip limit was exceeded. |
| 2 | `invalid` | Input is missing, unsafe, ambiguous or unreadable. |

JSON output includes each asset's relative filename, measurements, limits and
`within_budget` result. Invalid input returns code `web_budget_invalid` and a
fixed message without host paths or untrusted input.

## Limits of the evidence

These checks bound file sizes. They do not measure interactive latency,
rendering, runtime memory, network throughput or loading time, and they provide
no accessibility, WCAG conformance or Lighthouse score evidence.

## Browser accessibility checks

On 2026-10-16, Chromium exercised Home, New transcription, Speak, Models and
Providers in Carbon and Material 3, light and dark themes, and Spanish and English:
40 combinations at a 390 px viewport. The browser accessibility tree exposed a
nonempty name for every visible interactive control in the checked roles
(button, link, textbox, combobox, checkbox, radio, slider, spinbutton and
searchbox). Each view had exactly one visible `h1`, Tab reached a control,
and the document and body stayed within the viewport width.

To repeat the structural checks, open each route (`#/`, `#/nueva`, `#/speak`,
`#/modelos`, `#/proveedores`), select each appearance/language combination,
and use Chromium's Accessibility panel to inspect control names. Use keyboard
Tab and a 390 px responsive viewport to check focus and horizontal overflow.
The synthesis view was exercised with a deterministic local test engine;
these checks do not establish model quality or native inference performance.

This is a bounded structural review without an added audit dependency.
It does not establish full WCAG conformance: screen-reader operation, contrast,
all focus sequences, job/transcript states and every assistive technology remain
outside this check. The byte-budget command does not perform these browser
checks.
