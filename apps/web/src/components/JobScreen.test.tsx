import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { JobState, JobView } from '../api/jobs'
import { JobScreen } from './JobScreen'

afterEach(() => {
  cleanup()
})

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

function currentStep(): HTMLElement {
  const stepper = screen.getByRole('list', { name: 'Etapas' })
  const current = within(stepper)
    .getAllByRole('listitem')
    .find((item) => item.getAttribute('aria-current') === 'step')
  if (!current) {
    throw new Error('No hay paso actual')
  }
  return current
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
    expect(currentStep().textContent).toBe('En cola')
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
    expect(screen.getByRole('progressbar')).toHaveProperty('value', 0.42)
    expect(currentStep().textContent).toBe('Transcribiendo')
    expect(screen.getByText('large-v3')).toBeDefined()
    expect(screen.getByText('Equilibrado')).toBeDefined()
    expect(screen.getByText('cuda')).toBeDefined()
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
    expect(currentStep().textContent).toBe('Resultado')
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('FAILED muestra un error seguro con el código', () => {
    render(<JobScreen job={makeJob('FAILED', { error_code: 'gpu_lost' })} />)

    expect(screen.getByRole('alert').textContent).toBe(
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

    expect(screen.getByRole('status').textContent).toMatch(/cancelaste/i)
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })
})
