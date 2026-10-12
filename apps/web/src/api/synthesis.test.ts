import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setLang, translateIn } from '../i18n/i18n'
import {
  ACTIVE_SYNTHESIS_STATES,
  cancelSynthesis,
  createSynthesis,
  deleteSynthesis,
  getSynthesis,
  getSynthesisOptions,
  listSynthesis,
  messageForSynthesisError,
  SynthesisApiError,
  subscribeSynthesisEvents,
  synthesisAudioUrl,
} from './synthesis'

afterEach(() => {
  vi.unstubAllGlobals()
  setLang('es')
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function noContent(): Response {
  return {
    ok: true,
    status: 204,
    json: () => Promise.reject(new SyntaxError('sin cuerpo')),
  } as unknown as Response
}

function stubFetch(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const OPTIONS = {
  providers: [{ provider_id: 'sherpa-onnx', display_name: 'sherpa-onnx', locality: 'local' }],
  models: [
    {
      provider_id: 'sherpa-onnx',
      model_id: 'piper-es',
      display_name: 'Piper es_MX',
      runtime_ready: true,
      languages: ['es'],
      voices: [{ id: '0', name: 'Ald', languages: ['es'] }],
    },
  ],
  max_chars: 20000,
  speed: { min: 0.5, max: 2.0 },
}

const VIEW = {
  id: 's1',
  state: 'COMPLETED',
  progress: 1,
  chunks_done: 2,
  chunks_total: 2,
  error_code: null,
  created_at: '2026-10-12T10:00:00Z',
  updated_at: '2026-10-12T10:00:02Z',
  started_at: '2026-10-12T10:00:01Z',
  provider_id: 'sherpa-onnx',
  model_id: 'piper-es',
  voice_id: '0',
  language: null,
  speed: 1.0,
  text_length: 32,
  text_preview: 'Hola mundo',
  audio: { duration_ms: 2100, sample_rate: 22050, size_bytes: 92652, url: '/api/synthesis/s1/audio' },
}

describe('api/synthesis', () => {
  it('getSynthesisOptions valida y devuelve las opciones', async () => {
    const fetchMock = stubFetch(jsonResponse(200, OPTIONS))
    await expect(getSynthesisOptions()).resolves.toEqual(OPTIONS)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/synthesis/options')
  })

  it('acepta opciones sin motores ni modelos', async () => {
    stubFetch(jsonResponse(200, { ...OPTIONS, providers: [], models: [] }))
    await expect(getSynthesisOptions()).resolves.toMatchObject({ models: [] })
  })

  it.each([
    ['sin max_chars', { ...OPTIONS, max_chars: undefined }],
    ['max_chars cero', { ...OPTIONS, max_chars: 0 }],
    ['velocidad incompleta', { ...OPTIONS, speed: { min: 0.5 } }],
    ['modelo sin voces', { ...OPTIONS, models: [{ ...OPTIONS.models[0], voices: undefined }] }],
    ['voz con id numérico', { ...OPTIONS, models: [{ ...OPTIONS.models[0], voices: [{ id: 0, name: 'x', languages: [] }] }] }],
    ['runtime_ready de texto', { ...OPTIONS, models: [{ ...OPTIONS.models[0], runtime_ready: 'sí' }] }],
    ['cuerpo no objeto', []],
  ])('rechaza opciones inválidas (%s) con invalid_response', async (_name, body) => {
    stubFetch(jsonResponse(200, body))
    await expect(getSynthesisOptions()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('un error HTTP lleva el código estable y su texto traducido', async () => {
    stubFetch(jsonResponse(409, { detail: { code: 'synthesis_model_not_installed', message: 'x' } }))
    const error: unknown = await createSynthesis({
      text: 'hola',
      provider_id: 'sherpa-onnx',
      model_id: 'piper-es',
      voice_id: '0',
    }).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(SynthesisApiError)
    expect(error).toMatchObject({ code: 'synthesis_model_not_installed', status: 409 })
    expect((error as Error).message).toMatch(/instálalo en Modelos/)
  })

  it('sin cuerpo de error usa http_<estado>; un código desconocido muestra el código', async () => {
    stubFetch(jsonResponse(500, null))
    await expect(getSynthesis('s1')).rejects.toMatchObject({ code: 'http_500' })
    expect(messageForSynthesisError('algo_nuevo')).toContain('algo_nuevo')
  })

  it('un fallo de red se convierte en network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(listSynthesis()).rejects.toMatchObject({ code: 'network_error' })
  })

  it('createSynthesis envía el cuerpo JSON y exige reused', async () => {
    const fetchMock = stubFetch(jsonResponse(201, { ...VIEW, reused: false }))
    const input = { text: 'Hola', provider_id: 'sherpa-onnx', model_id: 'piper-es', voice_id: '0', speed: 1.25 }
    const created = await createSynthesis(input)
    expect(created.reused).toBe(false)
    expect(created.audio?.url).toBe('/api/synthesis/s1/audio')
    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/synthesis')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(input)

    stubFetch(jsonResponse(201, VIEW))
    await expect(createSynthesis(input)).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('normaliza campos opcionales ausentes (audio, language, started_at)', async () => {
    const partial: Record<string, unknown> = { ...VIEW }
    delete partial.audio
    delete partial.started_at
    delete partial.language
    stubFetch(jsonResponse(200, { ...partial, state: 'RUNNING', text: 'Hola mundo completo' }))
    const view = await getSynthesis('s1')
    expect(view).toMatchObject({ audio: null, started_at: null, language: null, text: 'Hola mundo completo' })
  })

  it('rechaza vistas con estado desconocido o tipos incorrectos', async () => {
    stubFetch(jsonResponse(200, { ...VIEW, state: 'EXPLODED' }))
    await expect(getSynthesis('s1')).rejects.toMatchObject({ code: 'invalid_response' })
    stubFetch(jsonResponse(200, { ...VIEW, progress: '0.5' }))
    await expect(getSynthesis('s1')).rejects.toMatchObject({ code: 'invalid_response' })
    stubFetch(jsonResponse(200, { ...VIEW, audio: { duration_ms: 1 } }))
    await expect(getSynthesis('s1')).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('getSynthesis y cancelSynthesis codifican el id', async () => {
    const fetchMock = stubFetch(jsonResponse(200, VIEW))
    await getSynthesis('a/b c')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/synthesis/a%2Fb%20c')
    stubFetch(jsonResponse(202, { ...VIEW, state: 'CANCELLING', audio: null }))
    const cancelMock = vi.mocked(fetch)
    const cancelled = await cancelSynthesis('s1')
    expect(cancelled.state).toBe('CANCELLING')
    expect(cancelMock.mock.calls[0]?.[0]).toBe('/api/synthesis/s1/cancel')
    expect(cancelMock.mock.calls[0]?.[1]?.method).toBe('POST')
  })

  it('listSynthesis pide el límite y valida cada elemento', async () => {
    const fetchMock = stubFetch(jsonResponse(200, { items: [VIEW] }))
    await expect(listSynthesis(20)).resolves.toHaveLength(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/synthesis?limit=20')

    const noLimit = stubFetch(jsonResponse(200, { items: [] }))
    await listSynthesis()
    expect(noLimit.mock.calls[0]?.[0]).toBe('/api/synthesis')

    stubFetch(jsonResponse(200, { items: [{ id: 'x' }] }))
    await expect(listSynthesis()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('deleteSynthesis manda la cabecera de confirmación y acepta 204 sin cuerpo', async () => {
    const fetchMock = stubFetch(noContent())
    await expect(deleteSynthesis('s1')).resolves.toBeUndefined()
    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/synthesis/s1')
    expect(init?.method).toBe('DELETE')
    expect(new Headers(init?.headers).get('X-VOZ-Action')).toBe('delete-synthesis')
  })

  it('deleteSynthesis propaga el 409 de un trabajo activo', async () => {
    stubFetch(jsonResponse(409, { detail: { code: 'synthesis_job_active', message: 'x' } }))
    await expect(deleteSynthesis('s1')).rejects.toMatchObject({
      code: 'synthesis_job_active',
      status: 409,
    })
  })

  it('synthesisAudioUrl direcciona por id y admite descarga', () => {
    expect(synthesisAudioUrl('s1')).toBe('/api/synthesis/s1/audio')
    expect(synthesisAudioUrl('a b', true)).toBe('/api/synthesis/a%20b/audio?download=true')
  })

  it('los estados activos son los que impiden borrar', () => {
    expect([...ACTIVE_SYNTHESIS_STATES].sort()).toEqual(['CANCELLING', 'PERSISTING', 'QUEUED', 'RUNNING'])
  })

  it('cada código de la API documentada tiene mensaje en español e inglés', () => {
    const codes = [
      'synthesis_provider_not_found',
      'synthesis_model_unknown',
      'synthesis_voice_not_found',
      'synthesis_model_not_installed',
      'synthesis_runtime_unavailable',
      'synthesis_request_invalid',
      'synthesis_job_not_found',
      'synthesis_job_terminal',
      'synthesis_job_active',
      'synthesis_audio_not_ready',
      'synthesis_audio_missing',
      'synthesis_delete_forbidden',
      'synthesis_delete_failed',
      // Códigos de fallo del trabajo (`error_code`).
      'voice_not_found',
      'model_not_installed',
      'runtime_unavailable',
      'synthesis_failed',
      'text_too_long',
      'io_error',
      'synthesis_internal_error',
      'synthesis_runner_crashed',
      'events_lost',
      'events_invalid',
    ]
    for (const code of codes) {
      const key = ('err.synth.' + code) as Parameters<typeof translateIn>[1]
      expect(translateIn('es', key)).not.toBe('')
      expect(translateIn('en', key)).not.toBe(translateIn('es', key))
    }
  })
})

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

  emit(type: string, data: unknown) {
    this.dispatchEvent(
      new MessageEvent(type, { data: typeof data === 'string' ? data : JSON.stringify(data) }),
    )
  }
}

describe('subscribeSynthesisEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  const handlers = () => ({ onJob: vi.fn(), onEnd: vi.fn(), onError: vi.fn() })
  const source = () => FakeEventSource.instances[0] as FakeEventSource

  it('abre el stream del trabajo y entrega cada vista con los opcionales rellenados', () => {
    const h = handlers()
    subscribeSynthesisEvents('a b', h)
    expect(source().url).toBe('/api/synthesis/a%20b/events')

    const omitted = ['started_at', 'language', 'audio']
    const partial = Object.fromEntries(Object.entries(VIEW).filter(([key]) => !omitted.includes(key)))
    source().emit('job', partial)

    expect(h.onJob).toHaveBeenCalledTimes(1)
    expect(h.onJob.mock.calls[0]?.[0]).toMatchObject({ id: VIEW.id, started_at: null, language: null, audio: null })
  })

  it('end cierra el stream y avisa una sola vez; después ignora eventos', () => {
    const h = handlers()
    subscribeSynthesisEvents(VIEW.id, h)

    source().emit('end', {})
    source().emit('job', VIEW)

    expect(source().close).toHaveBeenCalledTimes(1)
    expect(h.onEnd).toHaveBeenCalledTimes(1)
    expect(h.onJob).not.toHaveBeenCalled()
  })

  it('un payload inválido es un error con código estable', () => {
    const h = handlers()
    subscribeSynthesisEvents(VIEW.id, h)

    source().emit('job', '{no es json')
    source().emit('job', { id: VIEW.id })

    expect(h.onError).toHaveBeenCalledTimes(2)
    expect(h.onError.mock.calls[0]?.[0]).toMatchObject({ code: 'events_invalid' })
    expect(h.onJob).not.toHaveBeenCalled()
  })

  it('solo un stream cerrado del todo se reporta como conexión perdida', () => {
    const h = handlers()
    subscribeSynthesisEvents(VIEW.id, h)

    source().dispatchEvent(new Event('error'))
    expect(h.onError).not.toHaveBeenCalled()

    source().readyState = FakeEventSource.CLOSED
    source().dispatchEvent(new Event('error'))
    expect(h.onError.mock.calls[0]?.[0]).toMatchObject({ code: 'events_lost' })
  })

  it('la función devuelta cierra el stream y silencia los eventos', () => {
    const h = handlers()
    const stop = subscribeSynthesisEvents(VIEW.id, h)

    stop()
    stop()
    source().emit('job', VIEW)

    expect(source().close).toHaveBeenCalledTimes(1)
    expect(h.onJob).not.toHaveBeenCalled()
  })
})
