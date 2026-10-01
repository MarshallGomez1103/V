/**
 * Cliente tipado del gestor de modelos (docs/api/models.md): consulta, borrado,
 * instalación (descarga/importación) y tareas. Nunca rutas del host.
 */
import { readErrorCode } from './errors'

export interface ExternalSource {
  origin: string
}

export type ModelKind = 'asr' | 'diarization'

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
  profile: string | null
  size_bytes: number
  installed: boolean
  disk_bytes: number | null
  external: ExternalSource[]
}

export interface DiskUsage {
  models_bytes: number
  free_bytes: number | null
}

export interface ModelsPayload {
  models: ModelView[]
  disk: DiskUsage
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

const ERROR_MESSAGES: Record<string, string> = {
  disk_space_insufficient:
    'No hay espacio libre suficiente en el disco. Libera espacio y vuelve a intentarlo.',
  model_installation_network_error:
    'No se pudo conectar para descargar el modelo. Revisa tu conexión a Internet y reintenta.',
  model_installation_http_error:
    'El servidor de descarga respondió con un error. Inténtalo de nuevo más tarde.',
  model_installation_download_failed:
    'La descarga del modelo falló. Inténtalo de nuevo.',
  model_installation_io_error:
    'No se pudo escribir el modelo en el disco. Revisa los permisos y el espacio.',
  model_installation_invalid_snapshot:
    'Los archivos recibidos no corresponden al modelo esperado. Reintenta la instalación.',
  model_installation_cancelled: 'La instalación fue cancelada.',
  model_install_unconfirmed: 'Falta confirmar la instalación del modelo.',
  model_unknown: 'Ese modelo no está en el catálogo.',
  model_already_installed: 'Ese modelo ya está instalado.',
  external_model_not_found:
    'Buzz ya no tiene este modelo. Descárgalo desde HuggingFace.',
  model_task_terminal: 'La tarea ya había terminado.',
  model_task_not_found: 'La tarea ya no existe.',
  model_delete_unconfirmed: 'Falta confirmar el borrado del modelo.',
  model_not_installed: 'Ese modelo no está instalado.',
  model_in_use:
    'El modelo está en uso por una transcripción en curso. Espera a que termine o cancélala y vuelve a intentarlo.',
  model_remove_failed: 'No se pudo borrar el modelo por un error de disco.',
  model_task_failed: 'La tarea de instalación falló.',
  invalid_response: 'La API devolvió una respuesta con formato inesperado.',
}

/** Mensaje en español por código estable; el código siempre queda visible en el fallback. */
export function messageForModelError(code: string): string {
  if (Object.hasOwn(ERROR_MESSAGES, code)) {
    return ERROR_MESSAGES[code] ?? code
  }
  if (code.includes('checksum')) {
    return 'Un archivo descargado no coincide con su suma de verificación (checksum). Se descartó; reintenta la descarga.'
  }
  return 'No se pudo completar la operación (código ' + code + ').'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === 'number'
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isModelView(value: unknown): value is ModelView {
  return (
    isRecord(value) &&
    typeof value.key === 'string' &&
    typeof value.provider_id === 'string' &&
    (value.kind === 'asr' || value.kind === 'diarization') &&
    isNullableString(value.requires) &&
    typeof value.runtime_available === 'boolean' &&
    typeof value.model_id === 'string' &&
    typeof value.display_name === 'string' &&
    isNullableString(value.source) &&
    isNullableString(value.revision) &&
    typeof value.license === 'string' &&
    typeof value.multilingual === 'boolean' &&
    isNullableString(value.profile) &&
    typeof value.size_bytes === 'number' &&
    typeof value.installed === 'boolean' &&
    isNullableNumber(value.disk_bytes) &&
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

/** Descarga (HuggingFace) o importación desde Buzz; el backend la ejecuta como tarea. */
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
