import type { MessageKey } from '../i18n/messages'

/**
 * Rutas por hash, sin librería: `#/` Home, `#/nueva`, `#/t/<jobId>` (espacio de trabajo),
 * `#/modelos`, `#/proveedores`. El hash entra en el historial del navegador, así que
 * Atrás/Adelante y recargar funcionan sin código extra.
 */
export type Route =
  | { name: 'home' }
  | { name: 'nueva' }
  | { name: 'trabajo'; jobId: string }
  | { name: 'modelos' }
  | { name: 'proveedores' }

export type RouteName = Route['name']

export const HOME: Route = { name: 'home' }

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'nueva':
      return '#/nueva'
    case 'trabajo':
      return '#/t/' + encodeURIComponent(route.jobId)
    case 'modelos':
      return '#/modelos'
    case 'proveedores':
      return '#/proveedores'
  }
}

/** Hash → ruta. Lo desconocido y el hash vacío caen en Home; `#transcribir` (v2) en Nueva. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '').replace(/\/+$/, '')
  if (path === '') {
    return HOME
  }
  const [head = '', ...rest] = path.split('/')
  if (head === 't') {
    const raw = rest.join('/')
    try {
      const jobId = decodeURIComponent(raw)
      return jobId === '' ? HOME : { name: 'trabajo', jobId }
    } catch {
      return HOME
    }
  }
  if (rest.length > 0) {
    return HOME
  }
  switch (head) {
    case 'nueva':
    case 'transcribir':
      return { name: 'nueva' }
    case 'modelos':
      return { name: 'modelos' }
    case 'proveedores':
      return { name: 'proveedores' }
    default:
      return HOME
  }
}

export function sameRoute(a: Route, b: Route): boolean {
  return routeToHash(a) === routeToHash(b)
}

/** Entradas de la navegación superior (el espacio de trabajo cuelga de Inicio). */
export const NAV_ITEMS: readonly { route: Route; label: MessageKey }[] = [
  { route: HOME, label: 'nav.inicio' },
  { route: { name: 'nueva' }, label: 'nav.transcribir' },
  { route: { name: 'modelos' }, label: 'nav.modelos' },
  { route: { name: 'proveedores' }, label: 'nav.proveedores' },
]

/** ¿Esta entrada del menú es la sección actual? */
export function isCurrent(item: Route, current: Route): boolean {
  return item.name === current.name || (item.name === 'home' && current.name === 'trabajo')
}
