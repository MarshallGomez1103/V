import { describe, expect, it } from 'vitest'

import { buildSearchIndex, findMatches } from './segmentSearch'

function highlighted(text: string, query: string): string[] {
  return findMatches(text, query).map((range) => text.slice(range.start, range.end))
}

describe('findMatches', () => {
  it('ignora mayúsculas y devuelve el texto original', () => {
    expect(highlighted('Hola HOLA hola', 'HoLa')).toEqual(['Hola', 'HOLA', 'hola'])
  })

  it('ignora tildes en ambos sentidos', () => {
    expect(highlighted('La canción de Ángel', 'cancion')).toEqual(['canción'])
    expect(highlighted('La cancion de angel', 'ÁNGEL')).toEqual(['angel'])
  })

  it('conserva los índices originales aunque haya tildes antes', () => {
    const text = 'Él dijo: ¡Sí, señor! sí.'
    expect(findMatches(text, 'si')).toEqual([
      { start: 10, end: 12 },
      { start: 21, end: 23 },
    ])
  })

  it('trata texto ya descompuesto (NFD) incluyendo su marca', () => {
    const text = 'canción'
    expect(highlighted(text, 'cancion')).toEqual([text])
    expect(highlighted('Canción', 'canción')).toEqual(['Canción'])
  })

  it('no solapa coincidencias', () => {
    expect(findMatches('aaaa', 'aa')).toEqual([
      { start: 0, end: 2 },
      { start: 2, end: 4 },
    ])
  })

  it('consulta vacía o en blanco no coincide; se recorta el espacio', () => {
    expect(findMatches('hola', '')).toEqual([])
    expect(findMatches('hola', '   ')).toEqual([])
    expect(highlighted('hola mundo', ' mundo ')).toEqual(['mundo'])
  })

  it('no rompe pares sustitutos (emoji)', () => {
    const text = 'a 😀 b'
    expect(highlighted(text, 'b')).toEqual(['b'])
    expect(findMatches(text, 'b')).toEqual([{ start: 5, end: 6 }])
  })

  it('devuelve vacío cuando no hay coincidencia', () => {
    expect(findMatches('hola', 'adiós')).toEqual([])
  })
})

describe('buildSearchIndex', () => {
  const segments = [{ text: 'uno dos' }, { text: 'tres' }, { text: 'Dos y DOS' }]

  it('lista las coincidencias en orden entre segmentos', () => {
    const index = buildSearchIndex(segments, ' dos ')
    expect(index.query).toBe('dos')
    expect(index.hits).toEqual([
      { segment: 0, range: 0 },
      { segment: 2, range: 0 },
      { segment: 2, range: 1 },
    ])
    expect(index.ranges.get(1)).toBeUndefined()
    expect(index.ranges.get(2)).toHaveLength(2)
  })

  it('sin consulta no hay coincidencias', () => {
    const index = buildSearchIndex(segments, '')
    expect(index.hits).toEqual([])
    expect(index.query).toBe('')
  })
})
