import type { TranscriptSegment } from '../api/jobs'
import type { Translate } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'

// S13.04/S13.05: códigos estables del backend -> texto para la persona.
export const FLAG_KEYS: Readonly<Record<string, MessageKey>> = {
  repetition: 'flag.repetition',
  silence_hallucination: 'flag.silence_hallucination',
  out_of_bounds: 'flag.out_of_bounds',
  low_confidence: 'flag.low_confidence',
}

export function flagLabel(flag: string, t: Translate): string {
  return Object.hasOwn(FLAG_KEYS, flag) ? t(FLAG_KEYS[flag] ?? 'flag.low_confidence') : flag
}

export function flaggedSegments(
  segments: readonly TranscriptSegment[],
): TranscriptSegment[] {
  return segments.filter((segment) => segment.quality.flags.length > 0)
}
