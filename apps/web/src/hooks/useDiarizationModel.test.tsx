import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useDiarizationModel } from './useDiarizationModel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const MODEL = {
  key: 'diarization:sherpa-default',
  provider_id: 'diarization',
  kind: 'diarization',
  requires: 'diarization',
  runtime_available: true,
  model_id: 'sherpa-default',
  display_name: 'Hablantes',
  source: null,
  revision: null,
  license: 'MIT',
  multilingual: true,
  profile: null,
  size_bytes: 33_000_000,
  installed: false,
  disk_bytes: null,
  external: [],
}
const ASR = { ...MODEL, key: 'faster-whisper:tiny', provider_id: 'faster-whisper', kind: 'asr', requires: null }

const json = (body: unknown, status = 200) =>
  Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })

function stub(opts: { model?: Record<string, unknown>; tasks?: unknown[]; modelsStatus?: number } = {}) {
  const calls: string[] = []
  const tasks: unknown[] = [...(opts.tasks ?? [])]
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push((init?.method ?? 'GET') + ' ' + url)
      if (url === '/api/models') {
        return opts.modelsStatus
          ? json({ detail: { code: 'boom' } }, opts.modelsStatus)
          : json({
              models: [ASR, { ...MODEL, ...opts.model }],
              disk: { models_bytes: 0, free_bytes: null },
            })
      }
      if (url === '/api/model-tasks') {
        return json({ tasks })
      }
      if (url.endsWith('/install')) {
        const created = { id: 't1', key: MODEL.key, model_id: 'sherpa-default', method: 'download', origin: null, state: 'queued', done_bytes: 0, total_bytes: 33_000_000, error_code: null, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z' }
        tasks.push(created)
        return json(created, 202)
      }
      return Promise.reject(new Error('sin simular ' + url))
    }),
  )
  return calls
}

describe('useDiarizationModel', () => {
  it('desactivado no consulta nada', () => {
    const calls = stub()
    const { result } = renderHook(() => useDiarizationModel(false))
    expect(result.current.status).toBe('off')
    expect(calls).not.toContain('GET /api/models')
  })

  it('si falta el modelo lo reporta como missing con su tamaño', async () => {
    stub()
    const { result } = renderHook(() => useDiarizationModel(true))
    expect(result.current.status).toBe('checking')
    await waitFor(() => {
      expect(result.current.status).toBe('missing')
    })
    expect(result.current.model?.size_bytes).toBe(33_000_000)
  })

  it('instalado: ready', async () => {
    stub({ model: { installed: true, disk_bytes: 32_000_000 } })
    const { result } = renderHook(() => useDiarizationModel(true))
    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })
  })

  it('sin el extra que lo ejecuta: unavailable (descargarlo no serviría)', async () => {
    stub({ model: { runtime_available: false } })
    const { result } = renderHook(() => useDiarizationModel(true))
    await waitFor(() => {
      expect(result.current.status).toBe('unavailable')
    })
  })

  it('un fallo al consultar: error con mensaje humano', async () => {
    stub({ modelsStatus: 500 })
    const { result } = renderHook(() => useDiarizationModel(true))
    await waitFor(() => {
      expect(result.current.status).toBe('error')
    })
    expect(result.current.error).toMatch(/código http_500|No se pudo/)
  })

  it('download() pide la instalación y pasa a downloading', async () => {
    const calls = stub()
    const { result } = renderHook(() => useDiarizationModel(true))
    await waitFor(() => {
      expect(result.current.status).toBe('missing')
    })
    act(() => {
      result.current.download()
    })
    await waitFor(() => {
      expect(result.current.status).toBe('downloading')
    })
    expect(calls.some((call) => call.startsWith('POST /api/models/diarization%3Asherpa-default/install'))).toBe(true)
  })

  it('una descarga que falló se explica y deja reintentar', async () => {
    stub({
      tasks: [
        { id: 't0', key: MODEL.key, model_id: 'sherpa-default', method: 'download', origin: null, state: 'failed', done_bytes: 0, total_bytes: 33_000_000, error_code: 'model_installation_network_error', created_at: '2026-10-01T09:00:00Z', updated_at: '2026-10-01T09:00:01Z' },
      ],
    })
    const { result } = renderHook(() => useDiarizationModel(true))
    await waitFor(() => {
      expect(result.current.status).toBe('missing')
    })
    await waitFor(() => {
      expect(result.current.error).toMatch(/revisa tu conexión/i)
    })
  })
})
