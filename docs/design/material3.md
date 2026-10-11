# Material 3 as an alternative design for V

Status: research closed (C1) and implementation done (C2/C3, section 9).
Research date: October 3, 2026.

## 1. Decision

The maintainer asked for Material 3 as a **selectable alternative design** ("Design
system: Carbon | Material 3" in Settings), not as a migration. Carbon remains the
default design and remains rectangular.

Implementation decision: **an M3 skin over the same Carbon components**, enabled
with `[data-design="m3"]` on `<html>`. An SCSS layer remaps the `--cds-*` tokens to
M3 color roles, the roles are generated at runtime with
`@material/material-color-utilities` from the chosen accent, and typography,
shapes, elevation and state layers change only in that mode. The app is not
rewritten, tests are not duplicated, and `@material/web` is not added except for a
specific control that the skin cannot solve (see 6.9).

What is not done:

- No migration to MUI (it still implements Material Design 2, see 4.4).
- `@material/web` is not adopted as the basis of the interface (maintenance mode,
  4.1).
- The `weppa-cloud` MCP is not installed (section 5).
- Nothing is loaded from a CDN or from Google Fonts: the bundle remains offline.

## 2. Sources consulted

All consulted on 2026-10-03. The numeric values quoted come from the tokens of the
official repository (`tokens/versions/v0_192/*.scss` of `material-web`), not from
memory.

| Source | What it provides |
| --- | --- |
| https://m3.material.io/ (color, typography, shape, elevation, states, motion) | The M3 specification. The site renders with JavaScript and the reading tool did not extract the text; the values were verified against the official `material-web` tokens, which are their literal translation. |
| https://github.com/material-components/material-web (README, `docs/`, `tokens/`) | Project status, components, CSS tokens, browser support, sizes. |
| https://github.com/material-components/material-web/discussions/5642 | Official announcement of maintenance mode (2024-06-10). |
| https://registry.npmjs.org (`@material/web`, `@material/material-color-utilities`, `@lit/react`, `lit`, `@mui/material`, `@fontsource/*`) | Versions, dates, licenses, dependencies. |
| https://github.com/material-foundation/material-color-utilities | API for generating schemes from a seed color. |
| https://github.com/weppa-cloud/material3-mcp-server and its npm package | Evaluation of the MCP (section 5). |
| https://github.com/mui/material-ui/issues/29345 and https://mui.com/blog/2026-and-beyond/ | State of M3 in MUI. |
| https://m3.material.io/blog/m3-expressive-motion-theming | M3 Expressive motion system. |
| Local test (scratchpad, not part of the repo) | Real API of `material-color-utilities` 0.4.0, contrasts, bundle size, font weights. |

## 3. Material 3 fundamentals relevant to V

### 3.1 Color: roles and dynamic color

M3 does not use a fixed palette but **semantic roles** assigned to tones of five key
colors (primary, secondary, tertiary, neutral, error). Each role has its `on-*`
with accessible contrast. The CSS tokens follow the pattern
`--md-sys-color-<role>`.

`material-web` roles (the ones that matter here):

- Accent: `primary`, `on-primary`, `primary-container`, `on-primary-container`, and
  the same for `secondary`, `tertiary` and `error`.
- Surfaces: `background`, `surface`, `surface-dim`, `surface-bright`,
  `surface-container-lowest | low | (no suffix) | high | highest`, `on-surface`,
  `on-surface-variant`, `surface-variant`.
- Borders: `outline`, `outline-variant`.
- Inverse and others: `inverse-surface`, `inverse-on-surface`, `inverse-primary`,
  `scrim`, `shadow`, `surface-tint` and the `*-fixed` variants.

The surface hierarchy (`surface-container-*`) replaces the tint elevation of old
M3: depth is expressed with surface tones, not with strong shadows.

**Dynamic color**: given a seed color, the algorithm (HCT space) generates tonal
palettes and assigns each role to a different tone in light and dark. The contrast
level (0 = standard, up to 1 = high) is passed as a parameter and recalculates the
tones.

### 3.2 Typography

A scale of 15 styles (display, headline, title, body, label × large/medium/small)
with five properties each: family, size, line height, weight and tracking. Default
values verified in `material-web`:

| Style | Size / line height | Tracking |
| --- | --- | --- |
| body-large | 1 rem / 1.5 rem | 0.03125 rem |
| body-medium | 0.875 rem / 1.25 rem | 0.015625 rem |
| body-small | 0.75 rem / 1 rem | 0.025 rem |
| display-large | 3.5625 rem (57 px) | per token |

Default typeface: **Roboto** with three weights (400, 500, 700).
`--md-ref-typeface-brand` and `--md-ref-typeface-plain` select the family.
`material-web`'s documentation loads Roboto from Google Fonts; in V that is **not
possible** (offline), so it is bundled.

### 3.3 Shapes

`material-web`'s corner scale (verified values):

| Token | Value |
| --- | --- |
| `--md-sys-shape-corner-none` | 0 px |
| `…-extra-small` | 4 px |
| `…-small` | 8 px |
| `…-medium` | 12 px |
| `…-large` | 16 px |
| `…-extra-large` | 28 px |
| `…-full` | 9999 px (pill/circle) |

M3 convention: buttons, chips and toggles `full`; cards `medium` (12 px); dialogs
`extra-large` (28 px); filled text fields with an `extra-small` (4 px) top corner;
outlined fields `extra-small`. M3 Expressive adds an expanded library of shapes
and morphing between them; `material-web` does not implement it (its roadmap says
the expansion of shape and motion tokens "was being added" before the pause).

### 3.4 Elevation

Six levels (0 to 5). At rest, 0 to 3 are used; 4 and 5 are left for interaction
states (hover, drag). `material-web` exposes them as `--md-elevation-level: 0..5`
on an `md-elevation` element. Shadows are drawn with two layers (key and ambient)
with a vertical offset that grows per level (0, 1, 1, 1, 2 and 4 px according to
the comments in `_elevation.scss`). In dark mode the level is perceived mostly
through the tone of `surface-container-*`.

### 3.5 State layers

A semi-transparent layer of the content color over the container indicates the
state. Opacities verified in `_md-sys-state.scss`:

| State | Opacity |
| --- | --- |
| hover | 0.08 |
| focus | 0.12 |
| pressed | 0.12 |
| dragged | 0.16 |

`material-web`'s focus ring uses 3 px and the `secondary` role by default. Disabled
states use `on-surface` at 38 % (content) and 12 % (container).

### 3.6 Motion

`material-web` tokens: durations `short1..4` = 50, 100, 150, 200 ms; `medium1..4` =
250, 300, 350, 400 ms; `long1..4` = 450 to 600 ms; `extra-long1..4` = 700 to 1000
ms. Curves: `standard`, `standard-accelerate`, `standard-decelerate`, `emphasized`,
`emphasized-accelerate`, `emphasized-decelerate` and `linear` (`standard` =
`cubic-bezier(0.2, 0, 0, 1)`). M3 Expressive replaces part of the curves with
**spring physics** (fast, default, slow); that requires JS or the CSS `linear()`
property and is **out of scope** (V does not need expressive animation). Always
honor `prefers-reduced-motion`.

## 4. Library options

### 4.1 `@material/web` (official, Google, Lit)

- Version 2.5.0 published on 2026-07-15; Apache-2.0 license; ~11.3 thousand stars;
  dependencies: `lit` (^2.8 or ^3), `tslib`, `@lit/context`. Last push 2026-10-02.
- **Maintenance mode** since 2024-06-10: "MWC is in maintenance mode pending new
  maintainers". The official announcement says it is not deprecated, but no new
  components or features are planned, PRs are not accepted by default, and support
  depends on volunteer time. The roadmap (`docs/roadmap.md`, reviewed 2026-07-31)
  confirms it: "No future work is planned".
- Existing components: button (elevated, filled, filled-tonal, outlined, text),
  checkbox, chips, dialog, divider, elevation, fab, focus-ring, icon, icon-button,
  list, menu, progress (linear and circular), radio, ripple, select, slider,
  switch, tabs, text-field (filled and outlined). **Missing** (still "to be
  built"): autocomplete, badge, banner, bottom/top app bar, card, **data table**,
  date/time picker, navigation bar/drawer/rail, search, segmented button,
  snackbar, tooltip. V uses DataTable, Tag, Modal, Toggletip, Search and
  ContentSwitcher, which have no equivalent.
- Browsers: Chrome and Edge 120+, Firefox 119+, Safari 16.4+.
- Size (measured by the project, 2025-08-20): `all.js` 72.1 kb gzip; one button ~7
  kb gzip; `select` 19 to 27 kb gzip; `text-field` and `menu` between 6 and 14 kb
  gzip.
- Theming by CSS tokens (`--md-sys-color-*`, `--md-ref-typeface-*`,
  `--md-sys-shape-*`, `--md-sys-typescale-*`) and Sass (`color.light-theme`,
  `color.dark-theme`). Dark mode is not automatic: the app decides with which
  selector to apply the dark scheme.
- Conclusion: it is useful as a **source of truth for the tokens** and,
  occasionally, as a standalone component. It is not suitable as the basis of the
  whole UI: no DataTable, frozen maintenance and two component systems living
  together.

### 4.2 `@lit/react` 1.0.8

BSD-3-Clause license, peer `@types/react` 17/18/19. `createComponent` wraps a Lit
custom element for React with typed props and mapped events. **React 19 (V's,
19.2.7) already supports custom elements natively** (props as properties, events
with `on<name>`), so the wrapper only adds types and more convenient event names.
It would be used only in the exception case of 6.9. A risk to verify in C2: jsdom
(vitest) has incomplete support for `ElementInternals`, which `material-web`'s
form controls depend on; the tests would have to avoid mounting those components
or mock them.

### 4.3 `@material/material-color-utilities` 0.4.0

Apache-2.0 license, published on 2026-01-21 (repo with ~2.3 thousand stars and
activity in 2026-08). It is the reference implementation of dynamic color. Verified
in a local test:

- Usable API: `Hct.fromInt(argbFromHex(seed))`, a scheme (`SchemeTonalSpot`,
  `SchemeVibrant`, `SchemeContent`, `SchemeFidelity`, `SchemeNeutral`,
  `SchemeMonochrome`, `SchemeExpressive`, `SchemeRainbow`, `SchemeFruitSalad`) with
  `(hct, isDark, contrastLevel)`, and
  `new MaterialDynamicColors().<role>().getArgb(scheme)` for each role (in 0.4.0
  the roles are **instance methods**, not static; the old example code with
  `MaterialDynamicColors.primary` no longer works). `themeFromSourceColor` +
  `applyTheme` exist and write `--md-sys-color-*` on an element, but they only give
  the roles of the classic scheme; the `surface-container-*` ones are obtained with
  `MaterialDynamicColors` (confirmed: `surfaceContainerLowest … Highest`,
  `surfaceDim`, `surfaceBright`).
- It is ESM with extensionless imports (`./dynamic_scheme`): it **fails in plain
  Node**, and works with bundlers. Vite/Vitest resolve it; do not import it from
  Node scripts without a bundler.
- Size: importing only one scheme + `MaterialDynamicColors` + color utilities, the
  minified test bundle was 89 kB uncompressed and **20.5 kB gzip**. Loading it
  with a dynamic `import()` only when M3 is activated keeps it off Carbon's path.
- No runtime dependencies.

Accent colors measured (light theme) with `SchemeTonalSpot` versus `SchemeVibrant`
from Carbon's 8 accents (ramp 60). Contrast of `primary` over `surface` always ≥
6.1:1 and of `on-primary` over `primary` ≥ 6.4:1 (meets AA and AAA for normal
text):

| Accent (seed) | TonalSpot | Vibrant |
| --- | --- | --- |
| blue `#0f62fe` | `#4b5c92` (muted indigo) | `#0052dd` (blue) |
| teal `#007d79` | `#006a66` | `#006a66` |
| green `#198038` | `#36693d` | `#006e2b` |
| purple `#8a3ffc` | `#69548d` | `#7b00fc` |
| magenta `#d02670` | `#8c4a5e` (muted pink) | `#ba005f` |
| red `#da1e28` | `#904a45` (brown) | `#c0001a` |
| orange `#ba4e00` | `#8d4e2c` (brown) | `#9f4200` |
| neutral `#525252` | `#006874` (teal-ish, arbitrary hue) | `#006874` |

Design consequence: **TonalSpot** (Google's default, pastel) distorts V's accent
selector: red turns brown and blue turns indigo. Recommendation: **`SchemeVibrant`**
for the chromatic accents (it keeps the hue recognizable; it is still valid M3)
and **`SchemeMonochrome`** (or `SchemeNeutral`) for `neutral`, because with chroma
0 the seed's hue does not exist and TonalSpot/Vibrant invent a teal. The final
decision is confirmed with screenshots in C3; the scheme is a one-line parameter.

### 4.4 MUI

`@mui/material` 9.4.0 (2026-08-27, MIT) still implements **Material Design 2**. The
M3 adoption issue (mui/material-ui#29345) is still open (last movement 2026-06-03,
174 comments) and the "2026 and beyond" blog does not plan it. It also requires
Emotion and would duplicate the component system. Discarded.

### 4.5 Bundled typography (offline)

Options measured in `@fontsource` (OFL-1.1 license, v5.3.0, July 2026):

| Package | Files | Size |
| --- | --- | --- |
| `@fontsource/roboto` (static) | latin 400, 500, 700 `.woff2` | 21.9 + 22.2 + 22.2 kB = ~66 kB |
| `@fontsource-variable/roboto-flex` | `latin-wght-normal.woff2` (weight axis only) | 34.3 kB |

Recommendation: **variable Roboto Flex, `wght` axis only** (34 kB, covers 400/500/700
and any intermediate weight); a simpler alternative, faithful to the specification:
static Roboto 400/500/700 (66 kB). Both are imported from `node_modules` with Vite,
like IBM Plex today in `styles/index.scss`; the Latin subset covers es/en.
`fonts.googleapis.com` is not used.

## 5. Why `weppa-cloud/material3-mcp-server` is not installed

Verified facts: 6 stars, a single author, created on 2025-09-29 and unchanged since
2025-09-30 (version 1.1.1, MIT, ~12 months without maintenance). It runs with `npx
-y @weppa-cloud/material3-mcp-server` and uses `axios`, `cheerio` and the GitHub
API ("web" coverage: it reads `material-web`'s TypeScript; "flutter": it reads
`flutter/flutter`'s Dart) and Iconify for icons; scraping m3.material.io is listed
as "future". Reasons not to install it:

1. **It adds little.** Everything useful is public `material-web` information,
   which was already read directly in this research (tokens, components, docs) with
   verified values.
2. **Supply chain.** `npx -y` runs code from a package with a single unreviewed
   maintainer and no activity, with 10 direct dependencies, on the developer's
   machine. The benefit does not offset the risk.
3. **Network at time of use.** It depends on the GitHub API (60 requests/hour
   without a token; the package encourages setting a `GITHUB_TOKEN`, that is, more
   credentials in the configuration).
4. **Wrong coverage for V.** Its "React" support is listed as "coming soon" and
   the output that matters (CSS/SCSS tokens) is in a single directory of a public
   repository.
5. **Project rule.** `AGENTS.md` requires documenting why the standard library and
   existing dependencies are not enough before adding one; here there is no reason
   that justifies it.

Alternative without installing anything: the official tokens
(`tokens/versions/v0_192/`) and the documents in `material-web/docs/theming/` are
enough; this note cites them.

## 6. Design of the M3 skin for V

### 6.1 Preference

`apps/web/src/theme/appearance.ts` (the same module as the theme and accent):

- New type `DesignSystem = 'carbon' | 'm3'`, constant `DESIGN_SYSTEMS`,
  `localStorage` key `voz.design`, default value `'carbon'`, read and write with
  `try/catch` like the others.
- `applyAppearance(theme, accent, design)` sets `data-design` on `<html>`. Carbon
  keeps using the zone classes `cds--white | g10 | g90 | g100` for light/dark;
  **that logic is not changed**: M3 derives its mode from the resolved zone
  (`g10/white` = light, `g90/g100` = dark). This way Carbon's four themes still
  exist and "system" still works.
- `useAppearance` also returns `design` and `setDesign`.
- A selector in the Settings menu (next to theme and accent): two options, "Carbon"
  and "Material 3", with the labels in the es/en i18n catalog and a tooltip
  explaining that it is only the visual appearance.
- Tests (`appearance.test.ts`): default value, persistence, an invalid value in
  `localStorage` falls back to `'carbon'`, a `localStorage` that throws does not
  break anything, the attribute on `<html>`.

### 6.2 Generating roles from the accent

New module `apps/web/src/theme/m3.ts` (loaded with a dynamic `import()` only if
`design === 'm3'`):

```
seed = ACCENT_SWATCH[accent]            // already exists in appearance.ts
scheme = accent === 'neutral' ? SchemeMonochrome : SchemeVibrant
for dark of [false, true]: roles = { 'primary': M.primary().getArgb(s), ... }
```

Only the ~28 roles that the SCSS layer uses are generated (section 6.3). They are
applied as CSS properties with
`element.style.setProperty('--md-sys-color-<role>', hex)` on `<html>` (the CSSOM
does not clash with a restrictive `style-src` CSP; no `<style>` is injected). They
are recomputed when the accent or the zone (light/dark) changes. Contrast is left
at 0 (standard); optionally a high contrast level later, since it is a scheme
parameter.

### 6.3 Mapping of Carbon tokens to M3 roles

Layer `apps/web/src/styles/m3/` imported **after** `./accent` and `./shape`, with
all selectors under `[data-design='m3']` plus the zone class to beat Carbon
(`[data-design='m3'].cds--g100`, etc.; specificity (0,2,0) and later import order).
The accent rules in `_accent.scss` are overridden in this mode because the accent
already enters through the seed.

| Carbon token | M3 role |
| --- | --- |
| `--cds-background` | `surface` |
| `--cds-layer-01` | `surface-container-low` |
| `--cds-layer-02` | `surface-container` |
| `--cds-layer-03` | `surface-container-high` |
| `--cds-layer-accent-01` | `surface-container-highest` |
| `--cds-field-01` / `--cds-field-02` | `surface-container-highest` / `surface-container-high` |
| `--cds-border-subtle-00/01/02` | `outline-variant` |
| `--cds-border-strong-01/02/03`, `--cds-border-inverse` | `outline` |
| `--cds-text-primary` | `on-surface` |
| `--cds-text-secondary`, `--cds-text-helper`, `--cds-icon-secondary` | `on-surface-variant` |
| `--cds-text-placeholder` | `on-surface-variant` at 60 % (`color-mix`) |
| `--cds-text-disabled`, `--cds-icon-disabled` | `on-surface` at 38 % |
| `--cds-text-on-color`, `--cds-icon-on-color` | `on-primary` |
| `--cds-icon-primary` | `on-surface-variant` |
| `--cds-interactive`, `--cds-link-primary`, `--cds-icon-interactive`, `--cds-border-interactive`, `--cds-button-primary` | `primary` |
| `--cds-link-primary-hover`, `--cds-button-primary-hover` | `primary` mixed with 8 % of `on-primary` |
| `--cds-button-primary-active` | `primary` mixed with 12 % of `on-primary` |
| `--cds-button-secondary` | `secondary-container` (and the button text becomes `on-secondary-container`) |
| `--cds-button-tertiary` | `primary` (outlined variant: `outline` border) |
| `--cds-button-danger-primary` | `error` |
| `--cds-focus` | `secondary` (like `material-web`'s ring) |
| `--cds-highlight`, `--cds-background-selected` | `secondary-container` |
| `--cds-background-hover`, `--cds-layer-hover-0*` | `on-surface` at 8 % over the surface |
| `--cds-support-error` | `error` |
| `--cds-support-info` | `primary` |
| `--cds-support-success`, `--cds-support-warning` | custom colors (M3 has no role): `customColor` with the scheme's own `blend: true`, or fixed greens/ambers with generated container and `on-` |
| `--cds-overlay` | `scrim` at 32 % |
| `--cds-tag-background-*` / `--cds-tag-color-*` | the equivalent `*-container` / `on-*-container` |

The `color-mix(in srgb, ...)` mixes are written **once in SCSS** referencing the
role variables, so changing accent or light/dark only touches the ~28 roles on
`<html>`. `color-mix` is standard in Chrome 111+, Firefox 113+, Safari 16.2+, below
the minimum of `material-web` (Chrome 120, Firefox 119, Safari 16.4).

### 6.4 Typography

Bundled Roboto Flex (variable, `wght` only) or static Roboto (4.5). Under
`[data-design='m3']`: the app's `--cds-body-*`/`font-family` set to `Roboto Flex`,
and the M3 scale applied to the components that Carbon types with its own tokens
(`--cds-heading-*`, `--cds-label-*`, `--cds-body-*`, `--cds-helper-text-*`):
body-medium (14/20) for most things, label-large (14, weight 500) for buttons,
title-large for modal headers, headline for page titles. The monospaced font
(times, transcript) does **not** change: IBM Plex Mono is kept.

### 6.5 Shapes (M3 only)

Carbon stays rectangular: `_shape.scss` and the app's `border-radius: 0` are not
touched. The M3 layer defines `--m3-shape-*` with the values of section 3.3 and
applies them to:

- Buttons (`.cds--btn`), IconButton, Toggle and search: `full`; circular
  RadioButton.
- Tag: `small` (8 px, like M3 chips).
- Tiles, panels, the Settings panel and notifications: `medium` (12 px). Menus and
  dropdown lists: `extra-small` (4 px), like the M3 menu.
- Modal: `extra-large` (28 px).
- TextInput/Select/Search/NumberInput: filled container with 4 px top corners and
  a bottom line in `outline`/`primary` on focus (M3's "filled" variant).
- There are already `border-radius: 0` rules in `AudioPlayer.scss` (4 places) that,
  under `[data-design='m3']`, are overridden to `medium` where appropriate; they
  must be reviewed in C2.

### 6.6 Elevation and state layers (M3 only)

- Levels 0 to 3 as `--m3-elevation-*` variables (two-layer `box-shadow` computed
  from `material-web`'s table), used in Menu/Popover (level 2), Modal (level 3) and
  elevated buttons; the rest flat with a surface tone. In dark, tone is prioritized
  over shadow.
- State layers with `::before` or `box-shadow: inset` on the container: hover 8 %,
  focus 12 %, pressed 12 %, drag 16 %, using the content's `currentColor`
  (`on-primary` on filled buttons, `primary` on outlined and text, `on-surface` on
  rows and lists). Carbon's solid `-hover`/`-active` variants are replaced by these
  layers where the mapping of 6.3 is not enough. Dynamic ripple (`material-web`'s)
  is left out: the static layer covers 95 % of what is perceived.
- Visible focus: a 3 px ring in `secondary` with a 2 px offset, like
  `md-focus-ring`. Carbon's keyboard focus is kept (accessibility) and only its
  color and shape change.
- Motion: duration `short4` (200 ms) and curve `standard`
  (`cubic-bezier(0.2, 0, 0, 1)`) for state changes; `medium2` (300 ms) and
  `emphasized-decelerate` for modals appearing; all under
  `@media (prefers-reduced-motion: no-preference)`.

### 6.7 File structure

```
apps/web/src/
  theme/appearance.ts        # + DesignSystem, voz.design, data-design
  theme/m3.ts                # role generation (dynamic import())
  theme/m3.test.ts           # roles for the 8 accents, light/dark, contrast >= 4.5
  styles/m3/_roles.scss      # Carbon -> M3 mapping (table 6.3)
  styles/m3/_shape.scss      # M3 shapes
  styles/m3/_elevation.scss  # levels and state layers
  styles/m3/_type.scss       # Roboto + scale
  styles/m3/index.scss       # used from styles/index.scss after ./accent and ./shape
```

### 6.8 Acceptance criteria (C2 and C3)

- Carbon unchanged visually: the Carbon screenshots from before the layer are
  identical.
- With `data-design="m3"`: all V components meet table 6.3 and the shapes of 6.5;
  light and dark; es and en; the 8 accents.
- Contrast: normal text ≥ 4.5:1 and components/icons ≥ 3:1 in both modes; a test
  that computes the main pairs (`on-surface/surface`, `on-primary/primary`,
  `on-secondary-container/secondary-container`, `error/on-error`,
  `outline/surface`).
- Bundle: `grep -rE "https?://" dist/` with no font or CDN URLs (the strings
  `elevenlabs` and "Buzz" remain absent); fonts come from `node_modules`.
- `npm run lint`, `typecheck`, `npx vitest run`, `npm run build` green; Carbon vs
  M3 screenshots reviewed with Read.

### 6.9 When (and only when) to use `@material/web` + `@lit/react`

Only if a Carbon control ends up irreparably wrong with the skin, and only in M3
mode. Likely candidates: none on the first pass (V's components are buttons,
fields, selects, toggles, radios, tags, tables, modals, menus, progress bar). The
only real candidate is the audio player's **slider** if Carbon's does not admit an
acceptable M3 shape; M3's slider (`md-slider`) exists. Before adding it, the
following are evaluated: the cost of ~10 kB gzip for the component,
`ElementInternals` in jsdom, and the fact that it would stop being a Carbon
component (accessibility and keyboard to verify). Rule: if `@material/web` is
added, only the specific module is imported (`@material/web/slider/slider.js`)
with dynamic loading and registered only when M3 is activated.

## 7. Cost and risks

Work estimate for C2 + C3 (one Sonnet agent, a single thread; without touching the
backend):

| Piece | Effort |
| --- | --- |
| Preference + selector + i18n + tests | low (~0.5 day) |
| `m3.ts` (role generation, dynamic loading, contrast tests) | low-medium (~0.5 day) |
| SCSS layer: color and shape mapping | medium (~1 day) |
| State layers, elevation, typography, focus | medium (~1 day) |
| Per-component touch-ups (filled fields, tags, notifications, DataTable, Modal) | medium-high (~1 day; this is where the risk is) |
| Carbon vs M3 screenshots (light/dark, es/en), review, adjustments | low-medium (~0.5 day) |

Indicative total: 3 to 4 agent-days, versus weeks for a real migration.
Maintenance cost: low while the components are Carbon, because the skin only
touches tokens and CSS variables.

Risks:

- **CSS specificity and order.** Carbon applies its tokens by zone class; the M3
  layer must win without `!important`. Mitigation: a double selector
  (`[data-design]` + zone class) and importing after `./accent`.
- **Components with Carbon's own styling** (DataTable, Modal, ListBox, Toggle) use
  border and height values (32/40/48 px) that are not M3's. The skin keeps
  Carbon's heights (density), so it will not be a pixel-for-pixel replica of the M3
  specifications (e.g. 40 px buttons with a `full` corner, not 48). This is a
  conscious decision: M3 as an "appearance", not as full parity.
- **No success/warning role in M3** (6.3): solved with custom colors; adds 2 roles
  outside the scheme.
- **`SchemeVibrant` versus Google's recommendation (TonalSpot).** A deliberate
  deviation (4.3); the schemes depend on a single constant.
- **`material-color-utilities` 0.4.0 is ESM with extensionless imports.**
  Vite/Vitest resolve it; plain Node does not. Do not import it in command-line
  scripts without a bundler.
- **Dependence on a project in maintenance** (`@material/web`): mitigated by not
  depending on it except in the exception case of 6.9 and because tokens/styles are
  stable.
- **Weight**: +~20 kB gzip of color utilities (lazy-loaded), +34 to 66 kB of font
  (only requested if `data-design="m3"`, with `font-display: swap`), +~10 kB of CSS.
- **V's rules.** "Nothing generic from AI" and "square Carbon": M3 exists only as an
  explicit option; first launch and the default remain Carbon.

## 8. References

- https://m3.material.io/ (color, typography, shape, elevation, state layers, motion)
- https://m3.material.io/blog/m3-expressive-motion-theming
- https://github.com/material-components/material-web (`docs/theming/color.md`,
  `typography.md`, `shape.md`, `docs/support.md`, `docs/roadmap.md`, `docs/size.md`,
  `tokens/versions/v0_192/`)
- https://github.com/material-components/material-web/discussions/5642
- https://github.com/material-foundation/material-color-utilities
- https://www.npmjs.com/package/@material/material-color-utilities
- https://www.npmjs.com/package/@lit/react
- https://github.com/mui/material-ui/issues/29345
- https://github.com/weppa-cloud/material3-mcp-server
- https://fontsource.org/fonts/roboto-flex

## 9. Implementation (C2 and C3)

Done on 2026-10-03 following sections 6.1 to 6.9, with these differences:

- Carbon's type tokens are CSS variables (`--cds-body-compact-01-font-size`, etc.)
  and the sans styles do not set `font-family` (they inherit it), so M3 typography
  is applied by setting the family on `body`, `.voz-app` and the controls, and
  overriding the scale's variables; code stays in IBM Plex Mono.
- `data-design` is only set **after** the roles are published (`applyDesign` is
  asynchronous and a new call discards the previous one); `main.tsx` waits for
  `settleDesign()` so as not to paint M3 without colors on the first render.
- The 8 accents use `SchemeVibrant`; `neutral` uses `SchemeMonochrome`. Success and
  warning are custom roles (`--voz-m3-success*`, `--voz-m3-warning*`), harmonized
  toward the accent.
- Vitest needs `test.server.deps.inline: ['@material/material-color-utilities']`
  (`apps/web/vite.config.ts`): without it it fails because of the extensionless
  imports of section 4.3.
- `@material/web` and `@lit/react` were **not** installed: no control needed them
  (6.9).
- New dependencies (exact versions): `@material/material-color-utilities` 0.4.0
  (Apache-2.0; a separate chunk of 19.5 kB gzip, only downloaded in M3 mode) and
  `@fontsource-variable/roboto-flex` 5.3.0 (OFL-1.1; a single 34 kB `woff2` of the
  `wght` axis, downloaded only if something uses the font). Not a single external
  URL in the bundle.

Files: `apps/web/src/theme/appearance.ts` and `m3.ts` (plus their tests),
`apps/web/src/styles/m3/` (`_tokens`, `_type`, `_shape`, `_components`), selector in
`components/HeaderMenus.tsx` and texts in `i18n/messages/shell.ts`.

Carbon vs M3 comparisons (dark/es and light/en: home, workspace, Settings, export
and rename) and the accents: `docs/assets/screenshots/m3-*.png`.

## Screenshots

Carbon (default) versus Material 3, with demo data:

| Carbon | Material 3 |
| --- | --- |
| ![Carbon, workspace](../assets/screenshots/m3-carbon-dark-es-workspace.png) | ![Material 3, workspace](../assets/screenshots/m3-m3-dark-es-workspace.png) |
| ![Carbon, home](../assets/screenshots/m3-carbon-light-en-home.png) | ![Material 3, home](../assets/screenshots/m3-m3-light-en-home.png) |

Settings in Material 3 ([dark](../assets/screenshots/m3-m3-dark-es-settings.png),
[light](../assets/screenshots/m3-m3-light-en-settings.png)) and
[accents](../assets/screenshots/m3-accents-dark-es.png).
