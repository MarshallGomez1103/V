import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  cancelModelTask,
  deleteModel,
  getModels,
  installModel,
  listModelTasks,
  capabilityLabel,
  capabilityLabels,
  messageForModelError,
  modelGroup,
  ModelApiError,
  type ModelView,
} from './models'
import { translateIn } from '../i18n/i18n'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function stubFetch(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const MODEL = {
  key: 'faster-whisper:tiny',
  provider_id: 'faster-whisper',
  kind: 'asr',
  requires: null,
  runtime_available: true,
  model_id: 'tiny',
  display_name: 'Faster Whisper Tiny (fast)',
  source: 'Systran/faster-whisper-tiny',
  revision: 'd90ca5fe260221311c53c58e660288d3deb8d356',
  license: 'MIT',
  multilingual: true,
  profile: 'fast',
  size_bytes: 77003619,
  installed: false,
  disk_bytes: null,
  external: [{ origin: 'buzz' }],
}

const TASK = {
  id: 't1',
  key: 'faster-whisper:tiny',
  model_id: 'tiny',
  method: 'download',
  origin: null,
  state: 'running',
  done_bytes: 10,
  total_bytes: 100,
  error_code: null,
  created_at: '2026-09-30T10:00:00Z',
  updated_at: '2026-09-30T10:00:01Z',
}

describe('api/models', () => {
  it.each([null, 'sherpa-onnx-asr', [123], {}])('rejects malformed custom engines %j', async (custom_engines) => {
    stubFetch(jsonResponse(200, { models: [], disk: { models_bytes: 0, free_bytes: null }, custom_engines }))
    await expect(getModels()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('accepts custom engines without requiring an existing model', async () => {
    const payload = { models: [], disk: { models_bytes: 0, free_bytes: null }, custom_engines: ['sherpa-onnx-asr'] }
    stubFetch(jsonResponse(200, payload))
    await expect(getModels()).resolves.toEqual(payload)
  })

  it('getModels devuelve el payload validado', async () => {
    const payload = { models: [MODEL], disk: { models_bytes: 0, free_bytes: null } }
    const fetchMock = stubFetch(jsonResponse(200, payload))

    await expect(getModels()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/models',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('getModels acepta la entrada de diarización sin fuente ni perfil', async () => {
    const diarization = {
      ...MODEL,
      key: 'diarization:sherpa-default',
      provider_id: 'diarization',
      kind: 'diarization',
      requires: 'diarization',
      runtime_available: false,
      model_id: 'sherpa-default',
      source: null,
      revision: null,
      profile: null,
      external: [],
    }
    const payload = {
      models: [diarization],
      disk: { models_bytes: 0, free_bytes: null },
    }
    stubFetch(jsonResponse(200, payload))

    await expect(getModels()).resolves.toEqual(payload)
  })

  it('getModels acepta capabilities opcionales y las valida', async () => {
    const disk = { models_bytes: 0, free_bytes: null }
    const withCaps = { ...MODEL, capabilities: ['transcription', 'cpu'] }
    stubFetch(jsonResponse(200, { models: [withCaps], disk }))
    await expect(getModels()).resolves.toEqual({ models: [withCaps], disk })

    stubFetch(
      jsonResponse(200, { models: [{ ...MODEL, capabilities: [1] }], disk }),
    )
    await expect(getModels()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('conserva espacio recuperable cero y compartido nulo', async () => {
    const payload = { models: [{ ...MODEL, reclaimable_bytes: 0, shared_bytes: null }], disk: { models_bytes: 0, free_bytes: null } }
    stubFetch(jsonResponse(200, payload))
    await expect(getModels()).resolves.toEqual(payload)
  })

  it.each(['reclaimable_bytes', 'shared_bytes'])('rechaza bytes opcionales mal formados (%s)', async (field) => {
    stubFetch(jsonResponse(200, { models: [{ ...MODEL, [field]: '4000' }], disk: { models_bytes: 0, free_bytes: null } }))
    await expect(getModels()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('getModels acepta un kind nuevo (síntesis) sin invalidar la lista', async () => {
    const disk = { models_bytes: 0, free_bytes: null }
    const voice = { ...MODEL, kind: 'tts', capabilities: ['synthesis'] }
    stubFetch(jsonResponse(200, { models: [voice], disk }))
    await expect(getModels()).resolves.toEqual({ models: [voice], disk })
  })

  it('getModels rechaza un formato inesperado', async () => {
    stubFetch(jsonResponse(200, { models: [{ model_id: 1 }], disk: {} }))

    await expect(getModels()).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('traduce el código de error del backend a un mensaje en español', async () => {
    stubFetch(
      jsonResponse(409, { detail: { code: 'model_in_use', message: 'in use' } }),
    )

    const error = await deleteModel('faster-whisper:tiny').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ModelApiError)
    expect(error).toMatchObject({ code: 'model_in_use', status: 409 })
    expect((error as Error).message).toMatch(/en uso/i)
  })

  it('deleteModel repite la clave codificada en confirm', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, {
        key: 'whisper-cpp:small',
        model_id: 'small',
        freed_bytes: 5,
      }),
    )

    await expect(deleteModel('whisper-cpp:small')).resolves.toMatchObject({
      freed_bytes: 5,
    })
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/models/whisper-cpp%3Asmall?confirm=whisper-cpp%3Asmall',
    )
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('DELETE')
  })

  it('installModel envía confirm y origin solo al importar', async () => {
    const fetchMock = stubFetch(jsonResponse(202, TASK))

    await installModel('faster-whisper:tiny', 'download')
    await installModel('faster-whisper:tiny', 'import')

    const bodies = fetchMock.mock.calls.map((call) =>
      JSON.parse(call[1]?.body as string) as unknown,
    )
    expect(bodies).toEqual([
      { method: 'download', confirm: true },
      { method: 'import', origin: 'buzz', confirm: true },
    ])
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/models/faster-whisper%3Atiny/install',
    )
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
  })

  it('listModelTasks y cancelModelTask usan los endpoints de tareas', async () => {
    const fetchMock = stubFetch(jsonResponse(200, { tasks: [TASK] }))
    await expect(listModelTasks()).resolves.toEqual([TASK])
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/model-tasks')

    const cancelMock = stubFetch(jsonResponse(202, { ...TASK, state: 'cancelled' }))
    await expect(cancelModelTask('t1')).resolves.toMatchObject({
      state: 'cancelled',
    })
    expect(cancelMock.mock.calls[0]?.[0]).toBe('/api/model-tasks/t1/cancel')
  })

  it('cancelar una tarea terminada informa model_task_terminal', async () => {
    stubFetch(
      jsonResponse(409, { detail: { code: 'model_task_terminal', message: 'x' } }),
    )

    await expect(cancelModelTask('t1')).rejects.toMatchObject({
      code: 'model_task_terminal',
    })
  })

  it('messageForModelError cubre checksum y deja visible un código desconocido', () => {
    expect(messageForModelError('disk_space_insufficient')).toMatch(/espacio/i)
    expect(messageForModelError('model_installation_network_error')).toMatch(
      /conexión/i,
    )
    expect(messageForModelError('model_installation_checksum_mismatch')).toMatch(
      /checksum/i,
    )
    expect(messageForModelError('algo_raro')).toMatch(/algo_raro/)
    expect(messageForModelError('constructor')).toMatch(/constructor/)
  })
})

describe('agrupación y etiquetas de capacidades', () => {
  const view = (patch: Partial<ModelView>): ModelView => ({
    ...(MODEL as ModelView),
    ...patch,
  })

  it('la capacidad principal decide la sección', () => {
    expect(modelGroup(view({ capabilities: ['cpu', 'transcription'] }))).toBe('transcription')
    expect(modelGroup(view({ kind: 'diarization', capabilities: ['cpu', 'diarization'] }))).toBe(
      'diarization',
    )
    expect(modelGroup(view({ kind: 'tts', capabilities: ['cpu', 'synthesis'] }))).toBe('synthesis')
  })

  it('sin capacidades o con vocabulario desconocido cae en transcripción; diarización por kind', () => {
    expect(modelGroup(view({}))).toBe('transcription')
    expect(modelGroup(view({ capabilities: ['wake_word'] }))).toBe('transcription')
    expect(modelGroup(view({ kind: 'diarization' }))).toBe('diarization')
  })

  const es = (key: Parameters<typeof translateIn>[1]) => translateIn('es', key)
  const en = (key: Parameters<typeof translateIn>[1]) => translateIn('en', key)

  it('etiqueta cada capacidad del vocabulario en es y en', () => {
    const vocabulary = [
      'transcription',
      'diarization',
      'word_timestamps',
      'translation',
      'language_detection',
      'cpu',
      'gpu',
      'synthesis',
      'alignment',
      'wake_word',
      'realtime',
    ]
    for (const capability of vocabulary) {
      expect(capabilityLabel(capability, es)).not.toBe(capability.replace('_', ' '))
      expect(capabilityLabel(capability, es)).not.toMatch(/^mm\./)
      expect(capabilityLabel(capability, en)).not.toMatch(/^mm\./)
    }
    expect(capabilityLabel('synthesis', es)).toBe('Síntesis de voz')
    expect(capabilityLabel('word_timestamps', en)).toBe('Word timestamps')
  })

  it('una capacidad desconocida se muestra tal cual', () => {
    expect(capabilityLabel('telepathy', es)).toBe('telepathy')
  })

  it('ordena funciones antes que hardware y omite la principal', () => {
    const model = view({ capabilities: ['gpu', 'cpu', 'translation', 'transcription', 'zeta'] })
    expect(capabilityLabels(model, es, 'transcription')).toEqual([
      'Traducción al inglés',
      'CPU',
      'GPU',
      'zeta',
    ])
  })
})
