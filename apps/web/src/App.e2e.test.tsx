/**
 * S5.17: recorrido completo del espacio de trabajo con el cliente real y una
 * API simulada (fetch, XMLHttpRequest y EventSource). Los contratos de las
 * respuestas replican docs/api/*.md.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { AUTOSAVE_DEBOUNCE_MS } from './hooks/useSegmentDrafts'

const PROJECT = {
  id: 'p1',
  name: 'Clase de prueba',
  created_at: '2026-09-30T10:00:00Z',
}
const MEDIA = {
  media_asset_id: 'a1',
  project_id: 'p1',
  filename: 'clase.wav',
  media_type: 'audio',
  duration_ms: 90_000,
  sha256: 'ab'.repeat(32),
}
const OPTION = {
  option_id: 'option-v1-abc',
  provider_id: 'fake-asr',
  model_id: 'fixture',
  source: 'example/fake-asr',
  revision: 'e'.repeat(40),
  profile: {
    name: 'fast',
    device_preference: 'gpu_preferred',
    gpu_precisions: ['float16'],
    cpu_precision: 'int8',
  },
  display_name: 'Motor de prueba',
  installation_status: 'registered',
  files_available: true,
  runtime_available: true,
  can_start: true,
  capabilities: ['transcription'],
  execution: { device: 'cpu', precision: 'int8', fallback_reason: null },
  device_name: null,
  recommendation: { recommended: true, reason: 'default_compatible_profile' },
  blocking_reasons: [],
}
const SEGMENTS = [
  { id: 's1', start_ms: 0, end_ms: 1_500, text: 'Bienvenidos a la clase.' },
  { id: 's2', start_ms: 65_500, end_ms: 68_000, text: 'Hoy vemos el servicio.' },
  { id: 's3', start_ms: 68_000, end_ms: 70_000, text: 'Gracias por venir.' },
].map((segment) => ({
  ...segment,
  edited: false,
  revision: 0,
  speaker_id: null,
  quality: { flags: [], avg_logprob: null },
  words: [],
}))

function jobView(state: string, progress: number, transcriptId: string | null) {
  return {
    id: 'job-1',
    project_id: 'p1',
    media_asset_id: 'a1',
    state,
    progress,
    error_code: null,
    transcript_id: transcriptId,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:0' + String(Math.min(9, Math.round(progress * 9))) + 'Z',
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface Call {
  method: string
  path: string
  body: unknown
}

/** Servidor simulado: registra cada petición y responde según el contrato. */
function installApi() {
  const calls: Call[] = []
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : input.toString(), 'http://localhost')
    const method = init?.method ?? 'GET'
    const body: unknown =
      typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    calls.push({ method, path: url.pathname + url.search, body })
    const route = method + ' ' + url.pathname
    switch (true) {
      case route === 'GET /api/health':
        return Promise.resolve(json({ status: 'ok', service: 'voz' }))
      case route === 'POST /api/projects':
        return Promise.resolve(json(PROJECT, 201))
      case route === 'GET /api/transcription-options':
        return Promise.resolve(json({ options: [OPTION] }))
      case route === 'POST /api/jobs':
        return Promise.resolve(json(jobView('QUEUED', 0, null), 201))
      case route === 'GET /api/media/a1/peaks':
        return Promise.resolve(
          json({
            media_asset_id: 'a1',
            duration_ms: 90_000,
            buckets: 4,
            peaks: [
              [-0.1, 0.2],
              [-0.5, 0.6],
              [-0.3, 0.4],
              [-0.2, 0.1],
            ],
          }),
        )
      case route === 'GET /api/transcripts/t1/segments':
        return Promise.resolve(json({ segments: SEGMENTS }))
      case route.startsWith('PUT /api/segments/'): {
        const id = url.pathname.split('/').pop()
        const original = SEGMENTS.find((segment) => segment.id === id)
        const edit = body as { text: string; revision: number }
        return Promise.resolve(
          json({
            ...original,
            text: edit.text.trim(),
            edited: true,
            revision: edit.revision + 1,
          }),
        )
      }
      default:
        return Promise.reject(new Error('petición sin simular: ' + route))
    }
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

interface Upload {
  method: string
  url: string
  headers: Record<string, string>
  body: unknown
}

/** XMLHttpRequest mínimo: responde 201 con el resumen del medio importado. */
function installUploads() {
  const uploads: Upload[] = []
  class FakeXhr {
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
      onprogress: null,
    }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    onabort: (() => void) | null = null
    status = 0
    responseText = ''
    private method = ''
    private url = ''
    private headers: Record<string, string> = {}

    open(method: string, url: string) {
      this.method = method
      this.url = url
    }
    setRequestHeader(name: string, value: string) {
      this.headers[name] = value
    }
    send(body: unknown) {
      uploads.push({
        method: this.method,
        url: this.url,
        headers: this.headers,
        body,
      })
      queueMicrotask(() => {
        this.status = 201
        this.responseText = JSON.stringify(MEDIA)
        this.onload?.()
      })
    }
    abort() {
      this.onabort?.()
    }
  }
  vi.stubGlobal('XMLHttpRequest', FakeXhr)
  return uploads
}

/** EventSource simulado; el test emite los eventos SSE a mano. */
class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []
  readyState = FakeEventSource.OPEN
  private listeners = new Map<string, ((event: Event) => void)[]>()

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this)
  }
  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener])
  }
  close() {
    this.readyState = FakeEventSource.CLOSED
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

let calls: Call[]
let uploads: Upload[]
let play: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  calls = installApi()
  uploads = installUploads()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  // jsdom no implementa canvas ni reproducción de medios.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  play = vi
    .spyOn(HTMLMediaElement.prototype, 'play')
    .mockImplementation(() => Promise.resolve())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function source(): FakeEventSource {
  const instance = FakeEventSource.instances.at(-1)
  if (!instance) {
    throw new Error('la app no abrió el stream de eventos')
  }
  return instance
}

async function importAndTranscribe() {
  render(<App />)

  const file = new File(['RIFF-fake-wav'], 'clase.wav', { type: 'audio/wav' })
  fireEvent.change(screen.getByLabelText('Archivo de audio o video'), {
    target: { files: [file] },
  })
  fireEvent.change(screen.getByLabelText('Nombre del proyecto'), {
    target: { value: PROJECT.name },
  })
  fireEvent.click(
    screen.getByRole('button', { name: 'Crear proyecto e importar' }),
  )
  expect(await screen.findByText('Importación completa')).toBeDefined()

  // El motor viable único queda preseleccionado.
  const radio = await screen.findByRole<HTMLInputElement>('radio')
  await waitFor(() => {
    expect(radio.checked).toBe(true)
  })
  fireEvent.click(screen.getByRole('button', { name: 'Transcribir' }))
  await waitFor(() => {
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  const stream = source()
  stream.emit('job', jobView('TRANSCRIBING', 0.5, null))
  stream.emit('job', jobView('COMPLETED', 1, 't1'))
  stream.emit('end', {})
  return stream
}

describe('App E2E con API simulada', () => {
  it('crea el proyecto, sube el archivo y transcribe hasta COMPLETED', async () => {
    const stream = await importAndTranscribe()

    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/projects',
      body: { name: PROJECT.name },
    })
    expect(uploads).toHaveLength(1)
    expect(uploads[0]).toMatchObject({
      method: 'POST',
      url: '/api/projects/p1/media',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Voz-Filename': 'clase.wav',
      },
    })
    expect(uploads[0]?.body).toBeInstanceOf(File)

    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/jobs',
      body: {
        project_id: 'p1',
        media_asset_id: 'a1',
        option_id: OPTION.option_id,
        language: null,
        diarization: { enabled: false, speakers: {} },
      },
    })
    expect(stream.url).toBe('/api/jobs/job-1/events')
    expect(stream.readyState).toBe(FakeEventSource.CLOSED)

    expect(await screen.findByText('Transcripción completada')).toBeDefined()
    const list = await screen.findByRole('region', {
      name: 'Lista de segmentos',
    })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    // Modo Leer por defecto: texto por palabras; Editar muestra el textarea.
    expect(within(rows[1] as HTMLElement).getByText(/Hoy vemos el servicio/)).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    expect(
      screen.getByLabelText<HTMLTextAreaElement>('Texto del segmento s2').value,
    ).toBe('Hoy vemos el servicio.')
    expect(calls).toContainEqual({
      method: 'GET',
      path: '/api/transcripts/t1/segments',
      body: undefined,
    })
  })

  it('un clic en el tiempo hace seek en el reproductor del original', async () => {
    await importAndTranscribe()
    await screen.findByRole('region', { name: 'Lista de segmentos' })

    const audio = screen.getByLabelText<HTMLAudioElement>(
      'Reproductor del original',
    )
    expect(audio.getAttribute('src')).toBe('/api/media/a1/original')
    expect(play).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByRole('button', { name: 'Reproducir desde 01:05.5' }),
    )

    expect(audio.currentTime).toBe(65.5)
    expect(play).toHaveBeenCalledTimes(1)
  })

  it('edita un segmento y el autosave envía PUT con la revisión cargada', async () => {
    await importAndTranscribe()
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    const textarea = await screen.findByLabelText('Texto del segmento s3')

    fireEvent.change(textarea, { target: { value: 'Gracias por venir hoy.' } })
    expect(screen.getByText('Cambios sin guardar')).toBeDefined()
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)

    await waitFor(
      () => {
        expect(screen.getByText('Todo guardado')).toBeDefined()
      },
      { timeout: AUTOSAVE_DEBOUNCE_MS + 2_000 },
    )
    const puts = calls.filter((call) => call.method === 'PUT')
    expect(puts).toEqual([
      {
        method: 'PUT',
        path: '/api/segments/s3',
        body: { text: 'Gracias por venir hoy.', revision: 0 },
      },
    ])

    // Un segundo cambio parte de la revisión que devolvió el servidor.
    fireEvent.change(textarea, { target: { value: 'Gracias, hasta luego.' } })
    fireEvent.blur(textarea)
    await waitFor(() => {
      expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2)
    })
    expect(calls.filter((call) => call.method === 'PUT')[1]?.body).toEqual({
      text: 'Gracias, hasta luego.',
      revision: 1,
    })
  })

  it('buscar texto cuenta las coincidencias en la transcripción', async () => {
    await importAndTranscribe()
    await screen.findByRole('region', { name: 'Lista de segmentos' })

    fireEvent.change(screen.getByLabelText('Buscar en la transcripción'), {
      target: { value: 'servicio' },
    })

    expect(await screen.findByText('1 de 1')).toBeDefined()

    fireEvent.change(screen.getByLabelText('Buscar en la transcripción'), {
      target: { value: 'inexistente' },
    })
    expect(await screen.findByText('Sin coincidencias')).toBeDefined()
  })

  // Regresión: el editor resalta la búsqueda en una capa detrás del textarea.
  it('buscar texto resalta la coincidencia con <mark>', async () => {
    await importAndTranscribe()
    const list = await screen.findByRole('region', {
      name: 'Lista de segmentos',
    })

    fireEvent.change(screen.getByLabelText('Buscar en la transcripción'), {
      target: { value: 'servicio' },
    })
    await screen.findByText('1 de 1')

    const marks = list.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0]?.textContent).toBe('servicio')
  })

  it('el enlace de exportación apunta al transcript con el formato elegido', async () => {
    await importAndTranscribe()
    const link = await screen.findByRole('link', { name: 'Descargar' })

    expect(link.getAttribute('href')).toBe(
      '/api/transcripts/t1/export?format=txt',
    )
    expect(link.hasAttribute('download')).toBe(true)

    fireEvent.click(screen.getByLabelText('Incluir tiempos'))
    expect(link.getAttribute('href')).toBe(
      '/api/transcripts/t1/export?format=txt&timestamps=true',
    )

    fireEvent.change(screen.getByLabelText('Formato'), {
      target: { value: 'srt' },
    })
    expect(link.getAttribute('href')).toBe(
      '/api/transcripts/t1/export?format=srt',
    )
  })
})
