import { useEffect, useSyncExternalStore } from 'react'

/** Temas de Carbon: White, Gray 10, Gray 90 y Gray 100; `system` sigue al sistema. */
export type CarbonTheme = 'white' | 'g10' | 'g90' | 'g100'
export type ThemePreference = 'system' | CarbonTheme

export const THEME_PREFERENCES: readonly ThemePreference[] = [
  'system',
  'white',
  'g10',
  'g90',
  'g100',
]

/** Rampas de color de Carbon; el estilo de cada una vive en styles/_accent.scss. */
export const ACCENTS = [
  'blue',
  'teal',
  'green',
  'purple',
  'magenta',
  'red',
  'orange',
  'neutral',
] as const
export type Accent = (typeof ACCENTS)[number]

/** Color representativo (rampa 60 de Carbon) para la muestra del selector. */
export const ACCENT_SWATCH: Readonly<Record<Accent, string>> = {
  blue: '#0f62fe',
  teal: '#007d79',
  green: '#198038',
  purple: '#8a3ffc',
  magenta: '#d02670',
  red: '#da1e28',
  orange: '#ba4e00',
  neutral: '#525252',
}

/** Fondo de cada tema, para la muestra cuadrada del selector. */
export const THEME_SWATCH: Readonly<Record<CarbonTheme, string>> = {
  white: '#ffffff',
  g10: '#f4f4f4',
  g90: '#262626',
  g100: '#161616',
}

const THEME_KEY = 'voz.theme'
const ACCENT_KEY = 'voz.accent'
const LIGHT_QUERY = '(prefers-color-scheme: light)'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Modo privado o almacenamiento bloqueado: se aplica igual, no se recuerda.
  }
}

function isThemePreference(value: string | null): value is ThemePreference {
  return value !== null && (THEME_PREFERENCES as readonly string[]).includes(value)
}

function isAccent(value: string | null): value is Accent {
  return value !== null && (ACCENTS as readonly string[]).includes(value)
}

export interface Appearance {
  theme: ThemePreference
  accent: Accent
}

function load(): Appearance {
  const theme = read(THEME_KEY)
  const accent = read(ACCENT_KEY)
  return {
    theme: isThemePreference(theme) ? theme : 'system',
    accent: isAccent(accent) ? accent : 'blue',
  }
}

let state: Appearance = load()
const listeners = new Set<() => void>()

function systemPrefersLight(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia(LIGHT_QUERY).matches
  )
}

/** Tema de Carbon efectivo: el elegido o, en automático, g100 (oscuro) / g10 (claro). */
export function resolveTheme(preference: ThemePreference, light: boolean): CarbonTheme {
  if (preference !== 'system') {
    return preference
  }
  return light ? 'g10' : 'g100'
}

const THEME_CLASSES = THEME_PREFERENCES.filter(
  (item): item is CarbonTheme => item !== 'system',
).map((item) => 'cds--' + item)

/**
 * Clase de zona y acento en <html>: así los portales (menús, tooltips) y el fondo del
 * documento heredan lo mismo que el contenedor de la app.
 */
export function applyAppearance(theme: CarbonTheme, accent: Accent): void {
  const root = document.documentElement
  root.classList.remove(...THEME_CLASSES)
  root.classList.add('cds--' + theme)
  root.dataset.accent = accent
}

applyAppearance(resolveTheme(state.theme, systemPrefersLight()), state.accent)

function emit() {
  listeners.forEach((listener) => {
    listener()
  })
}

export function setThemePreference(theme: ThemePreference): void {
  write(THEME_KEY, theme)
  if (theme !== state.theme) {
    state = { ...state, theme }
    emit()
  }
}

export function setAccent(accent: Accent): void {
  write(ACCENT_KEY, accent)
  if (accent !== state.accent) {
    state = { ...state, accent }
    emit()
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function subscribeSystem(listener: () => void): () => void {
  if (typeof window.matchMedia !== 'function') {
    return () => undefined
  }
  const media = window.matchMedia(LIGHT_QUERY)
  media.addEventListener('change', listener)
  return () => {
    media.removeEventListener('change', listener)
  }
}

export interface AppearanceApi extends Appearance {
  /** Tema de Carbon que se está aplicando. */
  resolved: CarbonTheme
  setTheme: (theme: ThemePreference) => void
  setAccent: (accent: Accent) => void
}

/** Tema y acento, persistidos en localStorage; también refleja la elección en <html>. */
export function useAppearance(): AppearanceApi {
  const current = useSyncExternalStore(subscribe, () => state)
  const light = useSyncExternalStore(subscribeSystem, systemPrefersLight)
  const resolved = resolveTheme(current.theme, light)

  useEffect(() => {
    applyAppearance(resolved, current.accent)
  }, [resolved, current.accent])

  return {
    ...current,
    resolved,
    setTheme: setThemePreference,
    setAccent,
  }
}
