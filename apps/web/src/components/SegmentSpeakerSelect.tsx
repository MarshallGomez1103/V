import { useState } from 'react'
import { Select, SelectItem } from '@carbon/react'

import { assignSegmentSpeaker, type Speaker } from '../api/speakers'
import { translate, useI18n } from '../i18n/i18n'

import './SegmentSpeakerSelect.scss'

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
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)
  const current = speakers.find((speaker) => speaker.id === speakerId)

  async function change(next: string) {
    try {
      await assignSegmentSpeaker(segmentId, next === '' ? null : next)
      setError(null)
      onChanged?.()
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : translate('err.speaker.reassign'),
      )
    }
  }

  return (
    <span className="voz-segment-speaker">
      <span
        className="voz-segment-speaker__chip"
        aria-hidden="true"
        style={{ backgroundColor: current?.color ?? 'transparent' }}
      />
      <Select
        id={'segment-speaker-' + segmentId}
        size="sm"
        inline
        hideLabel
        labelText={t('spk.ofSegment', { id: segmentId })}
        value={current?.id ?? ''}
        onChange={(event) => {
          void change(event.target.value)
        }}
      >
        <SelectItem value="" text={t('spk.none.option')} />
        {speakers.map((speaker) => (
          <SelectItem key={speaker.id} value={speaker.id} text={speaker.name} />
        ))}
      </Select>
      {error !== null && (
        <span className="voz-segment-speaker__error" role="alert">
          {error}
        </span>
      )}
    </span>
  )
}
