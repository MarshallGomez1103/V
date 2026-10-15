import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  deleteSynthesis,
  listSynthesis,
  SynthesisApiError,
  type SynthesisModel,
  type SynthesisView,
} from '../api/synthesis'
import { localeOf, setLang } from '../i18n/i18n'
import type { AudioPlayerProps } from './AudioPlayer'
import { SpeakHistory } from './SpeakHistory'

vi.mock('../api/synthesis', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/synthesis')>(),
  listSynthesis: vi.fn(),
  deleteSynthesis: vi.fn(),
}))

vi.mock('./AudioPlayer', () => ({
  AudioPlayer: ({ src, mediaAssetId, durationMs }: AudioPlayerProps) => (
    <div role="group" aria-label="Audio player" data-src={src}
      data-id={mediaAssetId} data-duration={durationMs} />
  ),
}))

const MODEL: SynthesisModel = {
  provider_id: 'sherpa-onnx', model_id: 'kokoro', display_name: 'Kokoro',
  runtime_ready: true, languages: ['es'],
  voices: [{ id: '20', name: 'Dora', languages: ['es'] }],
}

function job(overrides: Partial<SynthesisView> = {}): SynthesisView {
  return {
    id: 'job-1', state: 'COMPLETED', progress: 1, chunks_done: 1, chunks_total: 1,
    error_code: null, created_at: '2026-10-15T15:30:00Z', updated_at: '2026-10-15T15:30:10Z',
    started_at: '2026-10-15T15:30:01Z', provider_id: MODEL.provider_id,
    model_id: MODEL.model_id, voice_id: '20', language: 'es', speed: 1,
    text_length: overrides.text_preview?.length ?? 12, text_preview: 'Hola, mundo.',
    audio: { duration_ms: 65_000, sample_rate: 24_000, size_bytes: 3120000, url: '/untrusted-url' },
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function row(text = 'Hola, mundo.'): HTMLElement {
  const item = screen.getByText(text).closest('li')
  if (!item) throw new Error('Missing history row')
  return item
}

const list = vi.mocked(listSynthesis)
const remove = vi.mocked(deleteSynthesis)

beforeEach(() => {
  vi.resetAllMocks()
  list.mockResolvedValue([job()])
  remove.mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
})

describe('SpeakHistory', () => {
  it('shows loading and then empty history without requiring installed models', async () => {
    const pending = deferred<SynthesisView[]>()
    list.mockReturnValueOnce(pending.promise)
    render(<SpeakHistory />)
    expect(screen.getByText('Cargando el historial…')).toBeDefined()
    expect(list).toHaveBeenCalledWith(undefined, expect.any(AbortSignal))
    await act(async () => { pending.resolve([]); await pending.promise })
    expect(screen.getByText('Aún no hay generaciones guardadas.')).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).toBeNull()
  })

  it('shows a truncated preview, voice, duration and localized date, preserving API order', async () => {
    const preview = 'a'.repeat(160)
    const first = job({ text_preview: preview, text_length: 300, text: 'FULL TEXT MUST STAY HIDDEN' })
    list.mockResolvedValue([first, job({ id: 'older', text_preview: 'Anterior' })])
    render(<SpeakHistory models={[MODEL]} />)
    await screen.findByText(preview + '…')
    const rows = screen.getAllByRole('listitem')
    expect(rows[0]?.textContent).toContain(preview + '…')
    expect(rows[1]?.textContent).toContain('Anterior')
    expect(within(rows[0]!).getByText('Dora')).toBeDefined()
    expect(within(rows[0]!).getByText('1:05')).toBeDefined()
    const time = rows[0]?.querySelector('time')
    expect(time?.getAttribute('datetime')).toBe(first.created_at)
    expect(time?.textContent).toBe(new Date(first.created_at).toLocaleString(localeOf('es'), {
      dateStyle: 'medium', timeStyle: 'short',
    }))
    expect(document.body.textContent).not.toContain('FULL TEXT MUST STAY HIDDEN')
    expect(document.body.innerHTML).not.toContain('/untrusted-url')
  })

  it.each([
    { models: [] },
    { models: [{ ...MODEL, provider_id: 'other' }] },
    { models: [{ ...MODEL, model_id: 'other' }] },
    { models: [{ ...MODEL, voices: [] }] },
  ])('uses voice_id if the exact provider/model/voice is unavailable (%j)', async ({ models }) => {
    render(<SpeakHistory models={models} />)
    await screen.findByText('Hola, mundo.')
    expect(within(row()).getByText('20')).toBeDefined()
    expect(screen.queryByText('Dora')).toBeNull()
    expect(screen.getByRole('link', { name: 'Descargar WAV' }).getAttribute('href'))
      .toBe('/api/synthesis/job-1/audio?download=true')
  })

  it('updates labels and dates when switching language without fetching again', async () => {
    render(<SpeakHistory />)
    await screen.findByText('Hola, mundo.')
    act(() => { setLang('en') })
    expect(screen.getByRole('heading', { name: 'Speech history' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Listen' })).toBeDefined()
    expect(row().querySelector('time')?.textContent).toBe(
      new Date(job().created_at).toLocaleString(localeOf('en'), {
        dateStyle: 'medium', timeStyle: 'short',
      }),
    )
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('offers playback and downloads only for completed jobs with audio and no delete for active jobs', async () => {
    const states = ['QUEUED', 'RUNNING', 'PERSISTING', 'CANCELLING', 'FAILED', 'CANCELLED'] as const
    list.mockResolvedValue([
      ...states.map((state) => job({ id: state, state, text_preview: state })),
      job({ id: 'no-audio', audio: null, text_preview: 'No audio' }),
      job(),
    ])
    render(<SpeakHistory />)
    await screen.findByText('Hola, mundo.')
    expect(screen.getAllByRole('button', { name: 'Escuchar' })).toHaveLength(1)
    expect(screen.getAllByRole('link', { name: 'Descargar WAV' })).toHaveLength(1)
    for (const state of states) {
      const item = within(row(state))
      expect(item.queryByRole('button', { name: 'Escuchar' })).toBeNull()
      expect(item.queryByRole('link')).toBeNull()
      expect(item.queryByRole('button', { name: 'Eliminar' }) !== null)
        .toBe(state === 'FAILED' || state === 'CANCELLED')
    }
    expect(remove).not.toHaveBeenCalled()
  })

  it('opens one AudioPlayer at a time using the job audio route, and allows closing it', async () => {
    list.mockResolvedValue([job(), job({ id: 'second', text_preview: 'Segundo' })])
    render(<SpeakHistory />)
    await screen.findByText('Hola, mundo.')
    expect(screen.queryByRole('group', { name: 'Audio player' })).toBeNull()
    fireEvent.click(within(row()).getByRole('button', { name: 'Escuchar' }))
    let player = screen.getByRole('group', { name: 'Audio player' })
    expect(player.getAttribute('data-src')).toBe('/api/synthesis/job-1/audio')
    expect(player.getAttribute('data-duration')).toBe('65000')
    fireEvent.click(within(row('Segundo')).getByRole('button', { name: 'Escuchar' }))
    player = screen.getByRole('group', { name: 'Audio player' })
    expect(player.getAttribute('data-id')).toBe('second')
    expect(within(row()).queryByRole('group')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar reproductor' }))
    expect(screen.queryByRole('group', { name: 'Audio player' })).toBeNull()
  })

  it('requires confirmation, allows cancellation, and notifies deletion only after success', async () => {
    const onDeleted = vi.fn()
    const pending = deferred<void>()
    remove.mockReturnValueOnce(pending.promise)
    list.mockResolvedValueOnce([job()]).mockResolvedValue([])
    render(<SpeakHistory onDeleted={onDeleted} />)
    await screen.findByText('Hola, mundo.')
    fireEvent.click(screen.getByRole('button', { name: 'Escuchar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    expect(screen.getByText('¿Eliminar esta generación y su audio?')).toBeDefined()
    expect(remove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('button', { name: 'Confirmar: eliminar' })).toBeNull()
    expect(remove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar: eliminar' }))
    expect(remove).toHaveBeenCalledExactlyOnceWith('job-1')
    expect(onDeleted).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Confirmar: eliminar' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveProperty('disabled', true)
    expect(screen.getByText('Eliminando generación…')).toBeDefined()
    await act(async () => { pending.resolve(); await pending.promise })
    expect(onDeleted).toHaveBeenCalledExactlyOnceWith('job-1')
    expect(screen.queryByRole('group', { name: 'Audio player' })).toBeNull()
    expect(await screen.findByText('Aún no hay generaciones guardadas.')).toBeDefined()
  })

  it('keeps the row and callback untouched after a delete failure and allows retry', async () => {
    const onDeleted = vi.fn()
    remove.mockRejectedValueOnce(new SynthesisApiError('synthesis_job_active'))
    render(<SpeakHistory onDeleted={onDeleted} />)
    await screen.findByText('Hola, mundo.')
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar: eliminar' }))
    expect(await screen.findByText('La generación sigue en curso: cancélala antes de borrarla.')).toBeDefined()
    expect(screen.getByText('Hola, mundo.')).toBeDefined()
    expect(onDeleted).not.toHaveBeenCalled()
    list.mockResolvedValue([])
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar: eliminar' }))
    await waitFor(() => { expect(onDeleted).toHaveBeenCalledExactlyOnceWith('job-1') })
    expect(remove).toHaveBeenCalledTimes(2)
  })

  it('shows a safe generic delete error instead of arbitrary exception text', async () => {
    remove.mockRejectedValueOnce(new Error('private exception value'))
    render(<SpeakHistory />)
    await screen.findByText('Hola, mundo.')
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar: eliminar' }))
    await screen.findByText('No se pudo eliminar la generación. Inténtalo de nuevo.')
    expect(document.body.textContent).not.toContain('private exception value')
    expect(screen.getByText('Hola, mundo.')).toBeDefined()
  })

  it('shows a list failure with retry and does not expose arbitrary exception text', async () => {
    list.mockRejectedValueOnce(new Error('private exception value'))
    render(<SpeakHistory />)
    await screen.findByText('No se pudo cargar el historial.')
    expect(document.body.textContent).not.toContain('private exception value')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Hola, mundo.')).toBeDefined()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('refreshes on refreshKey and ignores an older request that resolves later', async () => {
    const first = deferred<SynthesisView[]>()
    const second = deferred<SynthesisView[]>()
    list.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { rerender, unmount } = render(<SpeakHistory refreshKey="running" />)
    const oldSignal = list.mock.calls[0]?.[1]
    rerender(<SpeakHistory refreshKey="completed" />)
    expect(oldSignal?.aborted).toBe(true)
    await act(async () => { second.resolve([job()]); await second.promise })
    expect(screen.getByText('Hola, mundo.')).toBeDefined()
    await act(async () => { first.resolve([]); await first.promise })
    expect(screen.getByText('Hola, mundo.')).toBeDefined()
    rerender(<SpeakHistory refreshKey="completed" models={[MODEL]} />)
    expect(screen.getByText('Dora')).toBeDefined()
    expect(list).toHaveBeenCalledTimes(2)
    const signal = list.mock.calls[1]?.[1]
    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
