import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CompatibleEndpoint } from '../api/providers'
import { setLang } from '../i18n/i18n'
import { CompatibleEndpoints } from './CompatibleEndpoints'

const URL = '/api/providers/compatible'
const KEY = 'sk-compatible-ui-secret-4242'
const LOCAL: CompatibleEndpoint = {
  id: '0123456789ab',
  name: 'Local speech',
  base_url: 'http://127.0.0.1:8000/v1',
  cloud: false,
  cloud_consent: false,
  key_configured: true,
  stt_models: ['whisper'],
  tts_models: ['kokoro'],
  tts_voices: ['af_bella'],
}
const CLOUD: CompatibleEndpoint = {
  ...LOCAL,
  name: 'Remote speech',
  base_url: 'https://speech.example.com/v1',
  cloud: true,
  cloud_consent: true,
}
const CONSENT = 'Entiendo que el audio y el texto saldrán de mi equipo hacia este servidor.'

afterEach(() => {
  cleanup()
  setLang('es')
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>()
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function newForm(baseUrl: string) {
  await screen.findByRole('button', { name: 'Añadir servidor' })
  fireEvent.click(screen.getByRole('button', { name: 'Añadir servidor' }))
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Speech' } })
  fireEvent.change(screen.getByLabelText('URL base'), { target: { value: baseUrl } })
  fireEvent.change(screen.getByLabelText('Modelos de transcripción'), {
    target: { value: 'whisper' },
  })
}

describe('CompatibleEndpoints', () => {
  it('requires explicit CLOUD consent and clears it whenever the URL changes', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, []), jsonResponse(201, CLOUD), jsonResponse(200, [CLOUD]),
    )
    render(<CompatibleEndpoints />)
    await newForm(CLOUD.base_url)

    const save = screen.getByRole('button', { name: 'Guardar' })
    const consent = screen.getByRole('checkbox', { name: CONSENT })
    expect(consent).toHaveProperty('checked', false)
    expect(save).toHaveProperty('disabled', true)
    expect(screen.getByText(/se enviarán a speech.example.com/)).toBeDefined()
    const form = save.closest('form')
    if (!form) throw new Error('Missing endpoint form')
    fireEvent.submit(form)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    fireEvent.click(consent)
    expect(save).toHaveProperty('disabled', false)
    fireEvent.change(screen.getByLabelText('URL base'), {
      target: { value: 'https://other.example.com/v1' },
    })
    expect(consent).toHaveProperty('checked', false)
    expect(save).toHaveProperty('disabled', true)
    fireEvent.change(screen.getByLabelText('URL base'), {
      target: { value: CLOUD.base_url },
    })
    expect(consent).toHaveProperty('checked', false)
    fireEvent.click(consent)
    fireEvent.click(save)

    await screen.findByText('Servidor guardado.')
    expect(fetchMock.mock.calls[1]?.[0]).toBe(URL)
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        name: 'Speech', base_url: CLOUD.base_url, key: null, clear_key: false,
        stt_models: ['whisper'], tts_models: [], tts_voices: [], cloud_consent: true,
      }),
    })
  })

  it('labels saved remote endpoints CLOUD and never prechecks consent when editing', async () => {
    const fetchMock = stubFetch(jsonResponse(200, [CLOUD]))
    render(<CompatibleEndpoints />)
    await screen.findByRole('heading', { name: CLOUD.name })
    expect(screen.getByText('CLOUD')).toBeDefined()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    expect(screen.getByRole('checkbox', { name: CONSENT })).toHaveProperty('checked', false)
    expect(screen.getByRole('button', { name: 'Guardar' })).toHaveProperty('disabled', true)
    expect(screen.getByLabelText('Clave de API (opcional)')).toHaveProperty('value', '')
  })

  it.each([
    'http://localhost:8000/v1', 'http://127.9.8.7:8000/v1', 'http://[::1]:8000/v1',
  ])('allows loopback %s without CLOUD consent', async (baseUrl) => {
    stubFetch(jsonResponse(200, []))
    render(<CompatibleEndpoints />)
    await newForm(baseUrl)
    expect(screen.queryByRole('checkbox', { name: CONSENT })).toBeNull()
    expect(screen.getByRole('button', { name: 'Guardar' })).toHaveProperty('disabled', false)
  })

  it('sends a new key only in the save body and never fills it back in', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, []), jsonResponse(201, LOCAL), jsonResponse(200, [LOCAL]),
    )
    const onChanged = vi.fn()
    render(<CompatibleEndpoints onChanged={onChanged} />)
    await newForm(LOCAL.base_url)
    const input = screen.getByLabelText('Clave de API (opcional)')
    expect(input.getAttribute('type')).toBe('password')
    fireEvent.change(input, { target: { value: ' ' + KEY + ' ' } })
    expect(document.body.textContent).not.toContain(KEY)
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))

    await screen.findByText('Servidor guardado.')
    await screen.findByRole('heading', { name: LOCAL.name })
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[1]?.[0]).toBe(URL)
    expect(fetchMock.mock.calls[1]?.[1]?.body).toContain('"key":"' + KEY + '"')
    expect(fetchMock.mock.calls[1]?.[1]?.headers).not.toHaveProperty('Authorization')
    expect(document.body.innerHTML).not.toContain(KEY)
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    expect(screen.getByLabelText('Clave de API (opcional)')).toHaveProperty('value', '')
    expect(document.body.innerHTML).not.toContain(KEY)
  })

  it.each([false, true])('keeps stored keys unreadable while clear_key=%s', async (clearKey) => {
    const saved = { ...LOCAL, key_configured: !clearKey }
    const fetchMock = stubFetch(
      jsonResponse(200, [LOCAL]), jsonResponse(200, saved), jsonResponse(200, [saved]),
    )
    render(<CompatibleEndpoints />)
    await screen.findByRole('heading', { name: LOCAL.name })
    expect(screen.getByText('Clave guardada')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    const input = screen.getByLabelText('Clave de API (opcional)')
    expect(input).toHaveProperty('value', '')
    if (clearKey) {
      fireEvent.click(screen.getByRole('checkbox', { name: 'Quitar la clave guardada' }))
      expect(input).toHaveProperty('disabled', true)
    }
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Servidor guardado.')
    expect(fetchMock.mock.calls[1]?.[0]).toBe(URL + '/' + LOCAL.id)
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('PUT')
    expect(fetchMock.mock.calls[1]?.[1]?.body).toContain('"key":null')
    expect(fetchMock.mock.calls[1]?.[1]?.body).toContain('"clear_key":' + String(clearKey))
  })

  it('uses safe error codes and never renders or logs raw server messages', async () => {
    const logs = ['log', 'warn', 'error', 'debug'].map((method) =>
      vi.spyOn(console, method as 'log' | 'warn' | 'error' | 'debug'),
    )
    stubFetch(
      jsonResponse(200, []),
      jsonResponse(422, { detail: { code: 'endpoint_invalid', message: KEY, input: KEY } }),
    )
    render(<CompatibleEndpoints />)
    await newForm(LOCAL.base_url)
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    const message = await screen.findByText(/Revisa los datos/)
    expect(message.closest('[role="alert"]')).not.toBeNull()
    expect(document.body.innerHTML).not.toContain(KEY)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Guardar' })).toHaveProperty('disabled', false)
    })
    for (const log of logs) expect(JSON.stringify(log.mock.calls)).not.toContain(KEY)
  })

  it('refuses plain http to a remote host before saving', async () => {
    const fetchMock = stubFetch(jsonResponse(200, []))
    render(<CompatibleEndpoints />)
    await newForm('http://example.com/v1')
    expect(screen.getByText(/deben usar https:\/\//)).toBeDefined()
    fireEvent.click(screen.getByRole('checkbox', { name: CONSENT }))
    expect(screen.getByRole('button', { name: 'Guardar' })).toHaveProperty('disabled', true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows the server https hint when the API refuses the URL', async () => {
    stubFetch(jsonResponse(200, []), jsonResponse(422, { detail: { code: 'endpoint_invalid' } }))
    render(<CompatibleEndpoints />)
    await newForm(CLOUD.base_url)
    fireEvent.click(screen.getByRole('checkbox', { name: CONSENT }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText(/solo https:\/\//)).toBeDefined()
  })

  describe('saved key and origin', () => {
    const WARNING = 'La clave guardada se borrará al guardar'

    async function edit(nextUrl: string, [editLabel, urlLabel] = ['Editar', 'URL base']) {
      stubFetch(jsonResponse(200, [CLOUD]))
      render(<CompatibleEndpoints />)
      await screen.findByRole('heading', { name: CLOUD.name })
      fireEvent.click(screen.getByRole('button', { name: editLabel }))
      fireEvent.change(screen.getByLabelText(urlLabel), { target: { value: nextUrl } })
    }

    it.each([
      'https://other.example.com/v1',
      'https://speech.example.com:8443/v1',
      'http://speech.example.com/v1',
    ])('warns before saving when %s moves the origin without a new key', async (url) => {
      await edit(url)
      expect(screen.getByText(WARNING)).toBeDefined()
      expect(screen.getByText(/Vuelve a escribir la clave/)).toBeDefined()
    })

    it('does not warn for a path-only change, a new key or a cleared key', async () => {
      await edit('https://speech.example.com:443/other/')
      expect(screen.queryByText(WARNING)).toBeNull()
      fireEvent.change(screen.getByLabelText('URL base'), {
        target: { value: 'https://other.example.com/v1' },
      })
      expect(screen.getByText(WARNING)).toBeDefined()
      fireEvent.change(screen.getByLabelText('Clave de API (opcional)'), {
        target: { value: KEY },
      })
      expect(screen.queryByText(WARNING)).toBeNull()
      fireEvent.change(screen.getByLabelText('Clave de API (opcional)'), {
        target: { value: '' },
      })
      expect(screen.getByText(WARNING)).toBeDefined()
      fireEvent.click(screen.getByRole('checkbox', { name: 'Quitar la clave guardada' }))
      expect(screen.queryByText(WARNING)).toBeNull()
    })

    it('shows the warning in English too', async () => {
      setLang('en')
      await edit('https://other.example.com/v1', ['Edit', 'Base URL'])
      expect(screen.getByText('The saved key will be deleted when you save')).toBeDefined()
    })
  })
})
