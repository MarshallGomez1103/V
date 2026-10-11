/**
 * Flujos de la UI sobre una API simulada: modelo de hablantes que falta, estilo del
 * texto, transcripción visible mientras se calculan los hablantes, reabrir trabajos
 * guardados, cerrar el servidor, caída del servidor y ajustes (tema, acento, idioma,
 * icono de escritorio).
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
import { getLang } from './i18n/i18n'

const PROJECT = { id: 'p1', name: 'Clase', created_at: '2026-10-01T10:00:00Z' }
const MEDIA = {
  media_asset_id: 'a1',
  project_id: 'p1',
  filename: 'clase.wav',
  media_type: 'audio',
  duration_ms: 90_000,
  sha256: 'ab'.repeat(32),
}
const OPTION = {
  option_id: 'option-1',
  provider_id: 'fake-asr',
  model_id: 'fixture',
  source: null,
  revision: null,
  profile: null,
  display_name: 'Motor de prueba',
  installation_status: 'registered',
  files_available: true,
  runtime_available: true,
  can_start: true,
  capabilities: [],
  execution: null,
  device_name: null,
  recommendation: null,
  blocking_reasons: [],
}
const DIAR_MODEL = {
  key: 'diarization:sherpa-default',
  provider_id: 'diarization',
  kind: 'diarization',
  requires: 'diarization',
  runtime_available: true,
  model_id: 'sherpa-default',
  display_name: 'Separación de hablantes',
  source: null,
  revision: null,
  license: 'MIT',
  multilingual: true,
  profile: null,
  size_bytes: 33_488_994,
  installed: false,
  disk_bytes: null,
  external: [],
}
const SPEAKER = { id: 'sp1', name: 'Ana', color: '#336699', segment_count: 2 }
const SEGMENTS = [
  { id: 's1', start_ms: 0, end_ms: 1500, text: 'Bienvenidos a la clase.', speaker_id: 'sp1' },
  { id: 's2', start_ms: 1500, end_ms: 3000, text: 'Hoy vemos el servicio.', speaker_id: 'sp1' },
].map((segment) => ({
  ...segment,
  edited: false,
  revision: 0,
  quality: { flags: [], avg_logprob: null },
  words: [],
}))

function job(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    project_id: 'p1',
    media_asset_id: 'a1',
    state,
    progress: 0.5,
    error_code: null,
    transcript_id: null,
    created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:00:05Z',
    started_at: '2026-10-01T10:00:00Z',
    selection: {
      option_id: 'option-1',
      provider_id: 'fake-asr',
      model_id: 'fixture',
      diarization: { enabled: true, speakers: {} },
    },
    ...extra,
  }
}

const urlOf = (input: RequestInfo | URL): string =>
  input instanceof Request ? input.url : input.toString()

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

interface Call {
  method: string
  path: string
  headers: Record<string, string>
  body: unknown
}

interface Api {
  calls: Call[]
  /** Respuestas variables que el test cambia sobre la marcha. */
  state: {
    diarInstalled: boolean
    taskState: 'running' | 'completed'
    jobs: ReturnType<typeof job>[]
    preview: { start_ms: number; end_ms: number; text: string }[]
    library: 'items' | 'missing'
    shortcut: { supported: boolean; exists: boolean } | null
    shutdown: number
    installing: boolean
  }
}

function installApi(): Api {
  const api: Api = {
    calls: [],
    state: {
      diarInstalled: false,
      taskState: 'running',
      jobs: [],
      library: 'items',
      preview: [],
      shortcut: { supported: true, exists: false },
      shutdown: 202,
      installing: false,
    },
  }
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(input instanceof Request ? input.url : input.toString(), 'http://localhost')
      const method = init?.method ?? 'GET'
      const headers = (init?.headers ?? {}) as Record<string, string>
      const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      api.calls.push({ method, path: url.pathname + url.search, headers, body })
      const route = method + ' ' + url.pathname
      const { state } = api
      switch (true) {
        case route === 'GET /api/health':
          return Promise.resolve(json({ status: 'ok', version: '0.1.0' }))
        case route === 'GET /api/projects':
          return Promise.resolve(json({ projects: [PROJECT] }))
        case route === 'GET /api/library': {
          const latest = state.jobs[0]
          return Promise.resolve(
            state.library === 'missing'
              ? json({}, 404)
              : json({
                  items: latest
                    ? [
                        {
                          project_id: 'p1',
                          name: PROJECT.name,
                          created_at: PROJECT.created_at,
                          media: { media_asset_id: 'a1', filename: 'clase.wav', duration_ms: 90_000 },
                          latest_job: {
                            id: latest.id,
                            state: latest.state,
                            transcript_id: latest.transcript_id,
                            model_id: 'fixture',
                            created_at: latest.created_at,
                          },
                          speaker_count: 1,
                          segment_count: 2,
                        },
                      ]
                    : [],
                }),
          )
        }
        case route === 'POST /api/projects':
          return Promise.resolve(json(PROJECT, 201))
        case route === 'GET /api/jobs':
          return Promise.resolve(json({ jobs: state.jobs }))
        case route === 'POST /api/jobs':
          return Promise.resolve(json(job('QUEUED', { progress: 0 }), 201))
        case route === 'GET /api/jobs/job-1':
          return Promise.resolve(json(state.jobs[0] ?? job('QUEUED')))
        case route === 'GET /api/jobs/job-1/preview':
          return Promise.resolve(json({ segments: state.preview }))
        case route === 'GET /api/transcription-options':
          return Promise.resolve(json({ options: [OPTION] }))
        case route === 'GET /api/models':
          return Promise.resolve(
            json({
              models: [{ ...DIAR_MODEL, installed: state.diarInstalled, disk_bytes: state.diarInstalled ? 32_000_000 : null }],
              disk: { models_bytes: 0, free_bytes: 10_000_000_000 },
            }),
          )
        case route === 'POST /api/models/diarization%3Asherpa-default/install':
        case route === 'POST /api/models/diarization:sherpa-default/install':
          state.installing = true
          return Promise.resolve(json(task(), 202))
        case route === 'GET /api/model-tasks':
          return Promise.resolve(json({ tasks: state.installing ? [task()] : [] }))
        case route === 'GET /api/quality-profiles':
          return Promise.resolve(json({ default: 'default', profiles: [], recommendation: { language: null, profile: null, measured: false, evidence: 'x', synthetic: false, unmeasured_profiles: [] } }))
        case route.startsWith('GET /api/projects/') && route.endsWith('/glossary'):
          return Promise.resolve(json({ terms: [], max_terms: 50, max_term_length: 40, applies_to: [] }))
        case route === 'GET /api/media/a1/peaks':
          return Promise.resolve(json({ media_asset_id: 'a1', duration_ms: 90_000, buckets: 2, peaks: [[-0.1, 0.1], [-0.2, 0.2]] }))
        case route === 'GET /api/transcripts/t1/segments':
          return Promise.resolve(json({ segments: SEGMENTS }))
        case route === 'GET /api/transcripts/t1/speakers':
          return Promise.resolve(json({ speakers: [SPEAKER] }))
        case route === 'GET /api/providers':
          return Promise.resolve(json([]))
        case route === 'GET /api/desktop-shortcut':
          return Promise.resolve(
            state.shortcut === null ? json({}, 404) : json({ ...state.shortcut, path: '/x/VOZ.desktop' }),
          )
        case route === 'POST /api/desktop-shortcut':
          return Promise.resolve(json({ supported: true, exists: true, path: '/x/VOZ.desktop' }))
        case route === 'POST /api/shutdown':
          return Promise.resolve(json({ status: 'stopping' }, state.shutdown))
        default:
          return Promise.reject(new Error('petición sin simular: ' + route))
      }

      function task() {
        return {
          id: 't-1',
          key: 'diarization:sherpa-default',
          model_id: 'sherpa-default',
          method: 'download',
          origin: null,
          state: state.taskState,
          done_bytes: state.taskState === 'completed' ? 33_488_994 : 10_000_000,
          total_bytes: 33_488_994,
          error_code: null,
          created_at: '2026-10-01T10:00:00Z',
          updated_at: '2026-10-01T10:00:01Z',
        }
      }
    }),
  )
  return api
}

function installUploads() {
  class FakeXhr {
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    onabort: (() => void) | null = null
    status = 0
    responseText = ''
    open() {}
    setRequestHeader() {}
    send() {
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
}

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
  dispatch(name: string) {
    this.listeners.get(name)?.forEach((listener) => {
      listener(new Event(name))
    })
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

let api: Api

beforeEach(() => {
  api = installApi()
  installUploads()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve())
  window.location.hash = ''
})

/** Las pruebas que importan un archivo parten de «Nueva transcripción». */
function startFromNew() {
  window.location.hash = '#/nueva'
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.documentElement.className = ''
  document.documentElement.removeAttribute('style')
  document.documentElement.removeAttribute('data-design')
  window.localStorage.clear()
})

async function importFile() {
  const file = new File(['RIFF'], 'clase.wav', { type: 'audio/wav' })
  fireEvent.change(await screen.findByLabelText(/suelta aquí tu audio o video/i), {
    target: { files: [file] },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Crear proyecto e importar' }))
  await screen.findByRole('heading', { name: 'clase.wav' })
  await waitFor(() => {
    expect(screen.getByRole<HTMLInputElement>('radio', { name: /motor de prueba/i }).checked).toBe(true)
  }, { timeout: 5000 }) // ponytail: CI runners are slow; 1 s default flaked there
}

function transcribeButton() {
  return screen.getByRole<HTMLButtonElement>('button', { name: 'Transcribir' })
}

describe('modelo de hablantes que falta', () => {
  beforeEach(startFromNew)

  it('ofrece descargarlo en línea y bloquea Transcribir con una explicación hasta tenerlo', async () => {
    render(<App />)
    await importFile()
    expect(transcribeButton().disabled).toBe(false)

    fireEvent.click(screen.getByRole('switch', { name: 'Detectar quién habla' }))

    const download = await screen.findByRole('button', {
      name: /descargar modelo de hablantes \(33\sMB\)/i,
    })
    expect(transcribeButton().disabled).toBe(true)
    expect(screen.getByText(/transcribir se activa cuando el modelo de hablantes esté instalado/i)).toBeDefined()

    fireEvent.click(download)
    await waitFor(() => {
      expect(api.calls.some((call) => call.method === 'POST' && call.path.includes('/install'))).toBe(true)
    })
    expect(api.calls.find((call) => call.path.includes('/install'))?.body).toEqual({
      method: 'download',
      confirm: true,
    })
    // Mientras baja, sigue bloqueado y muestra el avance.
    expect(await screen.findByText(/descargando: 29 %/i)).toBeDefined()
    expect(transcribeButton().disabled).toBe(true)

    // Termina: el modelo queda instalado y Transcribir se habilita.
    api.state.taskState = 'completed'
    api.state.diarInstalled = true
    await waitFor(
      () => {
        expect(screen.getByText('Modelo de hablantes instalado.')).toBeDefined()
      },
      { timeout: 10_000 },
    )
    expect(transcribeButton().disabled).toBe(false)
  })

  it('con el modelo instalado no estorba y el trabajo pide hablantes', async () => {
    api.state.diarInstalled = true
    render(<App />)
    await importFile()
    fireEvent.click(screen.getByRole('switch', { name: 'Detectar quién habla' }))
    expect(await screen.findByText('Modelo de hablantes instalado.')).toBeDefined()

    fireEvent.click(transcribeButton())
    await waitFor(() => {
      expect(api.calls.some((call) => call.method === 'POST' && call.path === '/api/jobs')).toBe(true)
    })
    const body = api.calls.find((call) => call.method === 'POST' && call.path === '/api/jobs')?.body as {
      diarization: { enabled: boolean }
    }
    expect(body.diarization.enabled).toBe(true)
  })
})

describe('instrucciones de estilo', () => {
  beforeEach(startFromNew)

  it('se envían como `prompt` recortadas y explican que Whisper imita, no obedece', async () => {
    render(<App />)
    await importFile()

    fireEvent.click(screen.getByRole('button', { name: 'Cómo funcionan las instrucciones de estilo' }))
    expect(screen.getByText(/whisper no obedece órdenes como un chat/i)).toBeDefined()

    fireEvent.change(screen.getByPlaceholderText(/ejemplo: hola, buenas tardes/i), {
      target: { value: '  Hola, qué tal. Bien, gracias.  ' },
    })
    fireEvent.click(transcribeButton())

    await waitFor(() => {
      expect(api.calls.some((call) => call.method === 'POST' && call.path === '/api/jobs')).toBe(true)
    })
    expect(api.calls.find((call) => call.path === '/api/jobs' && call.method === 'POST')?.body).toMatchObject({
      prompt: 'Hola, qué tal. Bien, gracias.',
    })
  })

  it('sin texto no envía `prompt`', async () => {
    render(<App />)
    await importFile()
    fireEvent.click(transcribeButton())
    await waitFor(() => {
      expect(api.calls.some((call) => call.method === 'POST' && call.path === '/api/jobs')).toBe(true)
    })
    expect(
      Object.keys(api.calls.find((call) => call.path === '/api/jobs' && call.method === 'POST')?.body as object),
    ).not.toContain('prompt')
  })

  it('un ejemplo con puntuación se inserta con un clic', async () => {
    render(<App />)
    await importFile()
    fireEvent.click(await screen.findByRole('button', { name: 'Usar un ejemplo con puntuación' }))
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText<HTMLTextAreaElement>(/ejemplo: hola, buenas tardes/i).value,
      ).toMatch(/^Hola, buenas tardes\./)
    })
  })
})

describe('texto visible mientras se procesa', () => {
  beforeEach(startFromNew)

  async function start() {
    render(<App />)
    await importFile()
    fireEvent.click(transcribeButton())
    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1)
    })
    return FakeEventSource.instances[0] as FakeEventSource
  }

  it('muestra los segmentos confirmados en vivo durante la transcripción', async () => {
    api.state.preview = [{ start_ms: 0, end_ms: 1500, text: 'Bienvenidos a la clase.' }]
    const stream = await start()
    stream.emit('job', job('TRANSCRIBING', { stage_progress: 0.3, stage_started_at: '2026-10-01T10:00:01Z' }))

    expect(await screen.findByRole('heading', { name: 'Texto en vivo' })).toBeDefined()
    expect(await screen.findByText('Bienvenidos a la clase.')).toBeDefined()
    expect(screen.getByText(/1 segmento hasta 0:01/)).toBeDefined()
  })

  it('el texto completo aparece en cuanto hay transcript aunque los hablantes sigan calculándose', async () => {
    const stream = await start()
    stream.emit('job', job('DIARIZING', { transcript_id: 't1', stage_progress: 0.4 }))

    const list = await screen.findByRole('region', { name: 'Lista de segmentos' })
    expect(within(list).getByText('Bienvenidos a la clase.')).toBeDefined()
    expect(screen.getByText('Identificando hablantes', { selector: '.cds--inline-notification *' })).toBeDefined()
    // Mientras tanto no se puede editar ni exportar.
    expect(screen.queryByRole('tab', { name: 'Editar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Exportar' })).toBeNull()

    stream.emit('job', job('COMPLETED', { progress: 1, transcript_id: 't1' }))
    expect(await screen.findByRole('tab', { name: 'Editar' })).toBeDefined()
    expect(await screen.findByRole('button', { name: 'Exportar' })).toBeDefined()
    await waitFor(() => {
      // Al completar se recargan segmentos y hablantes.
      expect(api.calls.filter((call) => call.path === '/api/transcripts/t1/segments').length).toBeGreaterThanOrEqual(2)
    })
  })

  it('la línea de tiempo de hablantes tiene una fila por hablante y salta al hacer clic', async () => {
    const stream = await start()
    stream.emit('job', job('COMPLETED', { progress: 1, transcript_id: 't1' }))

    const group = await screen.findByRole('group', { name: 'Línea de tiempo de hablantes' })
    const track = await within(group).findByRole('button', { name: /^Ana: 1 bloques/ })
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')
    vi.spyOn(track, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      width: 100,
      top: 0,
      bottom: 10,
      right: 100,
      height: 10,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    fireEvent.click(track, { clientX: 50 })

    expect(audio.currentTime).toBe(45) // 50 % de 90 s
  })
})

describe('abrir lo guardado', () => {
  it('lista las transcripciones guardadas y abre una terminada por su propia URL', async () => {
    api.state.jobs = [job('COMPLETED', { progress: 1, transcript_id: 't1' })]
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()
    const table = await screen.findByRole('table', { name: 'Transcripciones guardadas' })
    expect(within(table).getByText('Clase')).toBeDefined()
    expect(within(table).getByText('1:30')).toBeDefined()
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir Clase' }))
    expect(window.location.hash).toBe('#/t/job-1')

    const stream = FakeEventSource.instances.at(-1)
    stream?.emit('job', job('COMPLETED', { progress: 1, transcript_id: 't1' }))
    const list = await screen.findByRole('region', { name: 'Lista de segmentos' })
    expect(within(list).getByText('Hoy vemos el servicio.')).toBeDefined()
    // El nombre sale de la biblioteca, no del archivo.
    expect(screen.getByRole('heading', { name: 'Reproducción' })).toBeDefined()

    // Atrás vuelve a Inicio.
    act(() => {
      window.location.hash = '#/'
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()
    expect(screen.queryByRole('region', { name: 'Lista de segmentos' })).toBeNull()
  })

  it('recargar #/t/<id> reabre ese trabajo sin pasar por Inicio', async () => {
    api.state.jobs = [job('COMPLETED', { progress: 1, transcript_id: 't1' })]
    window.location.hash = '#/t/job-1'
    render(<App />)

    const list = await screen.findByRole('region', { name: 'Lista de segmentos' }, { timeout: 5000 })
    expect(within(list).getByText('Bienvenidos a la clase.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Exportar' })).toBeDefined()
    expect(screen.getByRole('navigation', { name: 'Ruta de navegación' })).toBeDefined()
  })

  it('una URL de un trabajo que no existe lo dice y ofrece volver al inicio', async () => {
    window.location.hash = '#/t/no-existe'
    render(<App />)
    await waitFor(() => {
      expect(FakeEventSource.instances.length).toBeGreaterThan(0)
    })
    const stream = FakeEventSource.instances.at(-1) as FakeEventSource
    stream.readyState = FakeEventSource.CLOSED
    act(() => {
      stream.dispatch('error')
    })

    expect(await screen.findByText('No se encontró esta transcripción')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Ir al inicio' }))
    expect(window.location.hash).toBe('#/')
  })

  it('un trabajo en curso aparece en la lista con su estado y se abre desde ahí', async () => {
    api.state.jobs = [job('TRANSCRIBING', { stage_progress: 0.2 })]
    render(<App />)

    const table = await screen.findByRole('table', { name: 'Transcripciones guardadas' })
    expect(within(table).getByText('Transcribiendo el audio')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Abrir Clase' }))
    expect(await screen.findByRole('heading', { name: 'Transcribiendo el audio' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDefined()
  })

  it('con un servidor sin /api/library compone la lista con proyectos y trabajos', async () => {
    api.state.library = 'missing'
    api.state.jobs = [job('COMPLETED', { progress: 1, transcript_id: 't1' })]
    render(<App />)

    const table = await screen.findByRole('table', { name: 'Transcripciones guardadas' })
    expect(within(table).getByText('Clase')).toBeDefined()
    expect(api.calls.some((call) => call.path === '/api/projects')).toBe(true)
  })

  it('si no se pueden consultar, lo dice y deja reintentar', async () => {
    const original = globalThis.fetch
    let fail = true
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        fail && /\/api\/(projects|library)/.test(urlOf(input))
          ? Promise.reject(new Error('sin red'))
          : original(input, init),
      ),
    )
    render(<App />)

    expect(await screen.findByText('No se pudieron consultar las transcripciones')).toBeDefined()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText(/todavía no hay transcripciones/i)).toBeDefined()
  })

  it('«Ajustar y repetir» vuelve a #/nueva con la misma grabación ya importada', async () => {
    api.state.jobs = [job('FAILED', { error_code: 'asr_failed' })]
    window.location.hash = '#/t/job-1'
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /ajustar y repetir/i }, { timeout: 5000 }))
    expect(window.location.hash).toBe('#/nueva')
    expect(await screen.findByRole('heading', { name: 'Motor y calidad' })).toBeDefined()
    expect(screen.getByRole('heading', { name: 'clase.wav' })).toBeDefined()
  })

  it('Nueva transcripción lleva a importar', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva transcripción' }))
    expect(window.location.hash).toBe('#/nueva')
    expect(await screen.findByRole('heading', { level: 1, name: 'Transcribir' })).toBeDefined()
  })
})

describe('cerrar el servidor', () => {
  it('pide confirmación, envía la cabecera y muestra la pantalla final', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar servidor' }))

    const dialog = await screen.findByRole('dialog', { name: '¿Cerrar VOZ?' })
    expect(within(dialog).queryByText(/transcripción en curso/i)).toBeNull()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cerrar servidor' }))

    expect(await screen.findByRole('heading', { name: 'VOZ se cerró' })).toBeDefined()
    expect(screen.getByText(/puedes cerrar esta pestaña/i)).toBeDefined()
    expect(screen.getByText(/abre el archivo iniciar de la carpeta/i)).toBeDefined()
    const call = api.calls.find((item) => item.path === '/api/shutdown')
    expect(call?.method).toBe('POST')
    expect(call?.headers['X-VOZ-Action']).toBe('shutdown')
    expect(document.title).toBe('VOZ cerrado')
  })

  it('avisa si hay un trabajo en curso: se reanudará al volver a abrir VOZ', async () => {
    api.state.jobs = [job('TRANSCRIBING')]
    render(<App />)
    await screen.findByRole('table', { name: 'Transcripciones guardadas' })

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar servidor' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cerrar VOZ?' })
    expect(within(dialog).getByText(/se reanudará al volver a abrir voz/i)).toBeDefined()
  })

  it('cancelar no cierra nada', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar servidor' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cerrar VOZ?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))

    expect(api.calls.some((call) => call.path === '/api/shutdown')).toBe(false)
    expect(screen.queryByRole('heading', { name: 'VOZ se cerró' })).toBeNull()
  })

  it('si el servidor rechaza el cierre lo explica y se puede reintentar', async () => {
    api.state.shutdown = 501
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar servidor' }))
    const dialog = await screen.findByRole('dialog', { name: '¿Cerrar VOZ?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cerrar servidor' }))

    expect(await within(dialog).findByText(/no se pudo cerrar desde aquí/i)).toBeDefined()
    expect(screen.queryByRole('heading', { name: 'VOZ se cerró' })).toBeNull()
  })
})

describe('servidor caído', () => {
  it('muestra un aviso global claro y se quita solo al volver', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<App />)
    await screen.findByText('Disponible')

    const original = globalThis.fetch
    let down = true
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        down && urlOf(input).includes('/api/health')
          ? Promise.reject(new TypeError('Failed to fetch'))
          : original(input, init),
      ),
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000 + 2100)
    })
    expect(await screen.findByText('VOZ no responde')).toBeDefined()
    expect(screen.getByText(/si lo cerraste, ábrelo con el archivo iniciar/i)).toBeDefined()

    down = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar ahora' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    await waitFor(() => {
      expect(screen.queryByText('VOZ no responde')).toBeNull()
    })
  })
})

describe('ajustes', () => {
  it('cambia el tema entre los de Carbon y lo recuerda', () => {
    render(<App />)
    const settings = screen.getByRole('button', { name: 'Ajustes' })
    fireEvent.click(settings)

    for (const [label, cls] of [
      ['White', 'cds--white'],
      ['Gray 10', 'cds--g10'],
      ['Gray 90', 'cds--g90'],
      ['Gray 100', 'cds--g100'],
    ] as const) {
      fireEvent.click(screen.getByRole('radio', { name: label }))
      expect(document.documentElement.classList.contains(cls)).toBe(true)
    }
    fireEvent.click(screen.getByRole('radio', { name: 'White' }))
    expect(window.localStorage.getItem('voz.theme')).toBe('white')
    fireEvent.click(screen.getByRole('radio', { name: 'Automático' }))
    expect(window.localStorage.getItem('voz.theme')).toBe('system')
  })

  it('cambia el color de acento y lo recuerda', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))
    expect(document.documentElement.dataset.accent).toBe('blue')

    fireEvent.click(screen.getByRole('radio', { name: 'Verde' }))
    expect(document.documentElement.dataset.accent).toBe('green')
    expect(window.localStorage.getItem('voz.accent')).toBe('green')
    expect(document.querySelector('.voz-app')?.getAttribute('data-accent')).toBe('green')
  })

  it('elige el sistema de diseño Material 3, publica sus colores y lo recuerda', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))
    expect(screen.getByRole('radio', { name: 'Carbon' })).toHaveProperty('checked', true)

    fireEvent.click(screen.getByRole('radio', { name: 'Material 3' }))
    expect(window.localStorage.getItem('voz.design')).toBe('m3')
    await waitFor(() => {
      expect(document.documentElement.dataset.design).toBe('m3')
    })
    expect(document.documentElement.style.getPropertyValue('--md-sys-color-primary')).toMatch(
      /^#[0-9a-f]{6}$/,
    )

    fireEvent.click(screen.getByRole('radio', { name: 'Carbon' }))
    expect(window.localStorage.getItem('voz.design')).toBe('carbon')
    await waitFor(() => {
      expect(document.documentElement.dataset.design).toBe('carbon')
    })
    expect(document.documentElement.style.getPropertyValue('--md-sys-color-primary')).toBe('')
  })

  it('cambiar el acento con Material 3 recalcula los colores', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))
    fireEvent.click(screen.getByRole('radio', { name: 'Material 3' }))
    await waitFor(() => {
      expect(document.documentElement.dataset.design).toBe('m3')
    })
    const blue = document.documentElement.style.getPropertyValue('--md-sys-color-primary')

    fireEvent.click(screen.getByRole('radio', { name: 'Rojo' }))
    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue('--md-sys-color-primary')).not.toBe(
        blue,
      )
    })
  })

  it('un localStorage que falla no rompe la app', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))
    expect(() => {
      fireEvent.click(screen.getByRole('radio', { name: 'Gray 90' }))
    }).not.toThrow()
    expect(document.documentElement.classList.contains('cds--g90')).toBe(true)
  })

  it('cambia el idioma de toda la interfaz a inglés y lo recuerda', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Transcripciones' })).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Idioma' }))
    fireEvent.click(screen.getByRole('button', { name: 'English' }))

    expect(screen.getByRole('heading', { level: 1, name: 'Transcripts' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Close server' })).toBeDefined()
    expect(screen.getAllByRole('link', { name: 'Models' }).length).toBeGreaterThan(0)
    expect(window.localStorage.getItem('voz.lang')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(getLang()).toBe('en')
  })

  it('ofrece crear el icono de escritorio y luego volver a crearlo', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))

    fireEvent.click(await screen.findByRole('button', { name: 'Crear icono en el escritorio' }))
    expect(await screen.findByText('Icono creado en el escritorio.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Volver a crearlo' })).toBeDefined()
    const post = api.calls.find((call) => call.method === 'POST' && call.path === '/api/desktop-shortcut')
    expect(post?.headers['X-VOZ-Action']).toBe('desktop-shortcut')
  })

  it('oculta el icono de escritorio si el sistema no lo admite', async () => {
    api.state.shortcut = { supported: false, exists: false }
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))

    await waitFor(() => {
      expect(api.calls.some((call) => call.path === '/api/desktop-shortcut')).toBe(true)
    })
    expect(screen.queryByText('Icono de escritorio')).toBeNull()
  })

  it('oculta el icono de escritorio si el servidor no ofrece la función', async () => {
    api.state.shortcut = null
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))
    await waitFor(() => {
      expect(api.calls.some((call) => call.path === '/api/desktop-shortcut')).toBe(true)
    })
    expect(screen.queryByText('Icono de escritorio')).toBeNull()
  })
})

describe('texto de la interfaz', () => {
  it('no hay frases de marketing ni etiquetas de privacidad en la cabecera ni en el pie', () => {
    render(<App />)
    expect(screen.queryByText(/local y privado/i)).toBeNull()
    expect(screen.queryByText(/hecho para trabajar en local/i)).toBeNull()
    expect(screen.queryByText(/buzz/i)).toBeNull()
  })
})
