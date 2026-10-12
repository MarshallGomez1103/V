/** Estado del texto a sintetizar frente al límite `max_chars` de la API (sobre el texto recortado). */
export interface SpeakTextStatus {
  chars: number
  words: number
  /** `near`: quedan pocos caracteres; `over`: pasa el límite y no se puede generar. */
  level: 'empty' | 'ok' | 'near' | 'over'
  /** Caracteres que quedan (nunca negativo) y que sobran. */
  left: number
  over: number
  canGenerate: boolean
}

/** Desde este porcentaje del límite se avisa que se está llegando. */
export const NEAR_LIMIT_RATIO = 0.9

export function speakTextStatus(text: string, maxChars: number): SpeakTextStatus {
  const trimmed = text.trim()
  // Puntos de código, como cuenta el backend (no unidades UTF-16).
  const chars = Array.from(trimmed).length
  const words = trimmed === '' ? 0 : trimmed.split(/\s+/u).length
  const over = Math.max(0, chars - maxChars)
  const left = Math.max(0, maxChars - chars)
  const level =
    chars === 0 ? 'empty' : over > 0 ? 'over' : chars >= maxChars * NEAR_LIMIT_RATIO ? 'near' : 'ok'
  return { chars, words, level, left, over, canGenerate: chars > 0 && over === 0 }
}
