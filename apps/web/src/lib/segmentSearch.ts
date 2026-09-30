export interface TextRange {
  start: number
  end: number
}

export interface SearchHit {
  segment: number
  range: number
}

export interface SearchIndex {
  query: string
  ranges: ReadonlyMap<number, readonly TextRange[]>
  hits: readonly SearchHit[]
}

const MARKS = /\p{M}/gu

// Minúsculas y sin marcas diacríticas (NFD): "Canción" ~ "cancion". Ojo: "ñ"
// también se pliega a "n"; es lo que significa "insensible a tildes".
function fold(text: string): string {
  return text.normalize('NFD').replace(MARKS, '').toLowerCase()
}

/**
 * S5.13: rangos [start, end) en el texto ORIGINAL de cada coincidencia de
 * `query` (no solapadas), insensible a mayúsculas y tildes. El plegado puede
 * cambiar la longitud (ligaduras, marcas combinadas), así que se construye un
 * mapa índice plegado → índice original para resaltar el texto sin alterarlo.
 */
export function findMatches(text: string, query: string): TextRange[] {
  const needle = fold(query.trim())
  if (needle === '') {
    return []
  }
  // Camino rápido: casi todos los segmentos no coinciden y fold nativo es barato.
  if (!fold(text).includes(needle)) {
    return []
  }

  let folded = ''
  const starts: number[] = []
  const ends: number[] = []
  let position = 0
  let lastGroup = 0
  for (const char of text) {
    const next = position + char.length
    const piece = fold(char)
    if (piece === '') {
      // Marca combinante suelta: se pega al carácter previo.
      for (let i = lastGroup; i < ends.length; i += 1) {
        ends[i] = next
      }
    } else {
      lastGroup = starts.length
      for (let i = 0; i < piece.length; i += 1) {
        starts.push(position)
        ends.push(next)
      }
      folded += piece
    }
    position = next
  }

  const ranges: TextRange[] = []
  let from = 0
  for (;;) {
    const at = folded.indexOf(needle, from)
    if (at < 0) {
      return ranges
    }
    ranges.push({
      start: starts[at] as number,
      end: ends[at + needle.length - 1] as number,
    })
    from = at + needle.length
  }
}

const EMPTY: SearchIndex = { query: '', ranges: new Map(), hits: [] }

/** Coincidencias de todos los segmentos, en orden de aparición. */
export function buildSearchIndex(
  segments: readonly { text: string }[],
  query: string,
): SearchIndex {
  const trimmed = query.trim()
  if (trimmed === '') {
    return EMPTY
  }
  const ranges = new Map<number, readonly TextRange[]>()
  const hits: SearchHit[] = []
  segments.forEach((segment, index) => {
    const found = findMatches(segment.text, trimmed)
    if (found.length > 0) {
      ranges.set(index, found)
      found.forEach((_, range) => hits.push({ segment: index, range }))
    }
  })
  return { query: trimmed, ranges, hits }
}
