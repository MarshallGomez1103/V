// Piel Material 3: genera los roles de color desde el acento (docs/design/material3.md).
// Se carga con import() solo cuando el diseño elegido es M3.
import {
  argbFromHex,
  Blend,
  Hct,
  hexFromArgb,
  MaterialDynamicColors,
  SchemeMonochrome,
  SchemeVibrant,
  TonalPalette,
  type DynamicScheme,
} from '@material/material-color-utilities'

const COLORS = new MaterialDynamicColors()

/** Rol M3 (`--md-sys-color-<clave>`) → método de MaterialDynamicColors que lo calcula. */
const ROLES = {
  primary: 'primary',
  'on-primary': 'onPrimary',
  'primary-container': 'primaryContainer',
  'on-primary-container': 'onPrimaryContainer',
  secondary: 'secondary',
  'on-secondary': 'onSecondary',
  'secondary-container': 'secondaryContainer',
  'on-secondary-container': 'onSecondaryContainer',
  tertiary: 'tertiary',
  'on-tertiary': 'onTertiary',
  'tertiary-container': 'tertiaryContainer',
  'on-tertiary-container': 'onTertiaryContainer',
  error: 'error',
  'on-error': 'onError',
  'error-container': 'errorContainer',
  'on-error-container': 'onErrorContainer',
  background: 'background',
  'on-background': 'onBackground',
  surface: 'surface',
  'surface-dim': 'surfaceDim',
  'surface-bright': 'surfaceBright',
  'surface-container-lowest': 'surfaceContainerLowest',
  'surface-container-low': 'surfaceContainerLow',
  'surface-container': 'surfaceContainer',
  'surface-container-high': 'surfaceContainerHigh',
  'surface-container-highest': 'surfaceContainerHighest',
  'on-surface': 'onSurface',
  'surface-variant': 'surfaceVariant',
  'on-surface-variant': 'onSurfaceVariant',
  outline: 'outline',
  'outline-variant': 'outlineVariant',
  'inverse-surface': 'inverseSurface',
  'inverse-on-surface': 'inverseOnSurface',
  'inverse-primary': 'inversePrimary',
  scrim: 'scrim',
  shadow: 'shadow',
} as const satisfies Record<string, keyof MaterialDynamicColors>

type RoleMethod = (typeof ROLES)[keyof typeof ROLES]

/**
 * M3 no tiene roles de éxito ni de aviso: se crean a medida (verde y ámbar) y se
 * armonizan hacia el acento, con los mismos tonos que M3 usa para sus contenedores.
 */
const CUSTOM = { success: '#198038', warning: '#b28600' } as const

/** Variables CSS a publicar en <html> (nombre → color hexadecimal). */
export function m3Roles(seed: string, monochrome: boolean, dark: boolean): Record<string, string> {
  const source = Hct.fromInt(argbFromHex(seed))
  // Vibrant mantiene reconocible el acento (rojo, azul…); TonalSpot, el valor de Google,
  // los apaga hasta volverlos marrón/índigo. Con croma 0 (neutro) el matiz no existe.
  const scheme: DynamicScheme = monochrome
    ? new SchemeMonochrome(source, dark, 0)
    : new SchemeVibrant(source, dark, 0)

  const vars: Record<string, string> = {}
  for (const [name, method] of Object.entries(ROLES) as [string, RoleMethod][]) {
    vars['--md-sys-color-' + name] = hexFromArgb(COLORS[method]().getArgb(scheme))
  }

  for (const [name, hex] of Object.entries(CUSTOM)) {
    const base = monochrome ? argbFromHex(hex) : Blend.harmonize(argbFromHex(hex), source.toInt())
    const palette = TonalPalette.fromInt(base)
    vars['--voz-m3-' + name] = hexFromArgb(palette.tone(dark ? 80 : 40))
    vars['--voz-m3-on-' + name] = hexFromArgb(palette.tone(dark ? 20 : 100))
    vars['--voz-m3-' + name + '-container'] = hexFromArgb(palette.tone(dark ? 30 : 90))
    vars['--voz-m3-on-' + name + '-container'] = hexFromArgb(palette.tone(dark ? 90 : 10))
  }
  return vars
}

/** Publica los roles como propiedades CSS de <html> (CSSOM: no necesita `style-src` inline). */
export function applyM3Roles(
  root: HTMLElement,
  seed: string,
  monochrome: boolean,
  dark: boolean,
): void {
  for (const [name, value] of Object.entries(m3Roles(seed, monochrome, dark))) {
    root.style.setProperty(name, value)
  }
}
