import { useEffect, useRef } from 'react'

import type { PreviewSegment } from '../api/preview'
import { useI18n } from '../i18n/i18n'
import { formatStamp, formatSeconds } from '../lib/formatTime'
import { Busy } from './Busy'
import { Panel } from './Panel'
import './LivePreview.scss'

interface LivePreviewProps {
  segments: readonly PreviewSegment[]
}

/** Texto confirmado por el motor mientras transcribe (antes de que exista el transcript). */
export function LivePreview({ segments }: LivePreviewProps) {
  const { t, tn } = useI18n()
  const scrollRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  // Sigue el final de la lista salvo que la persona haya subido a leer.
  useEffect(() => {
    const box = scrollRef.current
    if (box && stick.current) {
      box.scrollTop = box.scrollHeight
    }
  }, [segments.length])

  const last = segments.at(-1)

  return (
    <Panel
      titleId="preview-title"
      title={t('preview.title')}
      description={t('preview.desc')}
      className="voz-preview"
    >
      {segments.length === 0 ? (
        <div role="status">
          <Busy description={t('preview.waiting')} />
          <p className="voz-field-note">{t('preview.empty')}</p>
        </div>
      ) : (
        <>
          <div
            ref={scrollRef}
            className="voz-preview__scroll"
            role="region"
            aria-label={t('preview.list')}
            tabIndex={0}
            onScroll={(event) => {
              const box = event.currentTarget
              stick.current = box.scrollHeight - box.scrollTop - box.clientHeight < 24
            }}
          >
            <ol className="voz-preview__list">
              {segments.map((segment) => (
                <li key={segment.start_ms + ':' + segment.end_ms} className="voz-preview__row">
                  <time className="voz-preview__time">{formatStamp(segment.start_ms)}</time>
                  <span className="voz-preview__text">{segment.text}</span>
                </li>
              ))}
            </ol>
          </div>
          <p className="voz-field-note" role="status">
            {tn('preview.count', segments.length, {
              time: formatSeconds((last?.end_ms ?? 0) / 1000),
            })}
          </p>
        </>
      )}
    </Panel>
  )
}
