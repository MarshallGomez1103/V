import { describe, expect, it } from 'vitest'

import { isCurrent, NAV_ITEMS, parseRoute, routeToHash, type Route } from './navigation'

describe('rutas por hash', () => {
  it('el hash vacío y desconocido llevan a Home', () => {
    for (const hash of ['', '#', '#/', '#/nada', '#/modelos/x', '#/t/', '#/t']) {
      expect(parseRoute(hash)).toEqual({ name: 'home' })
    }
  })

  it('reconoce las rutas de la app y el hash antiguo de Transcribir', () => {
    expect(parseRoute('#/nueva')).toEqual({ name: 'nueva' })
    expect(parseRoute('#transcribir')).toEqual({ name: 'nueva' })
    expect(parseRoute('#/modelos')).toEqual({ name: 'modelos' })
    expect(parseRoute('#modelos')).toEqual({ name: 'modelos' })
    expect(parseRoute('#/proveedores')).toEqual({ name: 'proveedores' })
  })

  it('#/t/<id> abre un trabajo y decodifica el id', () => {
    expect(parseRoute('#/t/job-1')).toEqual({ name: 'trabajo', jobId: 'job-1' })
    expect(parseRoute('#/t/a%20b')).toEqual({ name: 'trabajo', jobId: 'a b' })
    expect(parseRoute('#/t/%E0%A4%A')).toEqual({ name: 'home' })
  })

  it('ida y vuelta hash ↔ ruta', () => {
    const routes: Route[] = [
      { name: 'home' },
      { name: 'nueva' },
      { name: 'trabajo', jobId: 'x/y z' },
      { name: 'modelos' },
      { name: 'proveedores' },
    ]
    for (const route of routes) {
      expect(parseRoute(routeToHash(route))).toEqual(route)
    }
  })

  it('un trabajo cuenta como la sección Inicio', () => {
    const inicio = NAV_ITEMS[0]?.route as Route
    expect(isCurrent(inicio, { name: 'trabajo', jobId: 'j' })).toBe(true)
    expect(isCurrent({ name: 'modelos' }, { name: 'trabajo', jobId: 'j' })).toBe(false)
  })
})
