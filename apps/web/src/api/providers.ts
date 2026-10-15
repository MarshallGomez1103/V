/**
 * Cliente tipado de proveedores cloud opcionales (docs/api/providers.md):
 * estado de la clave, guardar/borrar y estimación de coste. La clave solo
 * viaja en `PUT`; ninguna respuesta la devuelve jamás.
 */
import { translateCode } from '../i18n/i18n'
import { readErrorCode } from './errors'

export interface ProviderView {
  id: string
  /** Nombre visible; lo decide el backend. */
  label: string
  /** Política de privacidad del proveedor, si el backend la conoce. */
  privacy_url: string | null
  configured: boolean
  cloud: boolean
}

export interface CloudEstimate {
  minutes: number
  usd: number
  price_source: string
  price_date: string
}

/** Mensaje por código estable; el código siempre queda visible en el texto genérico. */
export function messageForProviderError(code: string): string {
  return translateCode('err.provider.', code, 'err.provider.generic')
}

export class ProviderApiError extends Error {
  readonly code: string
  readonly status: number | null

  constructor(code: string, status: number | null = null) {
    super(messageForProviderError(code))
    this.name = 'ProviderApiError'
    this.code = code
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isProviderList(value: unknown): value is ProviderView[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        isRecord(item) &&
        typeof item.id === 'string' &&
        typeof item.label === 'string' &&
        (item.privacy_url === null || typeof item.privacy_url === 'string') &&
        typeof item.configured === 'boolean' &&
        typeof item.cloud === 'boolean',
    )
  )
}

function isCloudEstimate(value: unknown): value is CloudEstimate {
  return (
    isRecord(value) &&
    typeof value.minutes === 'number' &&
    typeof value.usd === 'number' &&
    typeof value.price_source === 'string' &&
    typeof value.price_date === 'string'
  )
}

async function request(url: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(url, {
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
  })
  if (response.status === 204) {
    return null
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ProviderApiError(
      readErrorCode(body) ?? 'http_' + String(response.status),
      response.status,
    )
  }
  return body
}

function providerUrl(providerId: string, suffix: string): string {
  return '/api/providers/' + encodeURIComponent(providerId) + suffix
}

export async function listProviders(
  signal?: AbortSignal,
): Promise<ProviderView[]> {
  const body = await request('/api/providers', signal ? { signal } : {})
  if (!isProviderList(body)) {
    throw new ProviderApiError('invalid_response')
  }
  return body
}

/** La clave va solo en el cuerpo del PUT; la API responde 204 sin eco. */
export async function saveProviderKey(
  providerId: string,
  key: string,
): Promise<void> {
  await request(providerUrl(providerId, '/key'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  })
}

export async function deleteProviderKey(providerId: string): Promise<void> {
  await request(providerUrl(providerId, '/key'), { method: 'DELETE' })
}

export async function getEstimate(
  providerId: string,
  mediaAssetId: string,
  model?: string,
  signal?: AbortSignal,
): Promise<CloudEstimate> {
  const query = new URLSearchParams({ media_asset_id: mediaAssetId })
  if (model) {
    query.set('model', model)
  }
  const body = await request(
    providerUrl(providerId, '/estimate?' + query.toString()),
    signal ? { signal } : {},
  )
  if (!isCloudEstimate(body)) {
    throw new ProviderApiError('invalid_response')
  }
  return body
}

/* --- Servidores compatibles con OpenAI (V4-04) ----------------------------- */

export interface CompatibleEndpoint {
  id: string
  name: string
  base_url: string
  /** Fuera de loopback: el audio y el texto salen del equipo. */
  cloud: boolean
  cloud_consent: boolean
  key_configured: boolean
  stt_models: string[]
  tts_models: string[]
  tts_voices: string[]
}

export interface CompatibleEndpointInput {
  name: string
  base_url: string
  /** `null` conserva la clave guardada; un texto la reemplaza. */
  key: string | null
  clear_key?: boolean
  stt_models: string[]
  tts_models: string[]
  tts_voices: string[]
  cloud_consent: boolean
}

export interface ConnectionCheck {
  reachable: boolean
  status: number | null
  models: string[]
  code: string | null
}

const ENDPOINTS_URL = '/api/providers/compatible'

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isEndpoint(value: unknown): value is CompatibleEndpoint {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.base_url === 'string' &&
    typeof value.cloud === 'boolean' &&
    typeof value.cloud_consent === 'boolean' &&
    typeof value.key_configured === 'boolean' &&
    isStringList(value.stt_models) &&
    isStringList(value.tts_models) &&
    isStringList(value.tts_voices)
  )
}

function isConnectionCheck(value: unknown): value is ConnectionCheck {
  return (
    isRecord(value) &&
    typeof value.reachable === 'boolean' &&
    (value.status === null || typeof value.status === 'number') &&
    isStringList(value.models) &&
    (value.code === null || typeof value.code === 'string')
  )
}

/** Misma regla que el backend: solo localhost, 127.0.0.0/8 y ::1 son locales. */
export function isLoopbackUrl(value: string): boolean {
  let host: string
  try {
    host = new URL(value.trim()).hostname
  } catch {
    return false
  }
  return (
    host === 'localhost' ||
    host === '[::1]' ||
    /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host)
  )
}

export async function listCompatibleEndpoints(
  signal?: AbortSignal,
): Promise<CompatibleEndpoint[]> {
  const body = await request(ENDPOINTS_URL, signal ? { signal } : {})
  if (!Array.isArray(body) || !body.every(isEndpoint)) {
    throw new ProviderApiError('invalid_response')
  }
  return body
}

/** Crea (sin `id`) o reemplaza un servidor; la clave nunca vuelve en la respuesta. */
export async function saveCompatibleEndpoint(
  input: CompatibleEndpointInput,
  id?: string,
): Promise<CompatibleEndpoint> {
  const body = await request(
    id === undefined ? ENDPOINTS_URL : ENDPOINTS_URL + '/' + encodeURIComponent(id),
    {
      method: id === undefined ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  )
  if (!isEndpoint(body)) {
    throw new ProviderApiError('invalid_response')
  }
  return body
}

export async function deleteCompatibleEndpoint(id: string): Promise<void> {
  await request(ENDPOINTS_URL + '/' + encodeURIComponent(id), {
    method: 'DELETE',
    headers: { 'X-VOZ-Action': 'delete-compatible-endpoint' },
  })
}

export async function testCompatibleEndpoint(id: string): Promise<ConnectionCheck> {
  const body = await request(ENDPOINTS_URL + '/' + encodeURIComponent(id) + '/test', {
    method: 'POST',
  })
  if (!isConnectionCheck(body)) {
    throw new ProviderApiError('invalid_response')
  }
  return body
}
