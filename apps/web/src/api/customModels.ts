import { parseErrorCode, readErrorCode } from './errors'
import { isTaskView, ModelApiError, type TaskView } from './models'

export interface CustomModelMetadata {
  engine: string
  family: string
  display_name: string
  license: string
  file_roles: Record<string, string>
}

export interface CustomModelPreview {
  id: string
  descriptor: {
    provider_id: string
    model_id: string
    display_name: string
    capabilities: string[]
    source: string | null
    revision: string | null
  }
  family: string
  license: string
  size_bytes: number
  file_count: number
}

export interface CustomModelUploadReceipt {
  id: string
  total_bytes: number
  file_count: number
}

export interface SelectedModelFile { name: string; file: File }

const BASE = '/api/models/custom'
const MAX_BYTES = 16 * 1024 ** 3
const SAFE_CODES = new Set([
  'custom_model_invalid', 'custom_model_engine_unsupported', 'custom_model_detection_ambiguous',
  'custom_model_runtime_unavailable', 'custom_model_metadata_unavailable',
  'custom_model_preview_expired', 'custom_model_upload_expired',
  'custom_model_upload_incomplete', 'custom_model_upload_limit',
  'custom_model_validation_failed', 'custom_model_validation_timeout',
  'custom_model_unavailable', 'custom_model_upload_too_large',
  'disk_space_insufficient', 'model_install_unconfirmed',
  'model_installation_cancelled', 'model_installation_failed',
  'artifact_checksum_mismatch', 'invalid_response', 'network_error', 'unknown',
])

export function customModelError(code: string | null): ModelApiError {
  return new ModelApiError(code !== null && SAFE_CODES.has(code) ? code : 'unknown')
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function positive(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 && value <= max
}

function opaque(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
}

function isPreview(value: unknown): value is CustomModelPreview {
  return record(value) && opaque(value.id) && record(value.descriptor)
    && typeof value.family === 'string' && typeof value.license === 'string'
    && positive(value.size_bytes, MAX_BYTES) && positive(value.file_count, 10_000)
    && typeof value.descriptor.provider_id === 'string'
    && typeof value.descriptor.model_id === 'string'
    && typeof value.descriptor.display_name === 'string'
    && Array.isArray(value.descriptor.capabilities)
    && value.descriptor.capabilities.every((item) => typeof item === 'string')
    && (value.descriptor.source === null || typeof value.descriptor.source === 'string')
    && (value.descriptor.revision === null || typeof value.descriptor.revision === 'string')
}

function isReceipt(value: unknown): value is CustomModelUploadReceipt {
  return record(value) && opaque(value.id) && positive(value.total_bytes, MAX_BYTES)
    && positive(value.file_count, 10_000)
}

async function call<T>(url: string, init: RequestInit, guard: (value: unknown) => value is T): Promise<T> {
  const response = await fetch(url, { ...init, headers: { Accept: 'application/json', ...init.headers } })
  const body: unknown = response.status === 204 ? undefined : await response.json().catch(() => null)
  if (!response.ok) throw customModelError(readErrorCode(body) ?? 'unknown')
  if (!guard(body)) throw customModelError('invalid_response')
  return body
}

function json(body?: unknown, signal?: AbortSignal): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    ...(signal === undefined ? {} : { signal }) }
}

export function previewCustomModel(
  request: CustomModelMetadata & { source_type: 'huggingface' | 'url'; source: string; revision: string },
  signal?: AbortSignal,
): Promise<CustomModelPreview> {
  return call(BASE + '/preview', json(request, signal), isPreview)
}

export function createCustomModelUpload(
  request: CustomModelMetadata & { files: { name: string; size_bytes: number }[] },
  signal?: AbortSignal,
): Promise<CustomModelUploadReceipt> {
  return call(BASE + '/uploads', json(request, signal), isReceipt)
}

export function previewCustomModelUpload(id: string, signal?: AbortSignal): Promise<CustomModelPreview> {
  return call(BASE + '/uploads/' + encodeURIComponent(id) + '/preview', json(undefined, signal), isPreview)
}

export function installCustomModel(previewId: string, signal?: AbortSignal): Promise<TaskView> {
  return call(BASE + '/install', json({ preview_id: previewId, confirm: true }, signal), isTaskView)
}

export function discardCustomModelUpload(id: string): Promise<void> {
  return call(BASE + '/uploads/' + encodeURIComponent(id), { method: 'DELETE' }, (value): value is undefined => value === undefined)
}

export function uploadCustomModelFile(
  id: string, index: number, file: File,
  { signal, onProgress }: { signal?: AbortSignal; onProgress?: (bytes: number) => void } = {},
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
    const xhr = new XMLHttpRequest()
    const abort = () => { xhr.abort() }
    const finish = () => { signal?.removeEventListener('abort', abort) }
    xhr.open('PUT', BASE + '/uploads/' + encodeURIComponent(id) + '/files/' + String(index))
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.min(file.size, event.loaded)) }
    xhr.onload = () => {
      finish()
      if (xhr.status === 204) { onProgress?.(file.size); resolve() }
      else reject(customModelError(parseErrorCode(xhr.responseText) ?? 'unknown'))
    }
    xhr.onerror = () => { finish(); reject(customModelError('network_error')) }
    xhr.onabort = () => { finish(); reject(new DOMException('Aborted', 'AbortError')) }
    signal?.addEventListener('abort', abort, { once: true })
    xhr.send(file)
  })
}

function safeRelative(name: string): boolean {
  return name.length > 0 && name.length <= 512 && !/[\\:]/.test(name)
    && !Array.from(name).some((character) => character.charCodeAt(0) < 32)
    && name.split('/').every((part) => part !== '' && part !== '.' && part !== '..')
}

function allowed(engine: string, name: string): boolean {
  if (engine === 'faster-whisper') return ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt', 'vocabulary.json', 'preprocessor_config.json', 'tokenizer_config.json'].includes(name)
  if (engine === 'whisper-cpp') return /^ggml-[^/]+\.bin$/.test(name)
  if (engine === 'sherpa-onnx-asr') return !name.includes('/') && (name.endsWith('.onnx') || ['tokens.txt', 'LICENSE', 'MODEL_CARD'].includes(name))
  if (name.includes('/')) return /^(espeak-ng-data|dict)\//.test(name) && (!name.split('/').at(-1)?.includes('.') || /\.(txt|dict)$/.test(name))
  return name.endsWith('.onnx') || ['tokens.txt', 'voices.bin', 'LICENSE', 'MODEL_CARD'].includes(name) || /^lexicon.*\.txt$/.test(name)
}

export function selectFolderFiles(files: readonly File[], engine: string): {
  files: SelectedModelFile[]; totalBytes: number; ignoredCount: number
} {
  if (!files.length || files.length > 10_000) throw customModelError('custom_model_invalid')
  const selected: SelectedModelFile[] = []
  const names = new Set<string>()
  let root: string | undefined
  let totalBytes = 0
  for (const file of files) {
    const parts = file.webkitRelativePath.split('/')
    const first = parts.shift()
    const name = parts.join('/')
    if (!first || !safeRelative(first) || !safeRelative(name) || (root !== undefined && root !== first)) throw customModelError('custom_model_invalid')
    root = first
    if (!allowed(engine, name) || file.size === 0) continue
    if (!positive(file.size, MAX_BYTES) || names.has(name.toLowerCase())) throw customModelError('custom_model_invalid')
    names.add(name.toLowerCase())
    totalBytes += file.size
    if (totalBytes > MAX_BYTES) throw customModelError('custom_model_invalid')
    selected.push({ name, file })
  }
  if (!selected.length) throw customModelError('custom_model_invalid')
  return { files: selected, totalBytes, ignoredCount: files.length - selected.length }
}
