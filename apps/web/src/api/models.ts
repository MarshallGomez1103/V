/**
 * Cliente tipado del gestor de modelos (docs/api/models.md): consulta, borrado,
 * instalación (descarga/importación) y tareas. Nunca rutas del host.
 */
import { MESSAGES, type MessageKey } from '../i18n/messages'
import { translate, translateCode, type Translate } from '../i18n/i18n'
import { readErrorCode } from './errors'

export interface ExternalSource {
  origin: string
}

/** `asr` y `diarization` hoy; el backend lo declara como texto libre (síntesis llegará con otro valor). */
export type ModelKind = string

export interface ModelView {
  /** Clave de la API: "<provider_id>:<model_id>" (los ids sueltos chocan entre proveedores). */
  key: string
  provider_id: string
  kind: ModelKind
  /** Runtime que necesita para usarse ("whisper-cli", "diarization") o null. */
  requires: string | null
  runtime_available: boolean
  model_id: string
  display_name: string
  /** null en diarización: sus artefactos son assets de release verificados por SHA-256. */
  source: string | null
  revision: string | null
  license: string
  multilingual: boolean
  /** Capacidades declaradas (transcription, synthesis, diarization...); siempre vienen en la API actual. */
  capabilities?: string[]
  profile: string | null
  size_bytes: number
  installed: boolean
  disk_bytes: number | null
  reclaimable_bytes?: number | null
  shared_bytes?: number | null
  external: ExternalSource[]
}

export interface DiskUsage {
  models_bytes: number
  free_bytes: number | null
}

export interface ModelsPayload {
  models: ModelView[]
  disk: DiskUsage
  custom_engines?: string[]
}

export type TaskState =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface TaskView {
  id: string
  key: string
  model_id: string
  method: string
  origin: string | null
  state: TaskState
  done_bytes: number
  total_bytes: number
  error_code: string | null
  created_at: string
  updated_at: string
}

export type InstallMethod = 'download' | 'import'

/** Sección del Model Manager a la que pertenece un modelo, según su capacidad principal. */
export type ModelGroup = 'transcription' | 'diarization' | 'synthesis'

/** Orden de las secciones; una sección sin modelos no se muestra. */
export const MODEL_GROUPS: readonly ModelGroup[] = [
  'transcription',
  'diarization',
  'synthesis',
]

/**
 * Capacidad principal: la que decide la sección. `transcription` gana si hay duda y es
 * también el destino de un modelo sin capacidades (respuesta anterior a V6-01).
 */
export function modelGroup(model: ModelView): ModelGroup {
  const capabilities = model.capabilities ?? []
  if (capabilities.includes('transcription')) {
    return 'transcription'
  }
  if (model.kind === 'diarization' || capabilities.includes('diarization')) {
    return 'diarization'
  }
  return capabilities.includes('synthesis') ? 'synthesis' : 'transcription'
}

/** Capacidades conocidas en el orden en que se muestran: funciones primero, hardware al final. */
const CAPABILITY_ORDER: readonly string[] = [
  'transcription',
  'diarization',
  'synthesis',
  'translation',
  'language_detection',
  'word_timestamps',
  'alignment',
  'wake_word',
  'realtime',
  'cpu',
  'gpu',
]

/** Etiqueta legible de una capacidad; una desconocida (vocabulario nuevo del backend) se muestra tal cual. */
export function capabilityLabel(capability: string, t: Translate): string {
  const key = 'mm.cap.' + capability
  return Object.hasOwn(MESSAGES, key) ? t(key as MessageKey) : capability
}

/** Capacidades ordenadas y traducidas; `omit` quita la que ya da nombre a la sección. */
export function capabilityLabels(
  model: ModelView,
  t: Translate,
  omit?: string,
): string[] {
  const rank = (capability: string) => {
    const index = CAPABILITY_ORDER.indexOf(capability)
    return index === -1 ? CAPABILITY_ORDER.length : index
  }
  return (model.capabilities ?? [])
    .filter((capability) => capability !== omit)
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((capability) => capabilityLabel(capability, t))
}

export class ModelApiError extends Error {
  readonly code: string
  readonly status: number | null

  constructor(code: string, status: number | null = null) {
    super(messageForModelError(code))
    this.name = 'ModelApiError'
    this.code = code
    this.status = status
  }
}

/** Mensaje por código estable; el código siempre queda visible en el texto genérico. */
export function messageForModelError(code: string): string {
  if (Object.hasOwn(MESSAGES, 'err.model.' + code)) {
    return translateCode('err.model.', code, 'err.model.generic')
  }
  if (code.includes('checksum')) {
    return translate('err.model.checksum')
  }
  return translate('err.model.generic', { code })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === 'number'
}

function isOptionalByteCount(value: unknown): boolean {
  return value === undefined || value === null ||
    (typeof value === 'number' && Number.isFinite(value) && value >= 0)
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isModelView(value: unknown): value is ModelView {
  return (
    isRecord(value) &&
    typeof value.key === 'string' &&
    typeof value.provider_id === 'string' &&
    typeof value.kind === 'string' &&
    isNullableString(value.requires) &&
    typeof value.runtime_available === 'boolean' &&
    typeof value.model_id === 'string' &&
    typeof value.display_name === 'string' &&
    isNullableString(value.source) &&
    isNullableString(value.revision) &&
    typeof value.license === 'string' &&
    typeof value.multilingual === 'boolean' &&
    (value.capabilities === undefined ||
      (Array.isArray(value.capabilities) &&
        value.capabilities.every((item) => typeof item === 'string'))) &&
    isNullableString(value.profile) &&
    typeof value.size_bytes === 'number' &&
    typeof value.installed === 'boolean' &&
    isNullableNumber(value.disk_bytes) &&
    isOptionalByteCount(value.reclaimable_bytes) &&
    isOptionalByteCount(value.shared_bytes) &&
    Array.isArray(value.external) &&
    value.external.every(
      (entry) => isRecord(entry) && typeof entry.origin === 'string',
    )
  )
}

function isModelsPayload(value: unknown): value is ModelsPayload {
  return (
    isRecord(value) &&
    Array.isArray(value.models) &&
    value.models.every(isModelView) &&
    (value.custom_engines === undefined ||
      (Array.isArray(value.custom_engines) &&
        value.custom_engines.every((engine) => typeof engine === 'string'))) &&
    isRecord(value.disk) &&
    typeof value.disk.models_bytes === 'number' &&
    isNullableNumber(value.disk.free_bytes)
  )
}

const TASK_STATES: readonly string[] = [
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
]

export function isTaskView(value: unknown): value is TaskView {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.key === 'string' &&
    typeof value.model_id === 'string' &&
    typeof value.method === 'string' &&
    (value.origin === null || typeof value.origin === 'string') &&
    typeof value.state === 'string' &&
    TASK_STATES.includes(value.state) &&
    typeof value.done_bytes === 'number' &&
    typeof value.total_bytes === 'number' &&
    (value.error_code === null || typeof value.error_code === 'string') &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  )
}

function isTaskList(value: unknown): value is { tasks: TaskView[] } {
  return (
    isRecord(value) && Array.isArray(value.tasks) && value.tasks.every(isTaskView)
  )
}

async function call<T>(
  url: string,
  init: RequestInit,
  guard: (value: unknown) => value is T,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ModelApiError(
      readErrorCode(body) ?? 'http_' + String(response.status),
      response.status,
    )
  }
  if (!guard(body)) {
    throw new ModelApiError('invalid_response', response.status)
  }
  return body
}

const isDeleteResult = (
  value: unknown,
): value is { key: string; model_id: string; freed_bytes: number } =>
  isRecord(value) &&
  typeof value.key === 'string' &&
  typeof value.model_id === 'string' &&
  typeof value.freed_bytes === 'number'

export function getModels(signal?: AbortSignal): Promise<ModelsPayload> {
  return call('/api/models', signal ? { signal } : {}, isModelsPayload)
}

/** `key` es la clave "<proveedor>:<modelo>"; `confirm` repite exactamente lo enviado en la ruta. */
export function deleteModel(key: string): Promise<{ freed_bytes: number }> {
  const id = encodeURIComponent(key)
  return call(
    '/api/models/' + id + '?confirm=' + id,
    { method: 'DELETE' },
    isDeleteResult,
  )
}

/** Descarga (HuggingFace) o copia local (origen buzz en la API); el backend la ejecuta como tarea. */
export function installModel(
  key: string,
  method: InstallMethod,
): Promise<TaskView> {
  const body =
    method === 'import'
      ? { method, origin: 'buzz', confirm: true }
      : { method, confirm: true }
  return call(
    '/api/models/' + encodeURIComponent(key) + '/install',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    isTaskView,
  )
}

export async function listModelTasks(signal?: AbortSignal): Promise<TaskView[]> {
  const payload = await call(
    '/api/model-tasks',
    signal ? { signal } : {},
    isTaskList,
  )
  return payload.tasks
}

export function cancelModelTask(taskId: string): Promise<TaskView> {
  return call(
    '/api/model-tasks/' + encodeURIComponent(taskId) + '/cancel',
    { method: 'POST' },
    isTaskView,
  )
}
