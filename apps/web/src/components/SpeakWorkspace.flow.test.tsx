import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SynthesisView } from '../api/synthesis'
import { setLang } from '../i18n/i18n'
import { SpeakWorkspace } from './SpeakWorkspace'

vi.mock('./SpeakHistory', () => ({ SpeakHistory: () => null }))

class FakeEventSource extends EventTarget {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readyState = FakeEventSource.OPEN
  readonly close = vi.fn(() => {
    this.readyState = FakeEventSource.CLOSED
  })

  constructor(readonly url: string) {
    super()
    FakeEventSource.instances.push(this)
  }
}

class FakeAudio extends EventTarget {
  static instances: FakeAudio[] = []
  readonly play = vi.fn(() => Promise.resolve())
  readonly pause = vi.fn()

  constructor(readonly src: string) {
    super()
    FakeAudio.instances.push(this)
  }
}

const KOKORO = {
  provider_id: 'sherpa-onnx',
  model_id: 'kokoro',
  display_name: 'Kokoro multilingüe',
  runtime_ready: true,
  languages: ['en', 'es'],
  voices: [
    { id: '10', name: 'Bella', languages: ['en'] },
    { id: '20', name: 'Dora', languages: ['es'] },
    { id: '21', name: 'Alex', languages: ['es'] },
  ],
}

const PIPER = {
  provider_id: 'sherpa-onnx',
  model_id: 'piper-es',
  display_name: 'Piper es_MX',
  runtime_ready: true,
  languages: ['es'],
  voices: [
    { id: '0', name: 'Ald', languages: ['es'] },
    { id: '1', name: 'Claude', languages: ['es'] },
  ],
}

const OPTIONS = {
  providers: [{ provider_id: 'sherpa-onnx', display_name: 'sherpa-onnx', locality: 'local' }],
  models: [PIPER, KOKORO],
  max_chars: 100,
  speed: { min: 0.5, max: 2 },
}

function view(overrides: Partial<SynthesisView> = {}): SynthesisView {
  return {
    id: 'job-1',
    state: 'QUEUED',
    progress: 0,
    chunks_done: 0,
    chunks_total: 0,
    error_code: null,
    created_at: '2026-10-12T12:00:00+00:00',
    updated_at: '2026-10-12T12:00:00+00:00',
    started_at: null,
    provider_id: 'sherpa-onnx',
    model_id: 'piper-es',
    voice_id: '0',
    language: null,
    speed: 1,
    text_length: 20,
    text_preview: 'Hola',
    audio: null,
    ...overrides,
  }
}

const DONE = view({
  state: 'COMPLETED',
  progress: 1,
  chunks_done: 2,
  chunks_total: 2,
  audio: { duration_ms: 65_000, sample_rate: 22_050, size_bytes: 2_621_440, url: '/api/synthesis/job-1/audio' },
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

const urlOf = (input: RequestInfo | URL): string =>
  typeof input === 'string' ? input : input instanceof URL ? input.href : input.url

interface Api {
  posts: unknown[]
  cancels: string[]
  fetchMock: ReturnType<typeof vi.fn<typeof fetch>>
}

/** Enruta fetch por URL; los snapshots GET quedan colgados para que el progreso llegue solo por SSE. */
function stubApi(creates: Response[], cancel: Response = jsonResponse(202, view({ state: 'CANCELLING' }))): Api {
  const api: Api = { posts: [], cancels: [], fetchMock: vi.fn<typeof fetch>() }
  const pending = [...creates]
  api.fetchMock.mockImplementation((input, init) => {
    const url = urlOf(input)
    const method = init?.method ?? 'GET'
    if (url === '/api/synthesis/options') {
      return Promise.resolve(jsonResponse(200, OPTIONS))
    }
    if (url === '/api/synthesis' && method === 'POST') {
      api.posts.push(JSON.parse(typeof init?.body === 'string' ? init.body : 'null'))
      return Promise.resolve(pending.shift() ?? jsonResponse(500, {}))
    }
    if (url.endsWith('/cancel')) {
      api.cancels.push(url)
      return Promise.resolve(cancel)
    }
    return new Promise<Response>(() => undefined)
  })
  vi.stubGlobal('fetch', api.fetchMock)
  return api
}

const latest = () => {
  const source = FakeEventSource.instances.at(-1)
  if (!source) {
    throw new Error('no EventSource was opened')
  }
  return source
}

function emit(type: string, data: unknown) {
  act(() => {
    latest().dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }))
  })
}

const created = (overrides: Partial<SynthesisView> = {}, reused = false, status = 201) =>
  jsonResponse(status, { ...view(overrides), reused })

async function open() {
  render(<SpeakWorkspace onOpenModels={() => undefined} />)
  await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
}

const area = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Texto a convertir en voz' })
const type = (text: string) => {
  fireEvent.change(area(), { target: { value: text } })
}
/** Texto de la notificación de error (el TextArea de Carbon también tiene un `alert` propio, vacío). */
const notice = () => {
  const found = screen.getAllByRole('alert').find((node) => node.classList.contains('cds--inline-notification'))
  if (!found) {
    throw new Error('no error notice')
  }
  return found.textContent
}
/** Espera a que la muestra o la generación hayan abierto su stream de eventos. */
const streamOpen = (count = 1) =>
  waitFor(() => {
    expect(FakeEventSource.instances).toHaveLength(count)
  })
const button = (name: string | RegExp) => screen.getByRole<HTMLButtonElement>('button', { name })

beforeEach(() => {
  setLang('es')
  window.localStorage.clear()
  FakeEventSource.instances = []
  FakeAudio.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('Audio', FakeAudio)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SpeakWorkspace: selectores', () => {
  it('lista los modelos instalados y las voces del elegido; sin idioma si tiene uno solo', async () => {
    stubApi([])
    await open()

    const models = screen.getByLabelText<HTMLSelectElement>('Modelo')
    expect([...models.options].map((option) => option.text)).toEqual(['Piper es_MX', 'Kokoro multilingüe'])
    expect(screen.getByText('Idiomas: español')).toBeDefined()
    const voices = screen.getByLabelText<HTMLSelectElement>('Voz', { selector: 'select' })
    expect([...voices.options].map((option) => option.text)).toEqual(['Ald', 'Claude'])
    expect(screen.queryByLabelText('Idioma')).toBeNull()
  })

  it('un modelo con varios idiomas añade el selector y filtra las voces', async () => {
    stubApi([])
    await open()

    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'sherpa-onnx:kokoro' } })

    const language = screen.getByLabelText<HTMLSelectElement>('Idioma')
    expect(language.value).toBe('es')
    expect([...language.options].map((option) => option.text)).toEqual(['inglés', 'español'])
    const voices = screen.getByLabelText<HTMLSelectElement>('Voz', { selector: 'select' })
    expect([...voices.options].map((option) => option.text)).toEqual(['Dora', 'Alex'])

    fireEvent.change(language, { target: { value: 'en' } })
    expect([...voices.options].map((option) => option.text)).toEqual(['Bella'])
  })

  it('la velocidad usa el rango de la API, se puede restablecer y se recuerda', async () => {
    stubApi([])
    await open()
    const range = screen.getByLabelText<HTMLInputElement>('Velocidad')
    expect([range.min, range.max]).toEqual(['0.5', '2'])
    expect(screen.getByRole('button', { name: 'Velocidad normal (1×)' })).toHaveProperty('disabled', true)

    fireEvent.change(range, { target: { value: '1.5' } })
    expect(range.getAttribute('aria-valuetext')).toBe('1,5×')
    fireEvent.change(screen.getByLabelText('Voz', { selector: 'select' }), { target: { value: '1' } })

    cleanup()
    await open()
    expect(screen.getByLabelText<HTMLInputElement>('Velocidad').value).toBe('1.5')
    expect(screen.getByLabelText<HTMLSelectElement>('Voz', { selector: 'select' }).value).toBe('1')

    fireEvent.click(screen.getByRole('button', { name: 'Velocidad normal (1×)' }))
    expect(screen.getByLabelText<HTMLInputElement>('Velocidad').value).toBe('1')
  })

  it('un almacenamiento que lanza no impide elegir', async () => {
    stubApi([])
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('bloqueado')
      },
      setItem: () => {
        throw new Error('bloqueado')
      },
    })
    await open()

    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'sherpa-onnx:kokoro' } })

    expect(screen.getByLabelText<HTMLSelectElement>('Modelo').value).toBe('sherpa-onnx:kokoro')
  })

  it('un modelo con motor no listo avisa y bloquea generar y la muestra', async () => {
    const fetchMock = stubApi([])
    fetchMock.fetchMock.mockImplementation((input) =>
      Promise.resolve(
        urlOf(input) === '/api/synthesis/options'
          ? jsonResponse(200, { ...OPTIONS, models: [{ ...PIPER, runtime_ready: false }] })
          : new Response(),
      ),
    )
    await open()
    type('Hola')

    expect(screen.getByText(/El motor de este modelo no está listo/)).toBeDefined()
    expect(button('Generar audio').disabled).toBe(true)
    expect(button('Escuchar muestra').disabled).toBe(true)
  })
})

describe('SpeakWorkspace: muestra', () => {
  it('sintetiza solo la primera oración con la elección actual y la reproduce', async () => {
    const api = stubApi([created()])
    await open()
    fireEvent.change(screen.getByLabelText('Voz', { selector: 'select' }), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Velocidad'), { target: { value: '1.2' } })
    type('Hola mundo. Esta segunda frase no se oye.')

    fireEvent.click(button('Escuchar muestra'))

    await waitFor(() => {
      expect(api.posts).toEqual([
        {
          text: 'Hola mundo.',
          provider_id: 'sherpa-onnx',
          model_id: 'piper-es',
          voice_id: '1',
          language: null,
          speed: 1.2,
        },
      ])
    })
    await screen.findByRole('button', { name: 'Cancelar muestra' })
    expect(screen.getByText('Preparando la muestra…')).toBeDefined()

    emit('job', view({ state: 'RUNNING', progress: 0.5 }))
    expect(FakeAudio.instances).toHaveLength(0)
    emit('job', DONE)

    await screen.findByRole('button', { name: 'Detener muestra' })
    expect(FakeAudio.instances).toHaveLength(1)
    expect(FakeAudio.instances[0]?.src).toBe('/api/synthesis/job-1/audio')
    expect(FakeAudio.instances[0]?.play).toHaveBeenCalledTimes(1)

    act(() => {
      FakeAudio.instances[0]?.dispatchEvent(new Event('ended'))
    })
    expect(button('Escuchar muestra').disabled).toBe(false)
    // La muestra no se confunde con una generación: no hay panel de resultado.
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.queryByRole('link', { name: 'Descargar WAV' })).toBeNull()
  })

  it('sin texto usa la frase fija del idioma de la voz', async () => {
    const api = stubApi([created(), created()])
    await open()

    fireEvent.click(button('Escuchar muestra'))
    await waitFor(() => {
      expect(api.posts).toHaveLength(1)
    })
    expect(api.posts[0]).toMatchObject({ text: 'Hola, esta es una muestra de mi voz.' })

    fireEvent.click(button('Cancelar muestra'))
    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'sherpa-onnx:kokoro' } })
    fireEvent.change(screen.getByLabelText('Idioma'), { target: { value: 'en' } })
    fireEvent.click(button('Escuchar muestra'))
    await waitFor(() => {
      expect(api.posts).toHaveLength(2)
    })
    expect(api.posts[1]).toMatchObject({
      text: 'Hello, this is a short sample of my voice.',
      language: 'en',
      voice_id: '10',
    })
  })

  it('cancelarla mientras se prepara cancela el trabajo y vuelve a reposo', async () => {
    const api = stubApi([created()])
    await open()
    fireEvent.click(button('Escuchar muestra'))
    await screen.findByRole('button', { name: 'Cancelar muestra' })

    fireEvent.click(button('Cancelar muestra'))

    await waitFor(() => {
      expect(api.cancels).toEqual(['/api/synthesis/job-1/cancel'])
    })
    expect(button('Escuchar muestra').disabled).toBe(false)
    expect(FakeEventSource.instances.at(-1)?.close).toHaveBeenCalled()
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('detenerla mientras suena pausa el audio', async () => {
    stubApi([created()])
    await open()
    fireEvent.click(button('Escuchar muestra'))
    await streamOpen()
    emit('job', DONE)
    fireEvent.click(await screen.findByRole('button', { name: 'Detener muestra' }))

    expect(FakeAudio.instances[0]?.pause).toHaveBeenCalled()
    expect(button('Escuchar muestra').disabled).toBe(false)
  })

  it('una muestra reutilizada no se cancela al detenerla (podría ser la generación de otro)', async () => {
    const api = stubApi([created({}, true, 200)])
    await open()
    fireEvent.click(button('Escuchar muestra'))
    await screen.findByRole('button', { name: 'Cancelar muestra' })

    fireEvent.click(button('Cancelar muestra'))

    expect(api.cancels).toEqual([])
  })

  it('si el trabajo de la muestra falla muestra el mensaje y no reproduce', async () => {
    stubApi([created()])
    await open()
    fireEvent.click(button('Escuchar muestra'))
    await streamOpen()

    emit('job', view({ state: 'FAILED', error_code: 'voice_not_found' }))

    await screen.findByText(/La voz elegida ya no existe/)
    expect(notice()).toMatch(/No se pudo preparar la muestra/)
    expect(button('Escuchar muestra').disabled).toBe(false)
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('si el navegador bloquea la reproducción lo explica', async () => {
    stubApi([created()])
    class BlockedAudio extends FakeAudio {
      override readonly play = vi.fn(() => Promise.reject(new DOMException('no', 'NotAllowedError')))
    }
    vi.stubGlobal('Audio', BlockedAudio)
    await open()
    fireEvent.click(button('Escuchar muestra'))
    await streamOpen()

    emit('job', DONE)

    await screen.findByText(/bloqueó la reproducción automática/)
    expect(button('Escuchar muestra').disabled).toBe(false)
  })
})

describe('SpeakWorkspace: generar', () => {
  it('no se puede generar sin texto, ni pasado del límite', async () => {
    stubApi([])
    await open()

    expect(button('Generar audio').disabled).toBe(true)
    expect(screen.getByText(/Escribe un texto para poder generar el audio/)).toBeDefined()
    type('a'.repeat(101))
    expect(button('Generar audio').disabled).toBe(true)
    type('a'.repeat(100))
    expect(button('Generar audio').disabled).toBe(false)
  })

  it('en cola, sintetizando con progreso por fragmentos y al final audio, descarga y datos', async () => {
    const api = stubApi([created()])
    await open()
    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'sherpa-onnx:kokoro' } })
    type('Hola mundo')

    fireEvent.click(button('Generar audio'))

    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()
    expect(api.posts[0]).toEqual({
      text: 'Hola mundo',
      provider_id: 'sherpa-onnx',
      model_id: 'kokoro',
      voice_id: '20',
      language: 'es',
      speed: 1,
    })
    expect(FakeEventSource.instances.at(-1)?.url).toBe('/api/synthesis/job-1/events')
    expect(screen.getByText(/Esperando a que termine otro trabajo/)).toBeDefined()
    // Mientras corre no se puede generar otra ni cambiar la elección.
    expect(button('Generar audio').disabled).toBe(true)
    expect(screen.getByLabelText<HTMLSelectElement>('Modelo').disabled).toBe(true)

    emit('job', view({ state: 'RUNNING', progress: 0.5, chunks_done: 1, chunks_total: 2 }))
    await screen.findByRole('heading', { name: 'Sintetizando la voz' })
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('50')
    expect(screen.getByText('1 de 2 fragmentos · 50 %')).toBeDefined()

    emit('job', view({ state: 'PERSISTING', progress: 1, chunks_done: 2, chunks_total: 2 }))
    await screen.findByRole('heading', { name: 'Guardando el audio' })

    emit('job', DONE)
    emit('end', {})
    await screen.findByRole('heading', { name: 'Audio listo' })
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()

    const result = screen.getByRole('region', { name: 'Audio listo' })
    const audio = result.querySelector('audio')
    expect(audio?.getAttribute('src')).toBe('/api/synthesis/job-1/audio')
    expect(within(result).getByRole('group', { name: 'Controles de reproducción' })).toBeDefined()
    expect(result.querySelector('.voz-speak-figures')?.textContent).toContain('1:05')
    expect(within(result).getByText('22,05 kHz')).toBeDefined()
    expect(within(result).getByText('2,5 MB')).toBeDefined()
    expect(within(result).getByText('Dora')).toBeDefined()
    const download = within(result).getByRole('link', { name: 'Descargar WAV' })
    expect(download.getAttribute('href')).toBe('/api/synthesis/job-1/audio?download=true')
    expect(screen.queryByText('Resultado reutilizado')).toBeNull()
    expect(button('Generar audio').disabled).toBe(false)
  })

  it('cancelar pide la cancelación y muestra cancelando y luego cancelada', async () => {
    const api = stubApi([created()])
    await open()
    type('Hola mundo')
    fireEvent.click(button('Generar audio'))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()
    emit('job', view({ state: 'RUNNING', progress: 0.25, chunks_done: 1, chunks_total: 4 }))

    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }))

    await waitFor(() => {
      expect(api.cancels).toEqual(['/api/synthesis/job-1/cancel'])
    })
    emit('job', view({ state: 'CANCELLING', progress: 0.25 }))
    await screen.findByRole('heading', { name: 'Cancelando la generación' })
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()

    emit('job', view({ state: 'CANCELLED', progress: 0.25 }))
    emit('end', {})
    await screen.findByRole('heading', { name: 'Generación cancelada' })
    expect(screen.getByText('Cancelaste la generación. No se guardó audio.')).toBeDefined()
    expect(screen.queryByRole('link', { name: 'Descargar WAV' })).toBeNull()
    expect(button('Generar audio').disabled).toBe(false)
  })

  it('un trabajo fallido muestra el código traducido y deja volver a intentar', async () => {
    stubApi([created()])
    await open()
    type('Hola mundo')
    fireEvent.click(button('Generar audio'))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()

    emit('job', view({ state: 'FAILED', error_code: 'synthesis_failed' }))

    await screen.findByRole('heading', { name: 'La generación falló' })
    expect(notice()).toMatch(/El motor no pudo sintetizar el texto/)
    expect(button('Generar audio').disabled).toBe(false)
  })

  it('un código de fallo desconocido se muestra tal cual en el texto genérico', async () => {
    stubApi([created()])
    await open()
    type('Hola')
    fireEvent.click(button('Generar audio'))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()

    emit('job', view({ state: 'FAILED', error_code: 'rarisimo' }))

    await screen.findByText(/código: rarisimo/)
  })

  it('un rechazo de POST se explica sin abrir el panel de resultado', async () => {
    stubApi([jsonResponse(409, { detail: { code: 'synthesis_model_not_installed', message: 'x' } })])
    await open()
    type('Hola')

    fireEvent.click(button('Generar audio'))

    await screen.findByText(/El modelo de voz no está instalado/)
    expect(screen.queryByRole('region', { name: 'En cola, esperando turno' })).toBeNull()
    expect(button('Generar audio').disabled).toBe(false)
  })

  it('resultado reutilizado: lo avisa y muestra el audio sin esperar al stream', async () => {
    const api = stubApi([created(DONE, true, 200)])
    await open()
    type('Hola mundo')

    fireEvent.click(button('Generar audio'))

    await screen.findByText('Resultado reutilizado')
    expect(screen.getByRole('heading', { name: 'Audio listo' })).toBeDefined()
    expect(screen.getByRole('link', { name: 'Descargar WAV' })).toBeDefined()
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(api.posts).toHaveLength(1)
  })

  it('si el stream se corta ofrece reconectar', async () => {
    stubApi([created()])
    await open()
    type('Hola')
    fireEvent.click(button('Generar audio'))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()
    const first = latest()

    first.readyState = FakeEventSource.CLOSED
    act(() => {
      first.dispatchEvent(new Event('error'))
    })
    expect(screen.getByText(/Se perdió la conexión con el progreso/)).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Reconectar' }))

    expect(FakeEventSource.instances).toHaveLength(2)
    emit('job', view({ state: 'RUNNING', progress: 0.5, chunks_done: 1, chunks_total: 2 }))
    expect(screen.queryByText(/Se perdió la conexión/)).toBeNull()
  })

  it('cierra el stream al desmontar', async () => {
    stubApi([created()])
    await open()
    type('Hola')
    fireEvent.click(button('Generar audio'))
    await screen.findByRole('heading', { name: 'En cola, esperando turno' })
    await streamOpen()

    cleanup()

    expect(latest().close).toHaveBeenCalled()
  })

  it('en inglés traduce estados, progreso y descarga', async () => {
    setLang('en')
    stubApi([created()])
    render(<SpeakWorkspace onOpenModels={() => undefined} />)
    fireEvent.change(await screen.findByRole('textbox', { name: 'Text to turn into speech' }), {
      target: { value: 'Hello' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Generate audio' }))
    await screen.findByRole('heading', { name: 'Queued, waiting for its turn' })
    emit('job', view({ state: 'RUNNING', progress: 0.5, chunks_done: 1, chunks_total: 2 }))
    await screen.findByText('1 of 2 chunks · 50%')
    emit('job', DONE)

    await screen.findByRole('link', { name: 'Download WAV' })
    expect(screen.getByRole('button', { name: 'Hear a sample' })).toBeDefined()
  })
})
