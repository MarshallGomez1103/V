import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

function stubFetch(healthFails = 0) {
  let healthCalls = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('/api/health')) {
        healthCalls += 1
        return healthCalls <= healthFails
          ? Promise.reject(new Error('offline'))
          : Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ status: 'ok', service: 'voz' }),
            })
      }
      // Otras secciones (p.ej. Modelos) cargan su propio estado.
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            models: [],
            disk: { models_bytes: 0, free_bytes: null },
            tasks: [],
            options: [],
          }),
      })
    }),
  )
  return () => healthCalls
}

function stubColorScheme(light: boolean) {
  vi.stubGlobal(
    'matchMedia',
    (query: string) => ({
      matches: light && query.includes('light'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  )
}

describe('App', () => {
  beforeEach(() => {
    window.location.hash = ''
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    document.documentElement.className = ''
  })

  it('renders the import card enabled and the health status', async () => {
    const healthCalls = stubFetch(1)

    render(<App />)

    expect(
      screen.getByRole('button', { name: /suelta aquí tu audio o video/i }),
    ).toHaveProperty('disabled', false)
    expect(screen.queryByText(/motor de transcripción/i)).toBeNull()
    expect(await screen.findByText('Sin conexión')).toBeDefined()

    fireEvent.click(
      screen.getByRole('button', { name: /volver a comprobar/i }),
    )

    expect(await screen.findByText('Disponible')).toBeDefined()
    expect(healthCalls()).toBe(2)
  })

  it('muestra el UI Shell con la navegación y las acciones globales', () => {
    stubFetch()
    render(<App />)

    const banner = screen.getByRole('banner', { name: 'VOZ' })
    expect(within(banner).getByText('VOZ')).toBeDefined()
    for (const name of ['Idioma', 'Ajustes', 'Cerrar servidor']) {
      expect(within(banner).getByRole('button', { name })).toBeDefined()
    }
    const nav = within(banner).getByRole('navigation', {
      name: 'Secciones de VOZ',
    })
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Transcribir', 'Modelos', 'Proveedores cloud'])
    expect(
      within(nav).getByRole('link', { name: 'Transcribir' }).getAttribute('aria-current'),
    ).toBe('page')
    expect(screen.getByRole('heading', { level: 1, name: 'Transcribir' })).toBeDefined()
  })

  it('navega entre secciones y refleja la sección en el hash', async () => {
    stubFetch()
    render(<App />)
    const nav = screen.getByRole('navigation', { name: 'Secciones de VOZ' })

    fireEvent.click(within(nav).getByRole('link', { name: 'Modelos' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Modelos' }),
    ).toBeDefined()
    expect(screen.queryByRole('heading', { level: 1, name: 'Transcribir' })).toBeNull()
    expect(window.location.hash).toBe('#modelos')

    fireEvent.click(within(nav).getByRole('link', { name: 'Proveedores cloud' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Proveedores cloud' }),
    ).toBeDefined()
  })

  it('usa el tema oscuro g100 por defecto y g10 si el sistema prefiere claro', () => {
    stubFetch()
    stubColorScheme(false)
    const dark = render(<App />)
    expect(document.documentElement.classList.contains('cds--g100')).toBe(true)
    expect(dark.container.querySelector('.cds--g100')).not.toBeNull()
    dark.unmount()

    stubColorScheme(true)
    render(<App />)
    expect(document.documentElement.classList.contains('cds--g10')).toBe(true)
    expect(document.documentElement.classList.contains('cds--g100')).toBe(false)
  })
})
