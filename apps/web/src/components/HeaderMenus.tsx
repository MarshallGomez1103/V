import { useId, useState, type ReactNode } from 'react'
import { HeaderGlobalAction, Popover, PopoverContent } from '@carbon/react'
import { Checkmark, Language, Settings } from '@carbon/icons-react'

import { LANGS, useI18n, type Lang } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import {
  ACCENT_SWATCH,
  ACCENTS,
  THEME_PREFERENCES,
  THEME_SWATCH,
  useAppearance,
  type Accent,
  type ThemePreference,
} from '../theme/appearance'
import { DesktopShortcut } from './DesktopShortcut'
import './HeaderMenus.scss'

interface MenuProps {
  label: string
  icon: ReactNode
  /** El contenido sabe si el panel está abierto (para consultar datos solo entonces). */
  children: (open: boolean) => ReactNode
}

/** Acción global del header que abre un panel anclado debajo (se cierra con Esc o al salir). */
function HeaderMenu({ label, icon, children }: MenuProps) {
  const [open, setOpen] = useState(false)
  return (
    <Popover
      open={open}
      align="bottom-end"
      dropShadow
      onRequestClose={() => {
        setOpen(false)
      }}
      className="voz-headermenu"
    >
      <HeaderGlobalAction
        aria-label={label}
        tooltipAlignment="end"
        isActive={open}
        onClick={() => {
          setOpen((current) => !current)
        }}
      >
        {icon}
      </HeaderGlobalAction>
      <PopoverContent className="voz-headermenu__content">{children(open)}</PopoverContent>
    </Popover>
  )
}

/** Selector de idioma (persistido; por defecto el del navegador). */
export function LanguageMenu() {
  const { t, lang, setLang } = useI18n()
  return (
    <HeaderMenu label={t('lang.label')} icon={<Language size={20} />}>
      {() => (
      <ul className="voz-menu" aria-label={t('lang.label')}>
        {LANGS.map((code: Lang) => (
          <li key={code}>
            <button
              type="button"
              className="voz-menu__item"
              aria-pressed={code === lang}
              lang={code}
              onClick={() => {
                setLang(code)
              }}
            >
              <span>{t(code === 'es' ? 'lang.es' : 'lang.en')}</span>
              {code === lang ? <Checkmark size={16} aria-hidden="true" /> : null}
            </button>
          </li>
        ))}
      </ul>
      )}
    </HeaderMenu>
  )
}

const THEME_LABELS: Record<ThemePreference, MessageKey> = {
  system: 'theme.system',
  white: 'theme.white',
  g10: 'theme.g10',
  g90: 'theme.g90',
  g100: 'theme.g100',
}

const ACCENT_LABELS: Record<Accent, MessageKey> = {
  blue: 'accent.blue',
  teal: 'accent.teal',
  green: 'accent.green',
  purple: 'accent.purple',
  magenta: 'accent.magenta',
  red: 'accent.red',
  orange: 'accent.orange',
  neutral: 'accent.neutral',
}

/** Ajustes: tema de Carbon, color de acento (se recuerdan en este navegador) e icono de escritorio. */
export function SettingsMenu() {
  const { t } = useI18n()
  const { theme, accent, setTheme, setAccent } = useAppearance()
  const groupId = useId()
  return (
    <HeaderMenu label={t('settings.label')} icon={<Settings size={20} />}>
      {(open) => (
      <>
      <fieldset className="voz-choices">
        <legend className="voz-choices__legend">{t('appearance.theme')}</legend>
        {THEME_PREFERENCES.map((option) => (
          <label key={option} className="voz-choice" title={option === 'system' ? t('theme.system.hint') : undefined}>
            <input
              type="radio"
              name={groupId + '-theme'}
              className="voz-choice__input"
              checked={theme === option}
              onChange={() => {
                setTheme(option)
              }}
            />
            <span
              className="voz-choice__swatch voz-choice__swatch--theme"
              aria-hidden="true"
              data-system={option === 'system' ? 'true' : undefined}
              style={
                option === 'system'
                  ? undefined
                  : { backgroundColor: THEME_SWATCH[option] }
              }
            />
            <span>{t(THEME_LABELS[option])}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="voz-choices voz-choices--accent">
        <legend className="voz-choices__legend">{t('appearance.accent')}</legend>
        <div className="voz-accents">
          {ACCENTS.map((option) => (
            <label key={option} className="voz-accent" title={t(ACCENT_LABELS[option])}>
              <input
                type="radio"
                name={groupId + '-accent'}
                className="voz-choice__input"
                checked={accent === option}
                aria-label={t(ACCENT_LABELS[option])}
                onChange={() => {
                  setAccent(option)
                }}
              />
              <span
                className="voz-accent__swatch"
                aria-hidden="true"
                style={{ backgroundColor: ACCENT_SWATCH[option] }}
              />
            </label>
          ))}
        </div>
      </fieldset>
      <DesktopShortcut active={open} />
      </>
      )}
    </HeaderMenu>
  )
}
