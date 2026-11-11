# V design guide

Rules for the look and behaviour of V's web interface. They describe what the
code in `apps/web/` does today and what a change to it must keep doing. Where a
rule is enforced by a test, the test is named; every other rule is a review
criterion. The Material 3 evaluation behind the alternative skin is in
[material3.md](material3.md).

"Must" marks a rule a pull request is expected to respect; "should" marks a
default that a change may break with a stated reason.

## 1. Design system and skin

- **Carbon is the default.** The interface is built from IBM Carbon components
  (`@carbon/react`) and its tokens, with rectangular shapes everywhere.
  `apps/web/src/styles/_shape.scss` removes the rounded corners Carbon gives to
  tags, toggles and radio buttons; new components must stay rectangular in
  Carbon.
- **Material 3 is a skin, not a second interface.** It changes colour roles,
  typography, shape, elevation and motion over the same Carbon components, and
  only while `<html data-design="m3">` is set (`apps/web/src/styles/m3/`,
  `apps/web/src/theme/m3.ts`). A feature is built once, with Carbon components,
  and must look correct in both. Never add a component that exists only in one
  design.
- **The skin falls back safely.** The Material 3 colour generator is loaded on
  demand; if loading fails the interface stays in Carbon
  (`applyDesign` in `apps/web/src/theme/appearance.ts`). Carbon users do not
  download the generator.
- **Everything is bundled.** IBM Plex (Carbon) and Roboto Flex (Material 3,
  Latin subset) ship inside the bundle. No font, icon set, script or stylesheet
  is loaded from a CDN, so V works offline. Do not add one.
- **Styles live next to their component** (`Component.scss`), use Carbon tokens
  through `apps/web/src/styles/_carbon.scss`, and avoid hard-coded colours.

## 2. Themes and accents

| Setting | Values | Default |
| --- | --- | --- |
| Theme | `system`, `white`, `g10`, `g90`, `g100` | `system` |
| Accent | `blue`, `teal`, `green`, `purple`, `magenta`, `red`, `orange`, `neutral` | `blue` |
| Design | `carbon`, `m3` | `carbon` |
| Language | `es`, `en` | browser language: Spanish if it starts with `es`, otherwise English |

- `system` follows the operating system: Gray 10 (light) or Gray 100 (dark). The
  other four are Carbon's White, Gray 10, Gray 90 and Gray 100. Gray 90 and Gray
  100 are the dark themes (`resolveTheme`, `isDarkTheme`).
- The theme class and the accent are set on `<html>`, so menus, tooltips and
  other portals inherit them. A component must never assume a theme: use Carbon
  tokens (`--cds-*`) and the accent follows by itself.
- Accents are the official Carbon colour ramps (`apps/web/src/styles/_accent.scss`).
  Interactive tokens are derived from ramp steps (60 in light themes, 50 and
  40 in dark ones), so changing the accent does not require per-component work.
  `neutral` is a grey ramp and tints nothing; with Material 3 it produces a
  monochrome scheme (`apps/web/src/theme/m3.test.ts`).
- Choices persist in `localStorage` (`voz.theme`, `voz.accent`, `voz.design`,
  `voz.lang`). Reading or writing can fail (private mode, blocked storage): the
  choice must still apply for the current session and nothing may throw
  (`apps/web/src/theme/appearance.test.ts`, `apps/web/src/i18n/i18n.test.ts`).
- Information is never carried by colour alone. Pair colour with text, an icon
  or a shape (status tags, review flags, speaker labels).

## 3. Languages

- Spanish and English are both complete. Every visible string is a catalog entry
  `[español, English]` in `apps/web/src/i18n/messages/`; both versions must exist
  and use the same variables (`apps/web/src/i18n/i18n.test.ts`).
- No visible text is written by hand in a component: `aria-label`, `title`,
  `placeholder`, button and dialog texts included
  (`apps/web/src/i18n/literals.test.ts`).
- Backend errors arrive as stable codes. Each code the interface can receive has
  its own message in both languages, and an unknown code shows the generic
  message with the code (`apps/web/src/i18n/backendCodes.test.ts`). Never show a
  raw server message, a traceback or a host path.
- Plurals use paired `_one` / `_other` entries. `<html lang>` follows the active
  language.
- Do not add a third language without an explicit decision.

## 4. The four states every view has

Any screen or panel that depends on data or on a long operation must handle all
four, in this form. The library (`apps/web/src/components/Library.tsx`) is the
reference.

| State | What the person sees | Building block |
| --- | --- | --- |
| Empty | A sentence saying there is nothing yet and the next step, never a blank area. The library shows the steps to import a first recording. | Plain text or an ordered list; `role="status"` when it appears after a search or filter. |
| Loading | An inline indicator with a text description in the active language. Do not freeze the layout and do not show a spinner without words. | `Busy` (`components/Busy.tsx`) inside a `role="status"` region. |
| Correct | The content itself. After an action, a short confirmation near the control that triggered it. | The component's own view; `Notice kind="success"`. |
| Error | What failed in the person's words, why if it is known, and a way forward. Recoverable failures offer **Retry**. | `Notice kind="error"` with an `action` (`common.retry`); it is announced as `role="alert"` (`components/Notice.tsx`). |

Also:

- Long operations show real progress from the API (stage, percentage, elapsed
  time), never inferred from logs, and can be cancelled when the backend allows
  it.
- A failed request never leaves the interface in a loading state, and a retry
  starts from the loading state again.
- Destructive actions (delete a transcript, remove a model) ask for
  confirmation and name what will be deleted.
- Anything that could send data off the machine says so before it happens and
  needs an explicit choice (cloud providers, remote endpoints).

## 5. Accessibility minimums

These are the minimums V has been checked against. They are structural checks,
not a conformance claim: [web-quality.md](../web-quality.md) lists what was and
was not examined.

- Every interactive control has an accessible name in the active language
  (`aria-label`, `iconDescription` or visible text). Icon-only buttons need one.
- Every view has exactly one visible `h1` and a logical heading order.
- Everything reachable by pointer is reachable by keyboard, with a visible
  `:focus-visible` indicator. Custom controls (waveform, segment list, range
  controls, speaker timeline) respond to the arrow keys and Escape where it
  makes sense. Do not remove outlines.
- Status changes that the person does not trigger directly (autosave, loading,
  progress) go in a `role="status"` region; failures use `role="alert"`.
- Text contrast is at least 4.5:1 and borders and the accent against the
  surface at least 3:1. The Material 3 roles are tested for this in all eight
  accents, light and dark (`apps/web/src/theme/m3.test.ts`); Carbon's own tokens
  are used unmodified for the rest.
- Motion respects `prefers-reduced-motion`: Material 3 transitions only apply
  under `no-preference`, and animated components provide a reduced variant
  (`SegmentList.scss`, `JobScreen.scss`).
- The layout holds at a 390 px viewport with no horizontal scroll of the page;
  wide content scrolls inside its own container.
- Technical terms get a plain explanation in a tooltip or helper text
  (`components/Hint.tsx`).

## 6. Layout and content

- Navigation and global actions live in Carbon's UI Shell header
  (`components/AppHeader.tsx`); screens are composed from panels
  (`components/Panel.tsx`).
- Format dates and numbers for the active language (`localeOf` in
  `apps/web/src/i18n/i18n.ts`).
- Never display absolute host paths. The interface receives identifiers and API
  fields only.

## 7. What is not done, and why

| Do not | Why |
| --- | --- |
| Load fonts, icons or scripts from a CDN | V is local-first and must work with no network; the bundle is the only source. |
| Round corners or use pill shapes in Carbon | Carbon is rectangular here; only the Material 3 skin has rounded shapes, and only under `data-design="m3"`. |
| Build components that exist in only one design | Both designs share the same components, so tests and behaviour stay single. |
| Hard-code a colour, theme or accent in a component | It breaks the other themes and the accent selector. Use `--cds-*` tokens. |
| Write visible text in a component | It would escape the Spanish/English catalogs and fail `literals.test.ts`. |
| Show a raw error, traceback or path | They are diagnostics, not user messages, and can leak host details. Use the stable code and its message. |
| Infer job state from logs or timers | The UI reads job state from the API, which is the only source of truth. |
| Rewrite or "correct" transcript text on screen | The transcript is literal; only the person edits it. |
| Rely on colour alone for meaning | It excludes colour-blind people and fails in some themes. Add text, an icon or a shape. |
| Block the page with a spinner and no words | A person cannot tell progress from a hang; use `Busy` with a description. |
| Enable a cloud provider implicitly | Audio and text leave the machine only after an explicit, per-use choice. |
| Add a UI dependency for one control | Bundle weight is budgeted ([web-quality.md](../web-quality.md)); try Carbon first. |
| Claim accessibility conformance | Only the structural checks above were run; say what was checked, not more. |
