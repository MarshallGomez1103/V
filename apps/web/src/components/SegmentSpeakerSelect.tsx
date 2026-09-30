import { useState } from 'react'

import { assignSegmentSpeaker, type Speaker } from '../api/speakers'

import './SegmentSpeakerSelect.css'

interface SegmentSpeakerSelectProps {
  segmentId: string
  speakerId: string | null
  speakers: Speaker[]
  onChanged?: () => void
}

export function SegmentSpeakerSelect({
  segmentId,
  speakerId,
  speakers,
  onChanged,
}: SegmentSpeakerSelectProps) {
  const [error, setError] = useState<string | null>(null)
  const current = speakers.find((speaker) => speaker.id === speakerId)

  async function change(next: string) {
    try {
      await assignSegmentSpeaker(segmentId, next === '' ? null : next)
      setError(null)
      onChanged?.()
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'No se pudo reasignar el hablante.',
      )
    }
  }

  return (
    <span className="segment-speaker">
      <span
        className="segment-speaker-chip"
        aria-hidden="true"
        style={{ backgroundColor: current?.color ?? 'transparent' }}
      />
      <select
        aria-label={'Hablante del segmento ' + segmentId}
        value={current?.id ?? ''}
        onChange={(event) => {
          void change(event.target.value)
        }}
      >
        <option value="">Sin hablante</option>
        {speakers.map((speaker) => (
          <option key={speaker.id} value={speaker.id}>
            {speaker.name}
          </option>
        ))}
      </select>
      {error !== null && (
        <span className="segment-speaker-error" role="alert">
          {error}
        </span>
      )}
    </span>
  )
}
