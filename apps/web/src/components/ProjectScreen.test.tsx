import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import { ProjectScreen } from './ProjectScreen'

class FakeXMLHttpRequest {
  static instances: FakeXMLHttpRequest[] = []

  url = ''
  headers: Record<string, string> = {}
  body: unknown = undefined
  status = 0
  responseText = ''
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  open(_method: string, url: string) {
    this.url = url
  }

  setRequestHeader(key: string, value: string) {
    this.headers[key] = value
  }

  send(body: unknown) {
    this.body = body
    FakeXMLHttpRequest.instances.push(this)
  }

  abort() {
    this.onabort?.()
  }

  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total } as ProgressEvent)
  }

  respond(status: number, body: unknown) {
    this.status = status
    this.responseText = JSON.stringify(body)
    this.onload?.()
  }
}

const media = (name: string, n: number) => ({
  media_asset_id: 'm-' + n,
  project_id: 'p1',
  filename: name,
  media_type: 'audio',
  duration_ms: 60_000,
  sha256: 'a'.repeat(64),
})

const recording = (name: string, n: number, latest_job: unknown = null) => ({
  media_asset_id: 'm-' + n,
  filename: name,
  media_type: 'audio',
  duration_ms: 125_000,
  created_at: '2026-11-01T10:00:00Z',
  latest_job,
})

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

/** Las respuestas de `recordings` salen por orden; la cola, las opciones y las tareas, vacías. */
function stubRecordings(responses: Response[], queue: () => Response = () => json({ queue: null })) {
  const fetchMock = vi.fn((url: string) => {
    if (url.endsWith('/transcription-queue')) {
      return Promise.resolve(queue())
    }
    if (url === '/api/transcription-options') {
      return Promise.resolve(json({ options: [] }))
    }
    if (url.endsWith('/recordings')) {
      return Promise.resolve(responses.shift() ?? json({ recordings: [] }))
    }
    return Promise.resolve(json({ tasks: [] }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const recordingCalls = (fetchMock: ReturnType<typeof stubRecordings>) =>
  fetchMock.mock.calls.filter(([url]) => url.endsWith('/recordings')).length

const file = (name: string) => new File(['x'], name, { type: 'audio/wav' })

async function drop(files: File[]) {
  const zone = await screen.findByRole('button', { name: /suelta aquí tus audios/i })
  fireEvent.drop(zone, { dataTransfer: { files } })
}

/** Espera a que haya exactamente `n` subidas iniciadas y devuelve la última. */
async function uploadNumber(n: number): Promise<FakeXMLHttpRequest> {
  await vi.waitFor(() => {
    expect(FakeXMLHttpRequest.instances).toHaveLength(n)
  })
  return FakeXMLHttpRequest.instances[n - 1] as FakeXMLHttpRequest
}

async function respond(request: FakeXMLHttpRequest, status: number, body: unknown) {
  await act(async () => {
    request.respond(status, body)
    await Promise.resolve()
  })
}

beforeEach(() => {
  FakeXMLHttpRequest.instances = []
  vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  setLang('es')
})

describe('ProjectScreen', () => {
  it('sube tres archivos soltados al mismo proyecto, uno tras otro', async () => {
    const fetchMock = stubRecordings([
      json({ recordings: [] }),
      json({ recordings: [recording('a.wav', 1), recording('b.wav', 2), recording('c.wav', 3)] }),
    ])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await screen.findByText(/todavía no hay grabaciones/i)

    const a = file('a.wav')
    await drop([a, file('b.wav'), file('c.wav')])

    const first = await uploadNumber(1)
    expect(first.url).toBe('/api/projects/p1/media')
    expect(first.headers['X-Voz-Filename']).toBe('a.wav')
    expect(first.body).toBe(a)
    // Una barra por archivo; los demás esperan su turno y no han empezado.
    expect(screen.getAllByRole('progressbar')).toHaveLength(3)
    expect(screen.getAllByText('En espera')).toHaveLength(2)
    act(() => {
      first.progress(50, 100)
    })
    expect(screen.getByText('Subiendo 50 %')).toBeDefined()
    expect(FakeXMLHttpRequest.instances).toHaveLength(1)

    await respond(first, 201, media('a.wav', 1))
    const second = await uploadNumber(2)
    expect(second.headers['X-Voz-Filename']).toBe('b.wav')
    await respond(second, 201, media('b.wav', 2))
    const third = await uploadNumber(3)
    expect(third.headers['X-Voz-Filename']).toBe('c.wav')
    await respond(third, 201, media('c.wav', 3))

    // Al terminar la cola la tabla se recarga con las tres grabaciones.
    const table = await screen.findByRole('table', { name: 'Grabaciones del proyecto' })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    expect(recordingCalls(fetchMock)).toBe(2)
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('si falla el segundo archivo muestra su error y sube el tercero igual', async () => {
    stubRecordings([json({ recordings: [] }), json({ recordings: [recording('a.wav', 1), recording('c.wav', 3)] })])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await screen.findByText(/todavía no hay grabaciones/i)

    await drop([file('a.wav'), file('malo.txt'), file('c.wav')])

    await respond(await uploadNumber(1), 201, media('a.wav', 1))
    await respond(await uploadNumber(2), 415, {
      detail: { code: 'media_unsupported', message: 'raw ffmpeg stderr' },
    })
    expect(await screen.findByText('No se pudo importar malo.txt')).toBeDefined()
    expect(screen.getByText('FFmpeg no reconoce este archivo como audio o video.')).toBeDefined()
    expect(screen.queryByText(/raw ffmpeg stderr/)).toBeNull()

    const third = await uploadNumber(3)
    expect(third.headers['X-Voz-Filename']).toBe('c.wav')
    await respond(third, 201, media('c.wav', 3))

    expect(await screen.findByRole('table', { name: 'Grabaciones del proyecto' })).toBeDefined()
    // El error por archivo se queda a la vista aunque la cola termine.
    expect(screen.getByText('No se pudo importar malo.txt')).toBeDefined()
  })

  it('un soltado vacío no borra los avisos de error anteriores', async () => {
    stubRecordings([json({ recordings: [] }), json({ recordings: [] })])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await screen.findByText(/todavía no hay grabaciones/i)

    await drop([file('malo.txt')])
    await respond(await uploadNumber(1), 415, { detail: { code: 'media_unsupported', message: 'x' } })
    expect(await screen.findByText('No se pudo importar malo.txt')).toBeDefined()

    await drop([])
    expect(screen.getByText('No se pudo importar malo.txt')).toBeDefined()
  })

  it('al desmontar aborta la subida en curso, no sigue con la cola ni recarga', async () => {
    const fetchMock = stubRecordings([json({ recordings: [] })])
    const view = render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await screen.findByText(/todavía no hay grabaciones/i)

    await drop([file('a.wav'), file('b.wav')])
    const first = await uploadNumber(1)
    const abort = vi.spyOn(first, 'abort')

    view.unmount()
    await act(async () => {
      await Promise.resolve()
    })

    expect(abort).toHaveBeenCalledTimes(1)
    expect(FakeXMLHttpRequest.instances).toHaveLength(1)
    expect(recordingCalls(fetchMock)).toBe(1)
  })

  it('lista nombre, duración y estado del último trabajo, y abre el trabajo', async () => {
    stubRecordings([
      json({
        recordings: [
          recording('clase.wav', 1, {
            id: 'job-1',
            state: 'COMPLETED',
            transcript_id: 't1',
            model_id: 'turbo',
            created_at: '2026-11-01T11:00:00Z',
          }),
          { ...recording('sin.wav', 2), duration_ms: null },
        ],
      }),
    ])
    const onOpenJob = vi.fn()
    render(<ProjectScreen projectId="p1" onOpenJob={onOpenJob} />)

    const table = await screen.findByRole('table', { name: 'Grabaciones del proyecto' })
    expect(within(table).getByText('2:05')).toBeDefined()
    expect(within(table).getByText('Transcripción completada')).toBeDefined()
    expect(within(table).getByText('Sin transcribir')).toBeDefined()
    expect(within(table).getByText('—')).toBeDefined()
    expect(screen.getByText('2 grabaciones')).toBeDefined()

    // Sin trabajo el nombre es texto; con trabajo, un enlace a #/t/<job>.
    expect(within(table).queryByRole('link', { name: 'sin.wav' })).toBeNull()
    const link = within(table).getByRole('link', { name: 'clase.wav' })
    expect(link.getAttribute('href')).toBe('#/t/job-1')
    fireEvent.click(link)
    expect(onOpenJob).toHaveBeenCalledWith('job-1')
  })

  it('traduce el 404 del proyecto y deja reintentar', async () => {
    const fetchMock = stubRecordings([
      json({ detail: { code: 'project_not_found', message: 'x' } }, 404),
      json({ recordings: [recording('a.wav', 1)] }),
    ])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)

    expect(await screen.findByText('No se pudieron consultar las grabaciones')).toBeDefined()
    expect(screen.getByText('El proyecto ya no existe.')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }))
    expect(await screen.findByRole('table', { name: 'Grabaciones del proyecto' })).toBeDefined()
    expect(recordingCalls(fetchMock)).toBe(2)
  })

  it('no ofrece la cola en un proyecto sin grabaciones', async () => {
    const fetchMock = stubRecordings([json({ recordings: [] })])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await screen.findByText(/todavía no hay grabaciones/i)

    expect(screen.queryByText('Transcribir el proyecto')).toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/transcription-queue'))).toBe(false)
  })

  it('con grabaciones sigue la cola y recarga la tabla cuando termina', async () => {
    vi.useFakeTimers()
    const queue = (state: 'running' | 'finished') =>
      json({
        queue: {
          id: 'q1',
          project_id: 'p1',
          created_at: 'a',
          state,
          progress: state === 'running' ? 0 : 1,
          counts: { total: 1, pending: 0, running: 0, done: state === 'running' ? 0 : 1, error: 0, cancelled: 0, skipped: 0 },
          items: [],
          skipped: [],
        },
      })
    const answers = [queue('running'), queue('finished')]
    const fetchMock = stubRecordings(
      [json({ recordings: [recording('a.wav', 1)] }), json({ recordings: [recording('a.wav', 1)] })],
      () => answers.shift() ?? queue('finished'),
    )
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('Cola de transcripción')).toBeDefined()
    expect(recordingCalls(fetchMock)).toBe(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText('1 de 1 terminadas')).toBeDefined()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(recordingCalls(fetchMock)).toBe(2)
  })

  it('en inglés habla inglés', async () => {
    setLang('en')
    stubRecordings([json({ recordings: [] })])
    render(<ProjectScreen projectId="p1" onOpenJob={vi.fn()} />)

    expect(await screen.findByText(/no recordings in this project/i)).toBeDefined()
    expect(screen.getByRole('button', { name: /drop your audio or video files here/i })).toBeDefined()
  })
})
