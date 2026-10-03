import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { JobView } from '../api/jobs'
import type { RecentJob } from '../hooks/useRecentJobs'
import { RecentJobs } from './RecentJobs'

afterEach(cleanup)

const item = (state: JobView['state'], id = 'j1'): RecentJob => ({
  project: { id: 'p1', name: 'Clase de cálculo', created_at: '2026-10-01T10:00:00Z' },
  job: {
    id,
    project_id: 'p1',
    media_asset_id: 'a1',
    state,
    progress: 1,
    error_code: null,
    transcript_id: 't1',
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:30:00Z',
  },
})

describe('RecentJobs', () => {
  it('cargando muestra el estado de carga', () => {
    render(<RecentJobs state={{ phase: 'loading' }} onOpen={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText('Buscando transcripciones guardadas…')).toBeDefined()
  })

  it('vacío explica cómo empezar', () => {
    render(<RecentJobs state={{ phase: 'ready', items: [] }} onOpen={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText(/todavía no hay transcripciones/i)).toBeDefined()
    expect(screen.getByText('Cómo empezar')).toBeDefined()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Ir a Modelos' }).getAttribute('href')).toBe('#modelos')
  })

  it('lista cada trabajo con su estado y abre el elegido', () => {
    const onOpen = vi.fn()
    render(
      <RecentJobs
        state={{ phase: 'ready', items: [item('COMPLETED', 'j1'), item('FAILED', 'j2')] }}
        onOpen={onOpen}
        onRetry={vi.fn()}
      />,
    )
    expect(screen.getAllByText('Clase de cálculo')).toHaveLength(2)
    expect(screen.getByText('Transcripción completada')).toBeDefined()
    expect(screen.getByText('La transcripción falló')).toBeDefined()

    fireEvent.click(screen.getAllByRole('button', { name: 'Abrir' })[1] as HTMLElement)
    expect((onOpen.mock.calls[0] as [RecentJob])[0].job.id).toBe('j2')
  })

  it('un error se explica y deja reintentar', () => {
    const onRetry = vi.fn()
    render(<RecentJobs state={{ phase: 'error', message: null }} onOpen={vi.fn()} onRetry={onRetry} />)
    expect(screen.getByText('No se pudieron consultar las transcripciones guardadas')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
