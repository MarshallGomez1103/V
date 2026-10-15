import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createSynthesis, deleteSynthesis, getSynthesisOptions, listSynthesis, type SynthesisView } from '../api/synthesis'
import { useSynthesisEvents } from '../hooks/useSynthesisEvents'
import { setLang } from '../i18n/i18n'
import { SpeakWorkspace } from './SpeakWorkspace'

vi.mock('../api/synthesis', async (original) => ({
  ...await original<typeof import('../api/synthesis')>(),
  getSynthesisOptions: vi.fn(),
  listSynthesis: vi.fn(),
  createSynthesis: vi.fn(),
  deleteSynthesis: vi.fn(),
}))
vi.mock('../hooks/useSynthesisEvents', () => ({ useSynthesisEvents: vi.fn() }))

const MODEL = {
  provider_id: 'local', model_id: 'voice', display_name: 'Voice', runtime_ready: true,
  languages: ['es'], voices: [{ id: '0', name: 'Ald', languages: ['es'] }],
}
const OPTIONS = {
  providers: [{ provider_id: 'local', display_name: 'Local', locality: 'local' }],
  models: [MODEL], max_chars: 100, speed: { min: 0.5, max: 2 },
}
const DONE: SynthesisView = {
  id: 'history-job', state: 'COMPLETED', progress: 1, chunks_done: 1, chunks_total: 1,
  error_code: null, created_at: '2026-10-15T12:00:00Z', updated_at: '2026-10-15T12:00:01Z',
  started_at: '2026-10-15T12:00:00Z', provider_id: 'local', model_id: 'voice', voice_id: '0',
  language: null, speed: 1, text_length: 18, text_preview: 'Generación anterior',
  audio: { duration_ms: 1500, sample_rate: 24000, size_bytes: 72044, url: '/api/synthesis/history-job/audio' },
}

beforeEach(() => {
  setLang('es')
  window.localStorage.clear()
  vi.mocked(getSynthesisOptions).mockResolvedValue(OPTIONS)
  vi.mocked(listSynthesis).mockResolvedValue([])
  vi.mocked(useSynthesisEvents).mockReturnValue({ job: null, ended: false, error: null, retry: vi.fn() })
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('SpeakWorkspace: history integration', () => {
  it('conserva el historial cuando ya no hay modelos instalados', async () => {
    vi.mocked(getSynthesisOptions).mockResolvedValue({ ...OPTIONS, models: [] })
    vi.mocked(listSynthesis).mockResolvedValue([DONE])
    render(<SpeakWorkspace onOpenModels={vi.fn()} />)

    await screen.findByRole('heading', { name: 'No hay voces instaladas' })
    expect(await screen.findByText(DONE.text_preview)).toBeDefined()
    expect(screen.getByRole('link', { name: 'Descargar WAV' }).getAttribute('href'))
      .toBe('/api/synthesis/history-job/audio?download=true')
  })

  it('borrar desde el historial también retira el resultado seleccionado', async () => {
    vi.mocked(createSynthesis).mockResolvedValue({ ...DONE, reused: true })
    vi.mocked(listSynthesis).mockResolvedValueOnce([]).mockResolvedValue([DONE])
    vi.mocked(deleteSynthesis).mockResolvedValue(undefined)
    const { container } = render(<SpeakWorkspace onOpenModels={vi.fn()} />)
    const area = await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    fireEvent.change(area, { target: { value: 'Hola' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generar audio' }))
    await screen.findByText(DONE.text_preview)
    expect(container.querySelector('.voz-speak-result')).not.toBeNull()
    const history = screen.getByRole('heading', { name: 'Historial de voz' }).closest('section')!
    fireEvent.click(within(history).getByRole('button', { name: 'Eliminar' }))
    vi.mocked(listSynthesis).mockResolvedValue([])
    fireEvent.click(within(history).getByRole('button', { name: 'Confirmar: eliminar' }))
    await waitFor(() => expect(container.querySelector('.voz-speak-result')).toBeNull())
    expect(deleteSynthesis).toHaveBeenCalledWith(DONE.id)
    expect(screen.queryByText(DONE.text_preview)).toBeNull()
  })

  it('vuelve a consultar el historial cuando termina una generación', async () => {
    vi.mocked(createSynthesis).mockResolvedValue({ ...DONE, state: 'QUEUED', audio: null, reused: false })
    const { rerender } = render(<SpeakWorkspace onOpenModels={vi.fn()} />)
    const area = await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    await waitFor(() => expect(listSynthesis).toHaveBeenCalled())
    fireEvent.change(area, { target: { value: 'Hola' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generar audio' }))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await waitFor(() => expect(listSynthesis).toHaveBeenCalledTimes(2))

    vi.mocked(listSynthesis).mockResolvedValue([DONE])
    vi.mocked(useSynthesisEvents).mockReturnValue({ job: DONE, ended: true, error: null, retry: vi.fn() })
    rerender(<SpeakWorkspace onOpenModels={vi.fn()} />)

    expect(await screen.findByText(DONE.text_preview)).toBeDefined()
    expect(listSynthesis).toHaveBeenCalledTimes(3)
  })
})
