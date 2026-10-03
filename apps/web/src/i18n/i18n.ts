import { useCallback, useSyncExternalStore } from 'react'

import { MESSAGES, type MessageKey } from './messages'

export type Lang = 'es' | 'en'
export type Vars = Readonly<Record<string, string | number>>
export type Translate = (key: MessageKey, vars?: Vars) => string

/** Claves con variante `_one`/`_other`: `plural('x', n)` elige según `n`. */
export type PluralKey = Extract<MessageKey, `${string}_one`> extends `${infer Base}_one`
  ? Base
  : never

export const LANGS: readonly Lang[] = ['es', 'en']
const STORAGE_KEY = 'voz.lang'

function stored(): Lang | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value === 'es' || value === 'en' ? value : null
  } catch {
    return null
  }
}

/** Idioma guardado; si no hay, el del navegador (español solo si empieza por «es»). */
export function detectLang(): Lang {
  const saved = stored()
  if (saved !== null) {
    return saved
  }
  const preferred = typeof navigator === 'undefined' ? '' : navigator.language
  return preferred.toLowerCase().startsWith('es') ? 'es' : 'en'
}

let current: Lang = detectLang()
const listeners = new Set<() => void>()

function syncDocument(lang: Lang) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang
  }
}
syncDocument(current)

export function getLang(): Lang {
  return current
}

export function setLang(lang: Lang): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // Modo privado o almacenamiento bloqueado: el idioma se aplica igual.
  }
  if (lang === current) {
    return
  }
  current = lang
  syncDocument(lang)
  listeners.forEach((listener) => {
    listener()
  })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function fill(template: string, vars: Vars | undefined): string {
  if (vars === undefined) {
    return template
  }
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : whole,
  )
}

/** Traducción fuera de React (mensajes de error de la API); usa el idioma actual. */
export function translate(key: MessageKey, vars?: Vars): string {
  return fill(MESSAGES[key][current === 'es' ? 0 : 1], vars)
}

export function translateIn(lang: Lang, key: MessageKey, vars?: Vars): string {
  return fill(MESSAGES[key][lang === 'es' ? 0 : 1], vars)
}

/** Mensaje de error por código estable (`prefix + code`); si no existe, el de `fallback`. */
export function translateCode(
  prefix: string,
  code: string,
  fallback: MessageKey,
  vars?: Vars,
): string {
  const key = prefix + code
  return Object.hasOwn(MESSAGES, key)
    ? translate(key as MessageKey, vars)
    : translate(fallback, { code, ...vars })
}

export function pluralKey(base: PluralKey, n: number): MessageKey {
  return (base + (n === 1 ? '_one' : '_other')) as MessageKey
}

/** Plural simple (uno / otros); `{n}` ya viene incluido en las variables. */
export function translatePlural(base: PluralKey, n: number, vars?: Vars): string {
  return translate(pluralKey(base, n), { n, ...vars })
}

export interface I18n {
  lang: Lang
  t: Translate
  /** Plural con `{n}` disponible en la plantilla. */
  tn: (base: PluralKey, n: number, vars?: Vars) => string
  setLang: (lang: Lang) => void
}

/** Idioma activo y traductor; se re-renderiza al cambiar de idioma. */
export function useI18n(): I18n {
  const lang = useSyncExternalStore(subscribe, getLang)
  const t = useCallback<Translate>((key, vars) => translateIn(lang, key, vars), [lang])
  const tn = useCallback<I18n['tn']>(
    (base, n, vars) => translateIn(lang, pluralKey(base, n), { n, ...vars }),
    [lang],
  )
  return { lang, t, tn, setLang }
}

/** Código BCP 47 para `Intl` / `toLocale*`. */
export function localeOf(lang: Lang): string {
  return lang === 'es' ? 'es-CO' : 'en-US'
}
