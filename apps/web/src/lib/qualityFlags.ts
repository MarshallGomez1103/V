import type { TranscriptSegment } from '../api/jobs'

// S13.04/S13.05: códigos estables del backend -> texto para la persona.
export const FLAG_LABELS: Readonly<Record<string, string>> = {
  repetition: 'Repetición',
  silence_hallucination: 'Posible alucinación en silencio',
  out_of_bounds: 'Fuera del audio',
  low_confidence: 'Baja confianza',
}

export function flagLabel(flag: string): string {
  return FLAG_LABELS[flag] ?? flag
}

export function flaggedSegments(
  segments: readonly TranscriptSegment[],
): TranscriptSegment[] {
  return segments.filter((segment) => segment.quality.flags.length > 0)
}
