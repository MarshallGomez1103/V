/** `POST /api/shutdown`: apaga el servidor local (la cabecera exige el valor exacto). */
import { readErrorCode } from './errors'

export class ShutdownError extends Error {
  readonly code: string

  constructor(code: string) {
    super(code)
    this.name = 'ShutdownError'
    this.code = code
  }
}

const CHECK_DELAY_MS = 700

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms)
  })

/** Si el servidor ya no responde, el cierre funcionó aunque la respuesta se perdiera. */
async function serverIsGone(): Promise<boolean> {
  await sleep(CHECK_DELAY_MS)
  try {
    await fetch('/api/health', { cache: 'no-store' })
    return false
  } catch {
    return true
  }
}

/** Resuelve cuando el servidor aceptó apagarse (202) o dejó de responder. */
export async function shutdownServer(): Promise<void> {
  let response: Response
  try {
    response = await fetch('/api/shutdown', {
      method: 'POST',
      headers: { Accept: 'application/json', 'X-VOZ-Action': 'shutdown' },
    })
  } catch {
    if (await serverIsGone()) {
      return
    }
    throw new ShutdownError('network_error')
  }
  if (response.ok) {
    return
  }
  const body: unknown = await response.json().catch(() => null)
  throw new ShutdownError(readErrorCode(body) ?? 'http_' + String(response.status))
}
