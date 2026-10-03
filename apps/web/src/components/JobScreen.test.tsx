import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { JobState, JobView } from '../api/jobs'
import { JobScreen } from './JobScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

// El backend dice qué proveedores son cloud y cómo se llaman.
const PROVIDERS = [
  { id: 'openai', label: 'OpenAI', privacy_url: null, configured: true, cloud: true },
  { id: 'acme', label: 'Acme Cloud', privacy_url: null, configured: false, cloud: true },
]

function stubProviders(body: unknown = PROVIDERS, ok = true) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(body),
  } as unknown as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function makeJob(state: JobState, overrides: Partial<JobView> = {}): JobView {
  return {
    id: 'job-1',
    project_id: 'project-1',
    media_asset_id: 'asset-1',
    state,
    progress: 0,
    error_code: null,
    transcript_id: null,
    created_at: '2026-09-21T10:00:00Z',
    updated_at: '2026-09-21T10:00:00Z',
    ...overrides,
  }
}

/** Texto de la etapa marcada como actual (aria-current="step"). */
function currentStep(): string | null {
  const stepper = screen.getByRole('list', { name: 'Etapas' })
  const label = within(stepper).getByRole('listitem', { current: 'step' }).querySelector('.voz-stage__label')
  return label?.textContent ?? null
}

function stageNames(): string[] {
  const stepper = screen.getByRole('list', { name: 'Etapas' })
  return within(stepper)
    .getAllByRole('listitem')
    .map((item) => (item.querySelector('.voz-stage__label')?.textContent ?? '').replace(/^\d+/, ''))
}

describe('JobScreen', () => {
  it('muestra el estado vacío cuando no hay trabajo', () => {
    render(<JobScreen job={null} />)

    expect(screen.getByText(/sin transcripción/i)).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })

  it('QUEUED marca la fase "En cola" y ofrece cancelar', () => {
    render(<JobScreen job={makeJob('QUEUED')} onCancel={() => undefined} />)

    expect(
      screen.getByRole('heading', { name: /en cola, esperando turno/i }),
    ).toBeDefined()
    expect(currentStep()).toContain('Preparando')
    expect(screen.getByText('En cola')).toBeDefined()
    expect(screen.getByText('0 %')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveProperty(
      'disabled',
      false,
    )
  })

  it('TRANSCRIBING al 0.42 muestra "42 %" y la fase Transcribiendo', () => {
    render(
      <JobScreen
        job={makeJob('TRANSCRIBING', {
          progress: 0.42,
          selection: {
            option_id: 'opt-1',
            provider_id: 'faster-whisper',
            model_id: 'large-v3',
            profile: { name: 'Equilibrado' },
            execution: { device: 'cuda' },
          },
        })}
      />,
    )

    expect(screen.getByText('42 %')).toBeDefined()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('42')
    expect(currentStep()).toContain('Transcribiendo')
    expect(screen.getByText('large-v3')).toBeDefined()
    expect(screen.getByText('Equilibrado')).toBeDefined()
    expect(screen.getByText('GPU (CUDA)')).toBeDefined()
  })

  it('COMPLETED llega a la fase final sin botón de cancelar', () => {
    render(
      <JobScreen
        job={makeJob('COMPLETED', { progress: 1, transcript_id: 'tr-1' })}
        onCancel={() => undefined}
      />,
    )

    expect(
      screen.getByRole('heading', { name: /transcripción completada/i }),
    ).toBeDefined()
    expect(stageNames().every((name) => name.length > 0)).toBe(true)
    expect(screen.getAllByText('Listo').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('FAILED muestra un error seguro con el código', () => {
    render(<JobScreen job={makeJob('FAILED', { error_code: 'gpu_lost' })} />)

    expect(screen.getByRole('alert').textContent).toContain(
      'La transcripción falló (código gpu_lost).',
    )
  })

  it('CANCELLING deshabilita el botón de cancelar', () => {
    const onCancel = vi.fn()
    render(<JobScreen job={makeJob('CANCELLING')} onCancel={onCancel} />)

    const button = screen.getByRole('button', { name: 'Cancelar' })
    expect(button).toHaveProperty('disabled', true)
    fireEvent.click(button)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('invoca onCancel al pulsar Cancelar', () => {
    const onCancel = vi.fn()
    render(<JobScreen job={makeJob('PREPROCESSING')} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('CANCELLED muestra el aviso de cancelación', () => {
    render(<JobScreen job={makeJob('CANCELLED')} />)

    expect(screen.getByText(/cancelaste esta transcripción/i)).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })

  it('muestra el badge CLOUD y el aviso de privacidad mientras corre un job cloud', async () => {
    stubProviders()
    render(
      <JobScreen
        job={makeJob('TRANSCRIBING', {
          progress: 0.3,
          selection: {
            option_id: 'opt-c',
            provider_id: 'openai',
            model_id: 'whisper-1',
          },
        })}
      />,
    )

    const note = await screen.findByRole('note')
    expect(within(note).getByText('CLOUD')).toBeDefined()
    expect(note.textContent).toMatch(/se envía a openai mientras dura/i)
  })

  it('conserva el badge CLOUD al terminar, en pasado y con el nombre del backend', async () => {
    stubProviders()
    render(
      <JobScreen
        job={makeJob('COMPLETED', {
          progress: 1,
          transcript_id: 'tr-1',
          selection: {
            option_id: 'o',
            provider_id: 'acme',
            model_id: 'scribe',
          },
        })}
      />,
    )

    expect((await screen.findByRole('note')).textContent).toMatch(
      /usó acme cloud \(cloud\): tu audio salió de tu equipo/i,
    )
  })

  it('un job local no muestra badge CLOUD', async () => {
    const fetchMock = stubProviders()
    render(
      <JobScreen
        job={makeJob('TRANSCRIBING', {
          selection: {
            option_id: 'o',
            provider_id: 'faster-whisper',
            model_id: 'turbo',
          },
        })}
      />,
    )

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    expect(screen.queryByText('CLOUD')).toBeNull()
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('si no se pueden consultar los proveedores no rompe ni inventa el aviso', async () => {
    const fetchMock = stubProviders({}, false)
    render(
      <JobScreen
        job={makeJob('TRANSCRIBING', {
          selection: { option_id: 'o', provider_id: 'openai', model_id: 'm' },
        })}
      />,
    )

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    expect(screen.queryByRole('note')).toBeNull()
    expect(screen.getByRole('heading', { name: /transcribiendo/i })).toBeDefined()
  })

  describe('progreso en vivo', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    const diarizing = {
      option_id: 'o',
      provider_id: 'faster-whisper',
      model_id: 'turbo',
      diarization: { enabled: true },
    }

    it('el tiempo transcurrido corre cada segundo y el restante cuenta hacia atrás', () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-09-21T10:00:10Z'))
      stubProviders()
      render(
        <JobScreen
          job={makeJob('TRANSCRIBING', {
            progress: 0.3,
            started_at: '2026-09-21T10:00:00Z',
            stage_started_at: '2026-09-21T10:00:04Z',
            stage_progress: 0.5,
            eta_seconds: 60,
            updated_at: '2026-09-21T10:00:10Z',
          })}
        />,
      )
      act(() => {
        vi.advanceTimersByTime(0)
      })

      expect(screen.getByText('0:10')).toBeDefined()
      expect(screen.getByText('0:06')).toBeDefined() // en esta etapa
      expect(screen.getByText('≈ 1:00')).toBeDefined()

      act(() => {
        vi.advanceTimersByTime(5000)
      })
      expect(screen.getByText('0:15')).toBeDefined()
      expect(screen.getByText('0:11')).toBeDefined()
      expect(screen.getByText('≈ 0:55')).toBeDefined()
    })

    it('sin estimación dice que la está calculando y no inventa un número', () => {
      render(<JobScreen job={makeJob('PREPROCESSING', { eta_seconds: null })} />)
      expect(screen.getByText('Calculando…')).toBeDefined()
    })

    it('muestra el avance de la etapa actual y lo cuenta en una frase', () => {
      render(
        <JobScreen
          job={makeJob('TRANSCRIBING', { progress: 0.4, stage_progress: 0.62 })}
        />,
      )
      expect(screen.getByText('62 % de la etapa')).toBeDefined()
      expect(screen.getByText(/va por el 62 % del audio/i)).toBeDefined()
    })

    it('la etapa «Hablantes» aparece solo si se pidieron y DIARIZING con texto lo explica', () => {
      const { rerender } = render(<JobScreen job={makeJob('TRANSCRIBING')} />)
      expect(stageNames()).toEqual(['Preparando', 'Transcribiendo', 'Guardando'])

      rerender(
        <JobScreen
          job={makeJob('DIARIZING', {
            progress: 0.8,
            stage_progress: 0.25,
            transcript_id: 'tr-1',
            selection: diarizing,
          })}
        />,
      )
      expect(stageNames()).toEqual([
        'Preparando',
        'Transcribiendo',
        'Hablantes',
        'Guardando',
      ])
      expect(currentStep()).toContain('Hablantes')
      expect(screen.getByText('25 % de la etapa')).toBeDefined()
      expect(screen.getByText(/el texto ya está completo/i)).toBeDefined()
    })

    it('la barra no se queda en 100 % durante la etapa de hablantes', () => {
      render(
        <JobScreen
          job={makeJob('DIARIZING', { progress: 0.85, selection: diarizing })}
        />,
      )
      expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('85')
    })

    it('al terminar muestra la duración total y ofrece ajustar y repetir', () => {
      const onAdjust = vi.fn()
      render(
        <JobScreen
          job={makeJob('COMPLETED', {
            progress: 1,
            transcript_id: 'tr-1',
            started_at: '2026-09-21T10:00:00Z',
            updated_at: '2026-09-21T10:01:30Z',
          })}
          onAdjust={onAdjust}
        />,
      )
      expect(screen.getByText('Duración del trabajo')).toBeDefined()
      expect(screen.getByText('1:30')).toBeDefined()
      fireEvent.click(screen.getByRole('button', { name: 'Ajustar y repetir' }))
      expect(onAdjust).toHaveBeenCalledTimes(1)
    })

    it('en inglés todo el panel habla inglés', async () => {
      const { setLang } = await import('../i18n/i18n')
      setLang('en')
      render(<JobScreen job={makeJob('TRANSCRIBING', { stage_progress: 0.1 })} />)
      expect(screen.getByRole('heading', { name: 'Transcribing the audio' })).toBeDefined()
      expect(screen.getByText('Overall progress')).toBeDefined()
      expect(screen.getByText('Estimated remaining')).toBeDefined()
    })
  })
})
