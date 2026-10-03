import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { useState } from 'react'
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

    const ready = await screen.findByRole('radio', { name: /turbo/i })
    expect(
      screen.getByRole('group', { name: /modelo de transcripción/i }),
    ).toBeDefined()
    expect(ready).toHaveProperty('disabled', false)
    expect(ready).toHaveProperty('checked', true)
    expect(screen.getByText('Recomendado')).toBeDefined()
    expect(screen.getByText(/perfil: rápido/i)).toBeDefined()
    expect(screen.getByText(/ejecución: gpu \(cuda\) · float16/i)).toBeDefined()

    // La opción no disponible no es elegible: va en la lista plegada con su motivo.
    expect(screen.queryByRole('radio', { name: /large-v3/i })).toBeNull()
    expect(screen.getByText('Mostrar 1 motor no disponible')).toBeDefined()
    expect(
      screen.getByText('Modelo no instalado · Faltan archivos del modelo'),
    ).toBeDefined()
    expect(screen.getByRole('link', { name: 'Ir a Modelos' }).getAttribute('href')).toBe(
      '#modelos',
    )
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
    fireEvent.click(screen.getByRole('button', { name: 'Ir a Modelos' }))
    expect(window.location.hash).toBe('#modelos')
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

  it('ordena por catálogo con las opciones iniciables primero', async () => {
    const tiny = option({
      option_id: 'o-tiny',
      model_id: 'tiny',
      display_name: 'Faster Whisper tiny',
      recommendation: null,
    })
    const small = option({
      option_id: 'o-small',
      model_id: 'small',
      display_name: 'Faster Whisper small',
      recommendation: null,
    })
    const custom = option({
      option_id: 'o-custom',
      model_id: 'zzz-custom',
      display_name: 'Custom',
      recommendation: null,
    })
    stubFetch(jsonResponse(200, { options: [custom, BLOCKED, tiny, small, READY] }))

    render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

    await screen.findAllByRole('radio')
    expect(
      screen.getAllByRole('radio').map((radio) => radio.getAttribute('value')),
    ).toEqual(['option-v1-ready', 'o-small', 'o-tiny', 'o-custom'])
  })

  it('vuelve a pedir las opciones cuando cambia refreshKey', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, { options: [BLOCKED] }),
      jsonResponse(200, { options: [READY] }),
    )

    const { rerender } = render(
      <TranscriptionOptionsSelector value={null} onChange={vi.fn()} refreshKey={0} />,
    )
    expect(await screen.findByText('Mostrar 1 motor no disponible')).toBeDefined()
    expect(screen.queryByRole('radio')).toBeNull()

    rerender(
      <TranscriptionOptionsSelector value={null} onChange={vi.fn()} refreshKey={1} />,
    )

    const ready = await screen.findByRole('radio', { name: /turbo/i })
    expect(ready).toHaveProperty('disabled', false)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  describe('opciones cloud (S11.09)', () => {
    const CLOUD = {
      option_id: 'option-v1-openai',
      provider_id: 'openai',
      model_id: 'whisper-1',
      display_name: 'OpenAI Whisper',
      profile: null,
      execution: null,
      recommendation: null,
      cloud: true,
      provider_label: 'OpenAI',
    }
    const ESTIMATE = {
      minutes: 5,
      usd: 0.03,
      price_source: 'https://platform.openai.com/pricing',
      price_date: '2026-09-30',
    }

    function cloudOption(overrides: Record<string, unknown> = {}) {
      return { ...option({ option_id: 'x' }), ...CLOUD, ...overrides }
    }

    it('muestra el badge CLOUD y el texto de envío en la opción, sin recomendarla', async () => {
      stubFetch(jsonResponse(200, { options: [cloudOption()] }))

      render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

      await screen.findByRole('radio', { name: /openai whisper/i })
      expect(screen.getByText('CLOUD')).toBeDefined()
      expect(screen.getByText(/tu audio se enviará a openai/i)).toBeDefined()
      expect(screen.queryByText('Recomendado')).toBeNull()
    })

    it('usa el nombre del proveedor que publica el backend, no una lista propia', async () => {
      stubFetch(
        jsonResponse(200, {
          options: [
            cloudOption({
              provider_id: 'acme',
              provider_label: 'Acme Cloud',
              can_start: false,
            }),
          ],
        }),
      )

      render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

      expect(await screen.findByText(/sin clave de acme cloud/i)).toBeDefined()
      expect(screen.queryByRole('radio')).toBeNull()
    })

    it('no recomienda una opción cloud aunque el backend lo marque', async () => {
      stubFetch(
        jsonResponse(200, {
          options: [
            cloudOption({
              recommendation: { recommended: true, reason: 'default' },
            }),
          ],
        }),
      )

      render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

      await screen.findByRole('radio', { name: /openai whisper/i })
      expect(screen.queryByText('Recomendado')).toBeNull()
    })

    it('nunca preselecciona una opción cloud, aunque sea la única iniciable', async () => {
      stubFetch(jsonResponse(200, { options: [cloudOption(), BLOCKED] }))
      const onChange = vi.fn()

      render(<TranscriptionOptionsSelector value={null} onChange={onChange} />)

      await screen.findByRole('radio', { name: /openai whisper/i })
      expect(onChange).not.toHaveBeenCalled()
    })

    it('al elegirla pide consentimiento y muestra el costo estimado', async () => {
      const fetchMock = stubFetch(
        jsonResponse(200, { options: [cloudOption()] }),
        jsonResponse(200, ESTIMATE),
      )
      const onConsent = vi.fn()

      render(
        <TranscriptionOptionsSelector
          value="option-v1-openai"
          onChange={vi.fn()}
          mediaAssetId="m-1"
          onCloudConsentChange={onConsent}
        />,
      )

      const checkbox = await screen.findByRole('checkbox', {
        name: /entiendo que el audio sale de mi equipo/i,
      })
      expect(checkbox).toHaveProperty('checked', false)
      expect(onConsent).toHaveBeenLastCalledWith(false)
      expect(await screen.findByText(/costo estimado: 5 min/i)).toBeDefined()
      expect(screen.getByText(/0,03 usd/i)).toBeDefined()
      expect(fetchMock.mock.calls[1]?.[0]).toBe(
        '/api/providers/openai/estimate?media_asset_id=m-1&model=whisper-1',
      )

      fireEvent.click(checkbox)

      expect(onConsent).toHaveBeenLastCalledWith(true)
    })

    it('si la estimación falla lo dice y el consentimiento sigue siendo obligatorio', async () => {
      stubFetch(
        jsonResponse(200, { options: [cloudOption()] }),
        jsonResponse(409, {
          detail: { code: 'media_duration_unknown', message: 'x' },
        }),
      )
      const onConsent = vi.fn()

      render(
        <TranscriptionOptionsSelector
          value="option-v1-openai"
          onChange={vi.fn()}
          mediaAssetId="m-1"
          onCloudConsentChange={onConsent}
        />,
      )

      expect(await screen.findByText(/no se pudo estimar el costo/i)).toBeDefined()
      expect(onConsent).toHaveBeenLastCalledWith(false)
    })

    it('una opción local no pide consentimiento ni estima', async () => {
      const fetchMock = stubFetch(jsonResponse(200, { options: [READY] }))
      const onConsent = vi.fn()

      render(
        <TranscriptionOptionsSelector
          value={READY.option_id}
          onChange={vi.fn()}
          mediaAssetId="m-1"
          onCloudConsentChange={onConsent}
        />,
      )

      await screen.findByRole('radio', { name: /turbo/i })
      expect(screen.queryByRole('checkbox')).toBeNull()
      expect(onConsent).toHaveBeenLastCalledWith(true)
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('sin clave la opción cloud queda bloqueada con la razón en español', async () => {
      stubFetch(
        jsonResponse(200, {
          options: [
            cloudOption({
              can_start: false,
              blocking_reasons: ['model_not_registered'],
            }),
          ],
        }),
      )

      render(<TranscriptionOptionsSelector value={null} onChange={vi.fn()} />)

      expect(await screen.findByText(/sin clave de openai/i)).toBeDefined()
      expect(screen.queryByRole('radio')).toBeNull()
      expect(
        screen.getByRole('link', { name: 'Ir a Proveedores cloud' }).getAttribute('href'),
      ).toBe('#proveedores')
    })

    it('cambiar a otra opción invalida el consentimiento dado', async () => {
      stubFetch(
        jsonResponse(200, {
          options: [
            cloudOption(),
            cloudOption({
              option_id: 'option-v1-acme',
              provider_id: 'acme',
              provider_label: 'Acme Cloud',
              model_id: 'scribe_v1',
              display_name: 'Acme Scribe',
            }),
          ],
        }),
      )
      const onConsent = vi.fn()

      function Harness() {
        const [value, setValue] = useState<string | null>('option-v1-openai')
        return (
          <TranscriptionOptionsSelector
            value={value}
            onChange={setValue}
            onCloudConsentChange={onConsent}
          />
        )
      }
      render(<Harness />)

      fireEvent.click(
        await screen.findByRole('checkbox', { name: /entiendo que el audio/i }),
      )
      expect(onConsent).toHaveBeenLastCalledWith(true)

      fireEvent.click(screen.getByRole('radio', { name: /acme scribe/i }))

      expect(onConsent).toHaveBeenLastCalledWith(false)
      expect(
        screen.getByRole('checkbox', { name: /entiendo que el audio/i }),
      ).toHaveProperty('checked', false)
    })
  })
})
