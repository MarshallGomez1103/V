import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProvidersSettings } from './ProvidersSettings'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function noContent(): Response {
  return {
    ok: true,
    status: 204,
    json: () => Promise.reject(new SyntaxError('sin cuerpo')),
  } as unknown as Response
}

// El backend decide qué proveedores existen, su nombre y su política.
const OPENAI = {
  id: 'openai',
  label: 'OpenAI',
  privacy_url: 'https://openai.com/policies/privacy-policy',
  configured: true,
  cloud: true,
}
const ACME = {
  id: 'acme',
  label: 'Acme Cloud',
  privacy_url: 'https://acme.example/privacy',
  configured: false,
  cloud: true,
}
const LIST = [OPENAI, ACME]

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>()
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function row(name: string): HTMLElement {
  const item = screen.getByRole('heading', { name }).closest('li')
  if (!item) {
    throw new Error('Sin fila ' + name)
  }
  return item
}

describe('ProvidersSettings', () => {
  it('lista los proveedores del backend con su estado y enlaces de privacidad', async () => {
    stubFetch(jsonResponse(200, LIST))

    render(<ProvidersSettings />)

    await screen.findByRole('heading', { name: 'OpenAI' })
    expect(within(row('OpenAI')).getByText('Configurado')).toBeDefined()
    expect(within(row('Acme Cloud')).getByText('No configurado')).toBeDefined()
    expect(
      screen
        .getByRole('link', { name: /privacidad de openai/i })
        .getAttribute('href'),
    ).toMatch(/^https:\/\/openai\.com/)
    expect(
      screen
        .getByRole('link', { name: /privacidad de acme cloud/i })
        .getAttribute('href'),
    ).toBe('https://acme.example/privacy')
  })

  it('sin privacy_url no muestra enlace y no inventa proveedores', async () => {
    stubFetch(jsonResponse(200, [{ ...ACME, privacy_url: null }]))

    render(<ProvidersSettings />)

    await screen.findByRole('heading', { name: 'Acme Cloud' })
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'OpenAI' })).toBeNull()
  })

  it('el campo de clave es password, nunca muestra una clave existente', async () => {
    stubFetch(jsonResponse(200, LIST))

    render(<ProvidersSettings />)

    const input = await screen.findByLabelText('Clave de API de OpenAI')
    expect(input.getAttribute('type')).toBe('password')
    expect(input).toHaveProperty('value', '')
    expect(
      within(row('OpenAI')).getByRole('button', { name: 'Eliminar' }),
    ).toHaveProperty('disabled', false)
    expect(
      within(row('Acme Cloud')).getByRole('button', { name: 'Eliminar' }),
    ).toHaveProperty('disabled', true)
  })

  it('guarda la clave con PUT, vacía el campo y recarga el estado', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, LIST),
      noContent(),
      jsonResponse(200, [OPENAI, { ...ACME, configured: true }]),
    )

    render(<ProvidersSettings />)

    const input = await screen.findByLabelText('Clave de API de Acme Cloud')
    const save = within(row('Acme Cloud')).getByRole('button', {
      name: 'Guardar',
    })
    expect(save).toHaveProperty('disabled', true)
    fireEvent.change(input, { target: { value: ' xi-secreta ' } })
    fireEvent.click(save)

    await waitFor(() => {
      expect(within(row('Acme Cloud')).getByText('Configurado')).toBeDefined()
    })
    const [url, init] = fetchMock.mock.calls[1] ?? []
    expect(url).toBe('/api/providers/acme/key')
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ key: 'xi-secreta' }))
    expect(screen.getByLabelText('Clave de API de Acme Cloud')).toHaveProperty(
      'value',
      '',
    )
    expect(document.body.textContent).not.toContain('xi-secreta')
  })

  it('muestra el error por código en español y conserva el estado', async () => {
    stubFetch(
      jsonResponse(200, LIST),
      jsonResponse(409, {
        detail: { code: 'secrets_file_insecure', message: 'x' },
      }),
    )

    render(<ProvidersSettings />)

    const input = await screen.findByLabelText('Clave de API de Acme Cloud')
    fireEvent.change(input, { target: { value: 'k' } })
    fireEvent.click(
      within(row('Acme Cloud')).getByRole('button', { name: 'Guardar' }),
    )

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/0600/)
    expect(within(row('Acme Cloud')).getByText('No configurado')).toBeDefined()
  })

  it('elimina la clave con DELETE', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, LIST),
      noContent(),
      jsonResponse(200, [{ ...OPENAI, configured: false }, ACME]),
    )

    render(<ProvidersSettings />)

    await screen.findByRole('heading', { name: 'OpenAI' })
    fireEvent.click(
      within(row('OpenAI')).getByRole('button', { name: 'Eliminar' }),
    )

    await waitFor(() => {
      expect(within(row('OpenAI')).getByText('No configurado')).toBeDefined()
    })
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/providers/openai/key')
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('DELETE')
  })

  it('si falla la lista permite reintentar', async () => {
    stubFetch(
      jsonResponse(500, { detail: { code: 'boom', message: 'x' } }),
      jsonResponse(200, LIST),
    )

    render(<ProvidersSettings />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/boom/)
    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }))

    expect(await screen.findByRole('heading', { name: 'OpenAI' })).toBeDefined()
  })
})
