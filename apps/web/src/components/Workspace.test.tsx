/** Espacio de trabajo: revisión → audio y lista, hablantes (filtro, muestra) y recálculo. */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ImportResult } from './NewProjectCard'
import { Workspace } from './Workspace'

const SEED: ImportResult = {
  project: { id: 'p1', name: 'Clase', created_at: '2026-10-01T10:00:00Z' },
  media: {
    media_asset_id: 'a1',
    project_id: 'p1',
    filename: 'clase.wav',
    media_type: 'audio',
    duration_ms: 120_000,
    sha256: 'ab'.repeat(32),
  },
}

function job(id: string, state: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    project_id: 'p1',
    media_asset_id: 'a1',
    state,
    progress: 1,
    error_code: null,
    transcript_id: 't1',
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:05Z',
    selection: { option_id: 'o', provider_id: 'fake', model_id: 'fixture' },
    ...extra,
  }
}

const seg = (
  id: string,
  start_ms: number,
  end_ms: number,
  text: string,
  speaker_id: string,
  flags: string[] = [],
) => ({
  id,
  start_ms,
  end_ms,
  text,
  speaker_id,
  edited: false,
  revision: 0,
  quality: { flags, avg_logprob: null },
  words: [],
})

const SEGMENTS = [
  seg('s1', 0, 5000, 'Buenos días a todos.', 'sp1'),
  seg('s2', 5000, 7000, 'Gracias, profe.', 'sp2'),
  seg('s3', 60_000, 70_000, 'Hoy vemos el servicio.', 'sp1', ['low_confidence']),
]
const SPEAKERS = [
  { id: 'sp1', name: 'Ana', color: '#336699', segment_count: 2 },
  { id: 'sp2', name: 'Beto', color: '#993366', segment_count: 1 },
]

class FakeEventSource {
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []
  readyState = 1
  private listeners = new Map<string, ((event: Event) => void)[]>()
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this)
  }
  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener])
  }
  close() {
    this.readyState = 2
  }
  emit(name: string, data: unknown) {
    const event = new MessageEvent(name, { data: JSON.stringify(data) })
    act(() => {
      this.listeners.get(name)?.forEach((listener) => {
        listener(event)
      })
    })
  }
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

let calls: { method: string; path: string; body: unknown }[]
let rediarizeStatus: number
let speakersNow: typeof SPEAKERS
let play: ReturnType<typeof vi.spyOn>
let pause: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  calls = []
  rediarizeStatus = 202
  speakersNow = SPEAKERS
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve())
  pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL((input instanceof Request ? input.url : input.toString()), 'http://localhost')
      const method = init?.method ?? 'GET'
      const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      calls.push({ method, path: url.pathname, body })
      const route = method + ' ' + url.pathname
      switch (route) {
        case 'GET /api/jobs/job-1':
          return Promise.resolve(json(job('job-1', 'COMPLETED')))
        case 'GET /api/transcripts/t1/segments':
          return Promise.resolve(json({ segments: SEGMENTS }))
        case 'GET /api/transcripts/t1/speakers':
          return Promise.resolve(json({ speakers: speakersNow }))
        case 'GET /api/media/a1/peaks':
          return Promise.resolve(json({ media_asset_id: 'a1', duration_ms: 120_000, buckets: 1, peaks: [[-1, 1]] }))
        case 'POST /api/transcripts/t1/rediarize':
          return Promise.resolve(
            rediarizeStatus === 202
              ? json(job('job-2', 'DIARIZING', { progress: 0.1 }), 202)
              : json({ detail: { code: 'diarization_models_missing', message: 'x' } }, rediarizeStatus),
          )
        default:
          return Promise.reject(new Error('petición sin simular: ' + route))
      }
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderWorkspace(onOpenModels = vi.fn()) {
  render(
    <Workspace
      jobId="job-1"
      seed={SEED}
      library={{ phase: 'ready', items: [] }}
      onAdjust={vi.fn()}
      onGoHome={vi.fn()}
      onOpenModels={onOpenModels}
    />,
  )
  const stream = FakeEventSource.instances[0] as FakeEventSource
  stream.emit('job', job('job-1', 'COMPLETED'))
  return stream
}

describe('Workspace', () => {
  it('el panel de hablantes se recarga al terminar de identificarlos', async () => {
    speakersNow = []
    render(
      <Workspace
        jobId="job-1"
        seed={SEED}
        library={{ phase: 'ready', items: [] }}
        onAdjust={vi.fn()}
        onGoHome={vi.fn()}
        onOpenModels={vi.fn()}
      />,
    )
    const stream = FakeEventSource.instances[0] as FakeEventSource
    stream.emit('job', job('job-1', 'DIARIZING', { progress: 0.8 }))
    expect((await screen.findAllByText(/Identificando hablantes/)).length).toBeGreaterThan(0)

    speakersNow = SPEAKERS
    stream.emit('job', job('job-1', 'COMPLETED'))
    expect(await screen.findByLabelText('Nombre de Ana')).toBeDefined()
  })

  it('«N segmentos por revisar» salta al segmento: audio, reproducción y resaltado', async () => {
    renderWorkspace()
    const list = await screen.findByRole('region', { name: 'Lista de segmentos' })
    await within(list).findByText('Hoy vemos el servicio.')
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')
    expect(play).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '1 segmento por revisar' }))

    expect(audio.currentTime).toBe(60)
    expect(play).toHaveBeenCalledTimes(1)
    await waitFor(() => {
      expect(document.querySelector('.segment-row[class*="is-focused"]')?.textContent).toContain(
        'Hoy vemos el servicio.',
      )
    })
  })

  it('filtra por hablante, escucha una muestra con fin y quita el filtro', async () => {
    renderWorkspace()
    const list = await screen.findByRole('region', { name: 'Lista de segmentos' })
    await within(list).findByText('Gracias, profe.')

    fireEvent.click(await screen.findByRole('button', { name: 'Ver solo a Ana en la transcripción' }))
    expect(within(list).queryByText('Gracias, profe.')).toBeNull()
    expect(within(list).getByText('Hoy vemos el servicio.')).toBeDefined()
    expect(screen.getByText('Solo Ana')).toBeDefined()

    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')
    fireEvent.click(screen.getByRole('button', { name: 'Escuchar una muestra de Ana' }))
    // El segmento más largo de Ana (60–70 s) recortado a 12 s no pasa de 70 s.
    expect(audio.currentTime).toBe(60)
    audio.currentTime = 70.2
    fireEvent(audio, new Event('timeupdate'))
    expect(pause).toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Mostrar a todos' }))
    expect(within(list).getByText('Gracias, profe.')).toBeDefined()
  })

  it('recalcula los hablantes con N exacto, sigue el progreso y recarga al terminar', async () => {
    renderWorkspace()
    await screen.findByRole('region', { name: 'Lista de segmentos' })
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular hablantes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Recalcular hablantes' })
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Exacto' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Recalcular' }))

    await waitFor(() => {
      expect(calls.find((call) => call.path === '/api/transcripts/t1/rediarize')?.body).toEqual({
        speakers: { exact: 2 },
      })
    })
    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(2)
    })
    const stream = FakeEventSource.instances[1] as FakeEventSource
    expect(stream.url).toBe('/api/jobs/job-2/events')
    stream.emit('job', job('job-2', 'DIARIZING', { stage_progress: 0.4 }))
    expect(await screen.findByText('Recalculando hablantes: 40 %')).toBeDefined()

    const before = calls.filter((call) => call.path === '/api/transcripts/t1/speakers').length
    stream.emit('job', job('job-2', 'COMPLETED'))
    await waitFor(() => {
      expect(calls.filter((call) => call.path === '/api/transcripts/t1/speakers').length).toBeGreaterThan(before)
    })
    expect(screen.queryByText(/Recalculando hablantes/)).toBeNull()
  })

  it('si falta el modelo de hablantes lo dice y lleva a Modelos', async () => {
    rediarizeStatus = 409
    const onOpenModels = vi.fn()
    renderWorkspace(onOpenModels)
    await screen.findByRole('region', { name: 'Lista de segmentos' })
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular hablantes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Recalcular hablantes' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Recalcular' }))

    expect(await within(dialog).findByText(/Falta el modelo de hablantes/)).toBeDefined()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ir a Modelos' }))
    expect(onOpenModels).toHaveBeenCalledTimes(1)
  })
})
