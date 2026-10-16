import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createCustomModelUpload, discardCustomModelUpload, installCustomModel,
  previewCustomModel, previewCustomModelUpload, selectFolderFiles,
  uploadCustomModelFile,
} from './customModels'

afterEach(() => { vi.unstubAllGlobals() })

const ID = 'a'.repeat(32)
const METADATA = { engine: 'faster-whisper', family: 'ctranslate2', display_name: 'My model', license: 'MIT', file_roles: {} }
const PREVIEW = {
  id: ID, family: 'ctranslate2', license: 'User-declared: MIT', size_bytes: 4, file_count: 1,
  descriptor: { provider_id: 'faster-whisper', model_id: 'custom-' + ID, display_name: 'My model', capabilities: ['transcription'], source: null, revision: null },
}

function response(status: number, body?: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as Response
}

function folderFile(path: string, contents = 'abcd'): File {
  const file = new File([contents], path.split('/').at(-1) ?? 'file')
  Object.defineProperty(file, 'webkitRelativePath', { value: path })
  return file
}

describe('custom model client', () => {
  it('selects only top-level ASR ONNX weights and tokens from the explorer', () => {
    const selected = selectFolderFiles([
      folderFile('Private folder/tiny-encoder.int8.onnx'),
      folderFile('Private folder/tiny-decoder.onnx'),
      folderFile('Private folder/tokens.txt'),
      folderFile('Private folder/voices.bin'),
      folderFile('Private folder/lexicon.txt'),
      folderFile('Private folder/dict/words.txt'),
      folderFile('Private folder/model.py'),
    ], 'sherpa-onnx-asr')
    expect(selected.files.map(({ name }) => name)).toEqual([
      'tiny-encoder.int8.onnx', 'tiny-decoder.onnx', 'tokens.txt',
    ])
    expect(selected.ignoredCount).toBe(4)
  })

  it('sends only folder-relative names and explicit metadata', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(201, { id: ID, total_bytes: 4, file_count: 1 }))
    vi.stubGlobal('fetch', request)
    const selected = selectFolderFiles([folderFile('Private folder/model.bin'), folderFile('Private folder/README.md')], 'faster-whisper')
    expect(selected.files.map((file) => file.name)).toEqual(['model.bin'])
    expect(selected.totalBytes).toBe(4)
    expect(selected.ignoredCount).toBe(1)
    await createCustomModelUpload({ ...METADATA, files: selected.files.map(({ name, file }) => ({ name, size_bytes: file.size })) })
    const encoded = request.mock.calls[0]?.[1]?.body
    if (typeof encoded !== 'string') throw new Error('Expected JSON body')
    const body: unknown = JSON.parse(encoded)
    expect(body).toEqual({ ...METADATA, files: [{ name: 'model.bin', size_bytes: 4 }] })
    expect(JSON.stringify(body)).not.toContain('Private folder')
  })

  it.each(['root/../model.bin', '/model.bin', 'root/C:/model.bin', 'root/a\\model.bin'])('rejects unsafe browser relative paths %s', (path) => {
    expect(() => selectFolderFiles([folderFile(path)], 'faster-whisper')).toThrow()
  })

  it('rejects duplicate names, inconsistent roots and excessive sizes', () => {
    expect(() => selectFolderFiles([folderFile('root/model.bin'), folderFile('root/model.bin')], 'faster-whisper')).toThrow()
    expect(() => selectFolderFiles([folderFile('one/model.bin'), folderFile('two/config.json')], 'faster-whisper')).toThrow()
    const huge = folderFile('root/model.bin')
    Object.defineProperty(huge, 'size', { value: 16 * 1024**3 + 1 })
    expect(() => selectFolderFiles([huge], 'faster-whisper')).toThrow()
  })

  it('previews remote metadata without installing or downloading weights', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(200, PREVIEW))
    vi.stubGlobal('fetch', request)
    await expect(previewCustomModel({ ...METADATA, source_type: 'huggingface', source: 'org/repo', revision: 'main' })).resolves.toEqual(PREVIEW)
    expect(request).toHaveBeenCalledTimes(1)
    expect(request.mock.calls[0]?.[0]).toBe('/api/models/custom/preview')
  })

  it('previews upload with no source path and deletes with 204', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(response(200, PREVIEW)).mockResolvedValueOnce(response(204))
    vi.stubGlobal('fetch', request)
    await previewCustomModelUpload(ID)
    await discardCustomModelUpload(ID)
    expect(request.mock.calls.map((call) => call[0])).toEqual(['/api/models/custom/uploads/' + ID + '/preview', '/api/models/custom/uploads/' + ID])
  })

  it('installs only a confirmed preview through the existing job API', async () => {
    const task = { id: 'job', key: 'faster-whisper:custom', model_id: 'custom', method: 'custom', origin: null, state: 'queued', done_bytes: 0, total_bytes: 4, error_code: null, created_at: '', updated_at: '' }
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(202, task))
    vi.stubGlobal('fetch', request)
    await expect(installCustomModel(ID)).resolves.toEqual(task)
    expect(request.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ preview_id: ID, confirm: true }))
  })

  it.each(['custom_model_invalid', '/private/secret-token', 'secret\npath'])('does not display raw error messages or unsafe error codes %s', async (code) => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(response(422, { detail: { code, message: '/private/token raw error' } })))
    await expect(previewCustomModelUpload(ID)).rejects.toThrow('custom_model_invalid' === code ? 'custom_model_invalid' : 'unknown')
    await expect(previewCustomModelUpload(ID)).rejects.not.toThrow('/private')
  })

  it('rejects malformed previews, receipts and task responses', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(response(200, { ...PREVIEW, size_bytes: -1 })))
    await expect(previewCustomModelUpload(ID)).rejects.toMatchObject({ code: 'invalid_response' })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(response(201, { id: '/private', total_bytes: 4, file_count: 1 })))
    await expect(createCustomModelUpload({ ...METADATA, files: [] })).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('uploads raw bytes with progress and aborts the XHR', async () => {
    const instances: FakeXhr[] = []
    class FakeXhr {
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null }
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      onabort: (() => void) | null = null
      ontimeout: (() => void) | null = null
      status = 204
      responseText = ''
      timeout = 0
      open = vi.fn()
      setRequestHeader = vi.fn()
      send = vi.fn()
      abort() { this.onabort?.() }
      constructor() { instances.push(this) }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    const controller = new AbortController()
    const progress = vi.fn()
    const pending = uploadCustomModelFile(ID, 0, new File(['abcd'], 'model.bin'), { signal: controller.signal, onProgress: progress })
    const xhr = instances[0]
    if (!xhr) throw new Error('Expected upload request')
    expect(xhr.open).toHaveBeenCalledWith('PUT', '/api/models/custom/uploads/' + ID + '/files/0')
    expect(xhr.setRequestHeader).toHaveBeenCalledWith('Content-Type', 'application/octet-stream')
    xhr.upload.onprogress?.(new ProgressEvent('progress', { lengthComputable: true, loaded: 2, total: 4 }))
    expect(progress).toHaveBeenCalledWith(2)
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
})
