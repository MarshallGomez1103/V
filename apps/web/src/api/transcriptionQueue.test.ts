import { afterEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import {
  cancelQueue,
  describeQueueError,
  getProjectQueue,
  QueueError,
  startQueue,
  type QueueView,
} from './transcriptionQueue'

afterEach(() => {
  vi.unstubAllGlobals()
  setLang('es')
})

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const VIEW: QueueView = {
  id: 'q1',
  project_id: 'p 1',
  created_at: '2026-11-11T10:00:00Z',
  state: 'running',
  progress: 0.25,
  counts: { total: 2, pending: 1, running: 1, done: 0, error: 0, cancelled: 0, skipped: 1 },
  items: [
    {
      position: 0, media_asset_id: 'm0', filename: 'a.wav', job_id: 'j0', status: 'running',
      job_state: 'TRANSCRIBING', progress: 0.5, error_code: null, transcript_id: null,
    },
    {
      position: 1, media_asset_id: 'm1', filename: 'b.wav', job_id: 'j1', status: 'pending',
      job_state: 'QUEUED', progress: 0, error_code: null, transcript_id: null,
    },
  ],
  skipped: [{ media_asset_id: 'm2', filename: 'c.wav', reason: 'duration_unknown' }],
}

function stub(response: Response) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(response))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('startQueue', () => {
  it('envía la opción y los hablantes a la ruta del proyecto y lee la vista', async () => {
    const fetchMock = stub(json(VIEW, 201))
    const input = { option_id: 'o1', language: null, diarization: { enabled: false, speakers: {} } }

    expect(await startQueue('p 1', input)).toEqual(VIEW)

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/projects/p%201/transcription-queue')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(input)
  })

  it('en un 409 de cola vacía conserva las omitidas que adjunta el servidor', async () => {
    stub(json({ detail: { code: 'transcription_queue_empty', message: 'x', skipped: VIEW.skipped } }, 409))

    const failure = await startQueue('p1', { option_id: 'o1', language: null }).catch((e: unknown) => e)

    expect(failure).toBeInstanceOf(QueueError)
    expect((failure as QueueError).code).toBe('transcription_queue_empty')
    expect((failure as QueueError).skipped).toEqual(VIEW.skipped)
  })

  it('una respuesta sin la forma de la cola es un error de respuesta inválida', async () => {
    stub(json({ ...VIEW, items: [{ position: 0 }] }, 201))

    await expect(startQueue('p1', { option_id: 'o1', language: null })).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
})

describe('getProjectQueue', () => {
  it('devuelve null si el proyecto nunca tuvo cola', async () => {
    const fetchMock = stub(json({ queue: null }))

    expect(await getProjectQueue('p1')).toBeNull()
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/projects/p1/transcription-queue')
  })

  it('devuelve la cola más reciente', async () => {
    stub(json({ queue: VIEW }))

    expect(await getProjectQueue('p1')).toEqual(VIEW)
  })

  it('un estado de ítem desconocido se rechaza', async () => {
    stub(json({ queue: { ...VIEW, items: [{ ...VIEW.items[0], status: 'paused' }] } }))

    await expect(getProjectQueue('p1')).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('traduce el 404 del proyecto', async () => {
    stub(json({ detail: { code: 'project_not_found', message: 'x' } }, 404))

    await expect(getProjectQueue('p1')).rejects.toMatchObject({
      code: 'project_not_found',
      message: 'El proyecto ya no existe.',
    })
  })
})

describe('cancelQueue', () => {
  it('hace POST a la ruta de cancelación de la cola', async () => {
    const fetchMock = stub(json(VIEW, 202))

    expect(await cancelQueue('q/1')).toEqual(VIEW)

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/transcription-queues/q%2F1/cancel')
    expect(init?.method).toBe('POST')
  })

  it('un estado HTTP sin cuerpo de la API cae al genérico con el código HTTP', async () => {
    stub(new Response('boom', { status: 502 }))

    await expect(cancelQueue('q1')).rejects.toMatchObject({
      code: 'http_502',
      message: 'No se pudo completar la operación de la cola (código http_502).',
    })
  })
})

const QUEUE_CODES = [
  'project_not_found',
  'option_unknown',
  'transcription_queue_active',
  'transcription_queue_empty',
  'option_not_startable',
  'insufficient_vram',
  'insufficient_ram',
  'diarization_unavailable',
  'diarization_models_missing',
  'transcription_queue_cloud_unsupported',
  'diarization_options_invalid',
  'quality_profile_unknown',
  'job_prompt_invalid',
  'job_options_unsupported',
  'transcription_queue_not_found',
  'transcription_queue_finished',
]

describe('describeQueueError', () => {
  it.each(QUEUE_CODES)('%s tiene mensaje propio en es y en, sin caer al genérico', (code) => {
    const messages = (['es', 'en'] as const).map((lang) => {
      setLang(lang)
      const message = describeQueueError(code)
      expect(message, lang).not.toContain(code)
      expect(message, lang).not.toMatch(/\(código|\(code/)
      return message
    })
    expect(messages[1]).not.toBe(messages[0])
  })

  it('un código nuevo muestra el genérico con su código', () => {
    expect(describeQueueError('gpu_lost')).toBe('No se pudo completar la operación de la cola (código gpu_lost).')
  })
})
