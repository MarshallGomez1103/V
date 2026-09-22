import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TranscriptionOption } from '../api/transcriptionOptions'
import { TranscriptionOptionsSelector } from './TranscriptionOptionsSelector'

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

function option(
  overrides: Partial<TranscriptionOption> &
    Pick<TranscriptionOption, 'option_id'>,
): TranscriptionOption {
  return {
    provider_id: 'faster-whisper',
    model_id: 'turbo',
    source: 'Systran/faster-whisper-large-v3-turbo',
    revision: 'abc123',
    profile: {
      name: 'fast',
      device_preference: 'gpu_preferred',
      gpu_precisions: ['float16', 'int8_float16'],
      cpu_precision: 'int8',
    },
    display_name: 'Faster Whisper turbo',
    installation_status: 'registered',
    files_available: true,
    runtime_available: true,
    can_start: true,
    capabilities: ['cpu', 'gpu', 'language_detection', 'transcription'],
    execution: { device: 'cuda', precision: 'float16', fallback_reason: null },
    device_name: null,
    recommendation: { recommended: true, reason: 'default_compatible_profile' },
    blocking_reasons: [],
    ...overrides,
  }
}

const READY = option({ option_id: 'option-v1-ready' })

const BLOCKED = option({
  option_id: 'option-v1-blocked',
  model_id: 'large-v3',
  display_name: 'Faster Whisper large-v3',
  revision: null,
  profile: {
    name: 'quality',
    device_preference: 'gpu_preferred',
    gpu_precisions: ['float16'],
    cpu_precision: 'int8',
  },
  installation_status: 'not_registered',
  files_available: false,
  can_start: false,
  execution: null,
  recommendation: null,
  blocking_reasons: ['model_not_registered', 'model_files_missing'],
})

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>()
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('TranscriptionOptionsSelector', () => {
  it('lista una opción recomendada y otra bloqueada con razones en español', async () => {
    const fetchMock = stubFetch(jsonResponse(200, { options: [READY, BLOCKED] }))
    const onChange = vi.fn()

    render(<TranscriptionOptionsSelector value={READY.option_id} onChange={onChange} />)

    expect(
      screen.getByRole('group', { name: /modelo de transcripción/i }),
    ).toBeDefined()
    const ready = await screen.findByRole('radio', { name: /turbo/i })
    expect(ready).toHaveProperty('disabled', false)
    expect(ready).toHaveProperty('checked', true)
    expect(screen.getByText('Recomendado')).toBeDefined()
    expect(screen.getByText(/perfil: rápido/i)).toBeDefined()
    expect(screen.getByText(/ejecución: gpu \(cuda\) · float16/i)).toBeDefined()

    const blocked = screen.getByRole('radio', { name: /large-v3/i })
    expect(blocked).toHaveProperty('disabled', true)
    expect(
      screen.getByText('Modelo no instalado · Faltan archivos del modelo'),
    ).toBeDefined()
    expect(screen.getByText(/perfil: calidad/i)).toBeDefined()
    expect(screen.queryByText(/instala un modelo para transcribir/i)).toBeNull()
    expect(onChange).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcription-options',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('dispara onChange con el option_id al elegir una opción', async () => {
    const second = option({
      option_id: 'option-v1-second',
      model_id: 'large-v3',
      display_name: 'Faster Whisper large-v3',
      recommendation: null,
    })
    stubFetch(jsonResponse(200, { options: [READY, second] }))
    const onChange = vi.fn()

    render(<TranscriptionOptionsSelector value={null} onChange={onChange} />)

    fireEvent.click(await screen.findByRole('radio', { name: /large-v3/i }))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('option-v1-second')
  })

  it('preselecciona la única opción que puede iniciar cuando no hay valor', async () => {
    stubFetch(jsonResponse(200, { options: [BLOCKED, READY] }))
    const onChange = vi.fn()

    render(<TranscriptionOptionsSelector value={null} onChange={onChange} />)

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(READY.option_id)
    })
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('descarta una selección que ya no existe o no puede iniciar', async () => {
    stubFetch(jsonResponse(200, { options: [BLOCKED] }))
    const onChange = vi.fn()

    render(
      <TranscriptionOptionsSelector value="option-v1-gone" onChange={onChange} />,
    )

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(null)
    })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText(/instala un modelo para transcribir/i),
    ).toBeDefined()
  })

  it('muestra el error 503 con mensaje seguro y permite reintentar', async () => {
    const fetchMock = stubFetch(
      jsonResponse(503, {
        detail: {
          code: 'transcription_options_unavailable',
          message: 'Transcription options could not be inspected.',
        },
      }),
      jsonResponse(200, { options: [READY] }),
    )

    render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/no pudo inspeccionar los modelos locales/i)
    expect(alert.textContent).not.toMatch(/could not be inspected/i)

    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }))

    expect(await screen.findByRole('radio', { name: /turbo/i })).toBeDefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('pasa a estado de error si el payload no cumple el contrato', async () => {
    stubFetch(jsonResponse(200, { options: [{ option_id: 42 }] }))

    render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/formato inesperado/i)
    expect(screen.getByRole('button', { name: /reintentar/i })).toBeDefined()
  })

  it('aborta la petición al desmontar', () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock.mockReturnValue(new Promise<Response>(() => undefined))
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = render(
      <TranscriptionOptionsSelector value={null} onChange={vi.fn()} />,
    )

    const signal = fetchMock.mock.calls[0]?.[1]?.signal
    expect(signal).toBeInstanceOf(AbortSignal)
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })
})
