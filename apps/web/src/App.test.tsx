import {
  act,
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
            items: [],
            projects: [],
            jobs: [],
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
    window.location.hash = '#/nueva'
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

    const banner = screen.getByRole('banner', { name: 'V' })
    expect(within(banner).getByText('V')).toBeDefined()
    for (const name of ['Idioma', 'Ajustes', 'Cerrar servidor']) {
      expect(within(banner).getByRole('button', { name })).toBeDefined()
    }
    const nav = within(banner).getByRole('navigation', {
      name: 'Secciones de V',
    })
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Inicio', 'Transcribir', 'Voz', 'Modelos', 'Proveedores cloud'])
    expect(
      within(nav).getByRole('link', { name: 'Inicio' }).getAttribute('aria-current'),
    ).toBe('page')
    expect(screen.getByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()
  })

  it('el logo de V lleva a Inicio desde cualquier sección', () => {
    stubFetch()
    window.location.hash = '#/modelos'
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Modelos' })).toBeDefined()

    fireEvent.click(screen.getByRole('link', { name: 'V, ir al inicio' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()
    expect(window.location.hash).toBe('#/')
  })

  it('navega entre secciones y refleja la sección en el hash', async () => {
    stubFetch()
    render(<App />)
    const nav = screen.getByRole('navigation', { name: 'Secciones de V' })

    fireEvent.click(within(nav).getByRole('link', { name: 'Modelos' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Modelos' }),
    ).toBeDefined()
    expect(screen.queryByRole('heading', { level: 1, name: 'Transcripciones' })).toBeNull()
    expect(window.location.hash).toBe('#/modelos')

    fireEvent.click(within(nav).getByRole('link', { name: 'Proveedores cloud' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Proveedores cloud' }),
    ).toBeDefined()
  })

  it('Voz carga sus opciones y «Ir a Modelos» lleva al gestor', async () => {
    stubFetch()
    const generic = vi.mocked(fetch)
    const fallback = generic.getMockImplementation()
    generic.mockImplementation((input, init) =>
      typeof input === 'string' && input.includes('/api/synthesis/options')
        ? Promise.resolve({
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve({
                providers: [],
                models: [],
                max_chars: 20000,
                speed: { min: 0.5, max: 2 },
              }),
          } as Response)
        : (fallback?.(input, init) as Promise<Response>),
    )
    render(<App />)
    const nav = screen.getByRole('navigation', { name: 'Secciones de V' })

    fireEvent.click(within(nav).getByRole('link', { name: 'Voz' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Texto a voz' })).toBeDefined()
    expect(window.location.hash).toBe('#/speak')

    fireEvent.click(await screen.findByRole('button', { name: 'Ir a Modelos' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Modelos' })).toBeDefined()
    expect(window.location.hash).toBe('#/modelos')
  })

  it('Atrás y Adelante del navegador cambian de sección', async () => {
    stubFetch()
    render(<App />)
    const nav = screen.getByRole('navigation', { name: 'Secciones de V' })
    fireEvent.click(within(nav).getByRole('link', { name: 'Modelos' }))
    fireEvent.click(within(nav).getByRole('link', { name: 'Proveedores cloud' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Proveedores cloud' })).toBeDefined()

    act(() => {
      window.location.hash = '#/modelos'
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Modelos' })).toBeDefined()
    act(() => {
      window.location.hash = '#/'
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()
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
