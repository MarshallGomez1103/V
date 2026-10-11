import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { setLang } from '../i18n/i18n'
import { MESSAGES } from '../i18n/messages'
import { HOME } from '../lib/navigation'
import { AppHeader } from './AppHeader'

afterEach(cleanup)

describe('marca V en la cabecera', () => {
  it('muestra el glifo V como enlace a Inicio, con "V" como nombre accesible', () => {
    render(<AppHeader route={HOME} onNavigate={() => undefined} />)

    const banner = screen.getByRole('banner', { name: 'V' })
    const home = within(banner).getByRole('link', { name: 'V, ir al inicio' })
    expect(within(home).getByText('V')).toBeDefined()
    // El glifo es decorativo: el texto lo aporta el nombre.
    const mark = home.querySelector('svg.voz-brand__mark')
    expect(mark?.getAttribute('aria-hidden')).toBe('true')
    expect(mark?.querySelector('polygon')).not.toBeNull()
    expect(banner.textContent).not.toContain('VOZ')
  })

  it('en inglés conserva la marca V', () => {
    setLang('en')
    render(<AppHeader route={HOME} onNavigate={() => undefined} />)

    expect(screen.getByRole('link', { name: 'V, go to the home page' })).toBeDefined()
    expect(screen.getByRole('navigation', { name: 'V sections' })).toBeDefined()
  })

  it('ningún texto de la interfaz (es/en) dice "VOZ"', () => {
    const offenders = Object.entries(MESSAGES).filter(([, pair]) =>
      pair.some((text) => /\bVOZ\b/.test(text)),
    )
    expect(offenders.map(([key]) => key)).toEqual([])
  })

  it('el título del documento usa la marca V en ambos idiomas', () => {
    expect(MESSAGES['app.title']).toEqual(['V · Voz local', 'V · Local Voice AI'])
  })
})
