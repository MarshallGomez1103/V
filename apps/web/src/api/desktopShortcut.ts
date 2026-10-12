/** `GET`/`POST`/`DELETE /api/desktop-shortcut`: acceso directo de V (si el sistema lo permite). */
import { readErrorCode } from './errors'

export interface ShortcutStatus {
  supported: boolean
  /** Está y abre V. */
  exists: boolean
  /** Está, pero apunta a algo que ya no existe (carpeta movida o borrada). */
  broken: boolean
}

export class ShortcutError extends Error {
  readonly code: string

  constructor(code: string) {
    super(code)
    this.name = 'ShortcutError'
    this.code = code
  }
}

function readStatus(value: unknown): ShortcutStatus | null {
  if (
    typeof value === 'object' &&
    value !== null &&
    'supported' in value &&
    typeof value.supported === 'boolean' &&
    'exists' in value &&
    typeof value.exists === 'boolean'
  ) {
    // Se descarta `path`: la interfaz no necesita rutas del equipo.
    const broken = 'broken' in value && value.broken === true
    return { supported: value.supported, exists: value.exists, broken }
  }
  return null
}

/** Estado del icono; `null` si el servidor no ofrece la función (la UI la oculta). */
export async function getShortcutStatus(signal?: AbortSignal): Promise<ShortcutStatus | null> {
  const response = await fetch('/api/desktop-shortcut', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) {
    return null
  }
  return readStatus(await response.json().catch(() => null))
}

/** Crea (o vuelve a crear) el icono; la cabecera evita que otra página lo dispare. */
export async function createShortcut(): Promise<ShortcutStatus> {
  const response = await fetch('/api/desktop-shortcut', {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-VOZ-Action': 'desktop-shortcut' },
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ShortcutError(readErrorCode(body) ?? 'http_' + String(response.status))
  }
  return readStatus(body) ?? { supported: true, exists: true, broken: false }
}

/** Quita el acceso directo; la cabecera propia evita que otra página lo dispare. */
export async function removeShortcut(): Promise<ShortcutStatus> {
  const response = await fetch('/api/desktop-shortcut', {
    method: 'DELETE',
    headers: { Accept: 'application/json', 'X-VOZ-Action': 'remove-desktop-shortcut' },
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ShortcutError(readErrorCode(body) ?? 'http_' + String(response.status))
  }
  return readStatus(body) ?? { supported: true, exists: false, broken: false }
}
