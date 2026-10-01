/**
 * Cliente tipado de proveedores cloud opcionales (docs/api/providers.md):
 * estado de la clave, guardar/borrar y estimación de coste. La clave solo
 * viaja en `PUT`; ninguna respuesta la devuelve jamás.
 */
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

const ERROR_MESSAGES: Record<string, string> = {
  provider_not_found: 'Ese proveedor no existe.',
  secrets_key_invalid:
    'La clave no es válida: usa de 1 a 512 caracteres ASCII visibles, sin espacios.',
  secrets_file_insecure:
    'El archivo de secretos de VOZ no es seguro (debe ser un archivo normal con permisos 0600). Corrige sus permisos y reintenta.',
  secrets_file_invalid:
    'No se pudo leer el archivo de secretos de VOZ. Revísalo o bórralo y reintenta.',
  secrets_write_failed:
    'No se pudo guardar la clave en el disco. Revisa los permisos y el espacio.',
  media_not_found: 'La grabación ya no existe.',
  media_duration_unknown: 'No se conoce la duración de la grabación.',
  invalid_response: 'La API devolvió una respuesta con formato inesperado.',
}

/** Mensaje en español por código estable; el código siempre queda visible en el fallback. */
export function messageForProviderError(code: string): string {
  return Object.hasOwn(ERROR_MESSAGES, code)
    ? (ERROR_MESSAGES[code] ?? code)
    : 'No se pudo completar la operación (código ' + code + ').'
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
