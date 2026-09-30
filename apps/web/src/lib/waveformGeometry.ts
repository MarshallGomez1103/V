// S5.09/S5.14: geometría pura del waveform (sin DOM, sin canvas).

export const MIN_ZOOM = 1
export const MAX_ZOOM = 32
export const SEEK_STEP_MS = 5000

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Entero en [1, 32]; un valor no numérico vuelve a 1x. */
export function clampZoom(zoom: number): number {
  return Number.isFinite(zoom)
    ? clamp(Math.round(zoom), MIN_ZOOM, MAX_ZOOM)
    : MIN_ZOOM
}

export function zoomIn(zoom: number): number {
  return clampZoom(zoom * 2)
}

export function zoomOut(zoom: number): number {
  return clampZoom(zoom / 2)
}

/** Ancho en px del waveform completo para un ancho de vista y un zoom. */
export function contentWidth(viewportWidth: number, zoom: number): number {
  return Math.max(1, Math.round(viewportWidth * clampZoom(zoom)))
}

export function msToX(ms: number, durationMs: number, width: number): number {
  if (durationMs <= 0) {
    return 0
  }
  return clamp((ms / durationMs) * width, 0, width)
}

export function xToMs(x: number, durationMs: number, width: number): number {
  if (width <= 0) {
    return 0
  }
  return Math.round(clamp(x / width, 0, 1) * durationMs)
}

export function clampScrollLeft(
  scrollLeft: number,
  viewportWidth: number,
  width: number,
): number {
  return clamp(scrollLeft, 0, Math.max(0, width - viewportWidth))
}

export function isVisibleX(
  x: number,
  scrollLeft: number,
  viewportWidth: number,
): boolean {
  return x >= scrollLeft && x <= scrollLeft + viewportWidth
}

/** Centra `x` en la vista si está fuera de ella; si ya se ve, no mueve nada. */
export function scrollLeftToReveal(
  x: number,
  scrollLeft: number,
  viewportWidth: number,
  width: number,
): number {
  if (isVisibleX(x, scrollLeft, viewportWidth)) {
    return clampScrollLeft(scrollLeft, viewportWidth, width)
  }
  return clampScrollLeft(x - viewportWidth / 2, viewportWidth, width)
}

export interface ZoomScrollInput {
  playheadMs: number
  durationMs: number
  viewportWidth: number
  oldZoom: number
  newZoom: number
  scrollLeft: number
}

/**
 * Nuevo scrollLeft al cambiar el zoom: el playhead conserva su posición en la
 * vista; si estaba fuera, queda centrado. Siempre termina visible.
 */
export function scrollLeftForZoom(input: ZoomScrollInput): number {
  const { playheadMs, durationMs, viewportWidth, scrollLeft } = input
  const oldX = msToX(
    playheadMs,
    durationMs,
    contentWidth(viewportWidth, input.oldZoom),
  )
  const newWidth = contentWidth(viewportWidth, input.newZoom)
  const newX = msToX(playheadMs, durationMs, newWidth)
  const offset = isVisibleX(oldX, scrollLeft, viewportWidth)
    ? oldX - scrollLeft
    : viewportWidth / 2
  return clampScrollLeft(newX - offset, viewportWidth, newWidth)
}

/** Salto de teclado (±5 s por defecto) acotado a la duración. */
export function seekTarget(
  currentMs: number,
  direction: -1 | 1,
  durationMs: number,
  stepMs: number = SEEK_STEP_MS,
): number {
  return clamp(currentMs + direction * stepMs, 0, Math.max(0, durationMs))
}

/**
 * Un `[min, max]` por columna de píxeles visible: agrega varios buckets si hay
 * más buckets que píxeles y repite el más cercano si hay menos.
 */
export function columnPeaks(
  peaks: readonly (readonly [number, number])[],
  scrollLeft: number,
  viewportWidth: number,
  width: number,
): [number, number][] {
  const count = peaks.length
  const columns: [number, number][] = []
  if (count === 0 || width <= 0) {
    return columns
  }
  for (let column = 0; column < viewportWidth; column += 1) {
    const x = scrollLeft + column
    if (x >= width) {
      break
    }
    const first = clamp(Math.floor((x / width) * count), 0, count - 1)
    const last = clamp(
      Math.max(first + 1, Math.ceil(((x + 1) / width) * count)),
      first + 1,
      count,
    )
    let low = 1
    let high = -1
    for (let index = first; index < last; index += 1) {
      const pair = peaks[index]
      if (pair) {
        low = Math.min(low, pair[0])
        high = Math.max(high, pair[1])
      }
    }
    columns.push([low, high])
  }
  return columns
}

export function formatClock(ms: number): string {
  const totalSeconds = Math.floor(Math.max(0, ms) / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return String(minutes) + ':' + String(seconds).padStart(2, '0')
}
