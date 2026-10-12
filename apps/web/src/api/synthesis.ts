/**
 * Cliente tipado de la síntesis de voz (docs/api/synthesis.md): opciones, crear,
 * consultar, cancelar, listar y borrar. El audio se direcciona por id de trabajo,
 * nunca por rutas del host. El progreso llega por SSE (`subscribeSynthesisEvents`).
 */
import { MESSAGES } from '../i18n/messages'
import { translate, translateCode } from '../i18n/i18n'
import { readErrorCode } from './errors'

export interface SynthesisProvider {
  provider_id: string
  display_name: string
  locality: string
}

export interface SynthesisVoice {
  id: string
  name: string
  languages: string[]
}

export interface SynthesisModel {
  provider_id: string
  model_id: string
  display_name: string
  runtime_ready: boolean
  languages: string[]
  voices: SynthesisVoice[]
}

export interface SynthesisOptions {
  providers: SynthesisProvider[]
  models: SynthesisModel[]
  /** Límite de texto tras recortar espacios. */
  max_chars: number
  speed: { min: number; max: number }
}

export const SYNTHESIS_STATES = [
  'QUEUED',
  'RUNNING',
  'PERSISTING',
  'COMPLETED',
  'FAILED',
  'CANCELLING',
  'CANCELLED',
] as const

export type SynthesisState = (typeof SYNTHESIS_STATES)[number]

/** Estados en los que el trabajo sigue vivo (hay que cancelarlo antes de borrarlo). */
export const ACTIVE_SYNTHESIS_STATES: ReadonlySet<SynthesisState> = new Set<SynthesisState>([
  'QUEUED',
  'RUNNING',
  'PERSISTING',
  'CANCELLING',
])

export interface SynthesisAudio {
  duration_ms: number
  sample_rate: number
  size_bytes: number
  url: string
}

export interface SynthesisView {
  id: string
  state: SynthesisState
  progress: number
  chunks_done: number
  chunks_total: number
  error_code: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  provider_id: string
  model_id: string
  voice_id: string
  language: string | null
  speed: number
  text_length: number
  text_preview: string
  /** Solo con el trabajo `COMPLETED`. */
  audio: SynthesisAudio | null
  /** Texto completo: solo en `GET /api/synthesis/{id}`. */
  text?: string
}

export type CreatedSynthesis = SynthesisView & { reused: boolean }

export interface CreateSynthesisInput {
  text: string
  provider_id: string
  model_id: string
  voice_id: string
  language?: string | null
  speed?: number
}

export class SynthesisApiError extends Error {
  readonly code: string
  readonly status: number | null

  constructor(code: string, status: number | null = null) {
    super(messageForSynthesisError(code))
    this.name = 'SynthesisApiError'
    this.code = code
    this.status = status
  }
}

/** Mensaje por código estable; el código siempre queda visible en el texto genérico. */
export function messageForSynthesisError(code: string): string {
  return Object.hasOwn(MESSAGES, 'err.synth.' + code)
    ? translateCode('err.synth.', code, 'err.synth.generic')
    : translate('err.synth.generic', { code })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

const isString = (value: unknown): value is string => typeof value === 'string'
const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const isNullableString = (value: unknown): value is string | null =>
  value === null || isString(value)
const isStringList = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString)

function isProvider(value: unknown): value is SynthesisProvider {
  return (
    isRecord(value) &&
    isString(value.provider_id) &&
    isString(value.display_name) &&
    isString(value.locality)
  )
}

function isVoice(value: unknown): value is SynthesisVoice {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isStringList(value.languages)
  )
}

function isModel(value: unknown): value is SynthesisModel {
  return (
    isRecord(value) &&
    isString(value.provider_id) &&
    isString(value.model_id) &&
    isString(value.display_name) &&
    typeof value.runtime_ready === 'boolean' &&
    isStringList(value.languages) &&
    Array.isArray(value.voices) &&
    value.voices.every(isVoice)
  )
}

function isOptions(value: unknown): value is SynthesisOptions {
  return (
    isRecord(value) &&
    Array.isArray(value.providers) &&
    value.providers.every(isProvider) &&
    Array.isArray(value.models) &&
    value.models.every(isModel) &&
    isNumber(value.max_chars) &&
    value.max_chars > 0 &&
    isRecord(value.speed) &&
    isNumber(value.speed.min) &&
    isNumber(value.speed.max)
  )
}

function isAudio(value: unknown): value is SynthesisAudio {
  return (
    isRecord(value) &&
    isNumber(value.duration_ms) &&
    isNumber(value.sample_rate) &&
    isNumber(value.size_bytes) &&
    isString(value.url)
  )
}

export function isSynthesisView(value: unknown): value is SynthesisView {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.state) &&
    (SYNTHESIS_STATES as readonly string[]).includes(value.state) &&
    isNumber(value.progress) &&
    isNumber(value.chunks_done) &&
    isNumber(value.chunks_total) &&
    isNullableString(value.error_code) &&
    isString(value.created_at) &&
    isString(value.updated_at) &&
    (value.started_at === undefined || isNullableString(value.started_at)) &&
    isString(value.provider_id) &&
    isString(value.model_id) &&
    isString(value.voice_id) &&
    (value.language === undefined || isNullableString(value.language)) &&
    isNumber(value.speed) &&
    isNumber(value.text_length) &&
    isString(value.text_preview) &&
    (value.audio === undefined || value.audio === null || isAudio(value.audio)) &&
    (value.text === undefined || isString(value.text))
  )
}

function isCreated(value: unknown): value is CreatedSynthesis {
  return isSynthesisView(value) && typeof (value as { reused?: unknown }).reused === 'boolean'
}

function isList(value: unknown): value is { items: SynthesisView[] } {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isSynthesisView)
}

/** Rellena los campos opcionales que el backend puede omitir, para que el resto de la UI no mire `undefined`. */
function normalize<T extends SynthesisView>(view: T): T {
  return {
    ...view,
    started_at: view.started_at ?? null,
    language: view.language ?? null,
    audio: view.audio ?? null,
  }
}

async function send(url: string, init: RequestInit): Promise<{ response: Response; body: unknown }> {
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new SynthesisApiError('network_error')
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new SynthesisApiError(
      readErrorCode(body) ?? 'http_' + String(response.status),
      response.status,
    )
  }
  return { response, body }
}

async function call<T>(
  url: string,
  init: RequestInit,
  guard: (value: unknown) => value is T,
): Promise<T> {
  const { response, body } = await send(url, init)
  if (!guard(body)) {
    throw new SynthesisApiError('invalid_response', response.status)
  }
  return body
}

const withSignal = (signal?: AbortSignal): RequestInit => (signal ? { signal } : {})

export function getSynthesisOptions(signal?: AbortSignal): Promise<SynthesisOptions> {
  return call('/api/synthesis/options', withSignal(signal), isOptions)
}

export async function createSynthesis(input: CreateSynthesisInput): Promise<CreatedSynthesis> {
  return normalize(
    await call(
      '/api/synthesis',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      },
      isCreated,
    ),
  )
}

export async function getSynthesis(id: string, signal?: AbortSignal): Promise<SynthesisView> {
  return normalize(
    await call('/api/synthesis/' + encodeURIComponent(id), withSignal(signal), isSynthesisView),
  )
}

export async function cancelSynthesis(id: string): Promise<SynthesisView> {
  return normalize(
    await call(
      '/api/synthesis/' + encodeURIComponent(id) + '/cancel',
      { method: 'POST' },
      isSynthesisView,
    ),
  )
}

/** Más recientes primero; el backend limita `limit` a 1–200 (50 por defecto). */
export async function listSynthesis(limit?: number, signal?: AbortSignal): Promise<SynthesisView[]> {
  const query = limit === undefined ? '' : '?limit=' + String(limit)
  const payload = await call('/api/synthesis' + query, withSignal(signal), isList)
  return payload.items.map(normalize)
}

/** Borra el WAV y los registros; un trabajo activo debe cancelarse antes (409). */
export async function deleteSynthesis(id: string): Promise<void> {
  await send('/api/synthesis/' + encodeURIComponent(id), {
    method: 'DELETE',
    headers: { 'X-VOZ-Action': 'delete-synthesis' },
  })
}

/** URL del WAV de un trabajo terminado (`download` fuerza `attachment`). */
export function synthesisAudioUrl(id: string, download = false): string {
  return '/api/synthesis/' + encodeURIComponent(id) + '/audio' + (download ? '?download=true' : '')
}

export interface SynthesisEventHandlers {
  onJob(view: SynthesisView): void
  onEnd(): void
  onError(error: SynthesisApiError): void
}

function parseSynthesisView(event: Event): SynthesisView | null {
  if (!(event instanceof MessageEvent)) {
    return null
  }
  const raw: unknown = event.data
  try {
    const parsed: unknown = typeof raw === 'string' ? JSON.parse(raw) : raw
    return isSynthesisView(parsed) ? normalize(parsed) : null
  } catch {
    return null
  }
}

/**
 * Sigue `GET /api/synthesis/{id}/events` y devuelve la función que lo cierra.
 * El stream se cierra solo con `end`; el navegador reconecta ante cortes
 * transitorios, así que solo un stream cerrado del todo se reporta como error.
 */
export function subscribeSynthesisEvents(
  id: string,
  handlers: SynthesisEventHandlers,
): () => void {
  const source = new EventSource('/api/synthesis/' + encodeURIComponent(id) + '/events')
  let active = true
  const stop = () => {
    if (active) {
      active = false
      source.close()
    }
  }
  source.addEventListener('job', (event) => {
    if (!active) {
      return
    }
    const view = parseSynthesisView(event)
    if (view === null) {
      handlers.onError(new SynthesisApiError('events_invalid'))
      return
    }
    handlers.onJob(view)
  })
  source.addEventListener('end', () => {
    if (active) {
      stop()
      handlers.onEnd()
    }
  })
  source.addEventListener('error', () => {
    if (active && source.readyState === EventSource.CLOSED) {
      active = false
      handlers.onError(new SynthesisApiError('events_lost'))
    }
  })
  return stop
}
