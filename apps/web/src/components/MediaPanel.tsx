import type { ReactNode } from 'react'
import { Button } from '@carbon/react'
import { Renew } from '@carbon/icons-react'

import { useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { mediaTypeLabel } from '../lib/media'
import type { ImportResult } from './NewProjectCard'
import { AudioPlayer } from './AudioPlayer'
import { Term } from './Hint'
import { Panel } from './Panel'
import { Waveform } from './Waveform'
import './MediaPanel.scss'

interface MediaPanelProps {
  imported: ImportResult
  seekToMs: number | null
  seekNonce: number
  currentMs: number
  onTimeUpdate: (ms: number) => void
  onSeek: (ms: number) => void
  onDuration?: ((ms: number) => void) | undefined
  /** Ficha del archivo (duración, tipo, huella) encima del reproductor. */
  showMeta?: boolean
  /** Botón para volver a importar otra grabación. */
  onChangeFile?: (() => void) | undefined
  /** Contenido extra bajo la forma de onda (la línea de tiempo de hablantes). */
  children?: ReactNode
  title?: string | undefined
  titleId?: string
}

/** Reproductor del original (controles Carbon), forma de onda y, si se da, la línea de tiempo. */
export function MediaPanel({
  imported,
  seekToMs,
  seekNonce,
  currentMs,
  onTimeUpdate,
  onSeek,
  onDuration,
  showMeta = false,
  onChangeFile,
  children,
  title,
  titleId = 'audio-title',
}: MediaPanelProps) {
  const { t } = useI18n()
  const { media, project } = imported
  return (
    <Panel
      titleId={titleId}
      title={title ?? media.filename}
      description={t('media.description', { project: project.name })}
      actions={
        onChangeFile ? (
          <Button kind="ghost" size="sm" renderIcon={Renew} onClick={onChangeFile}>
            {t('media.change')}
          </Button>
        ) : null
      }
    >
      {showMeta ? (
        <dl className="voz-meta">
          <div>
            <dt>{t('media.duration')}</dt>
            <dd>{media.duration_ms === null ? '—' : formatDuration(media.duration_ms)}</dd>
          </div>
          {media.media_type !== null ? (
            <div>
              <dt>{t('media.type')}</dt>
              <dd>{t(mediaTypeLabel(media.media_type))}</dd>
            </div>
          ) : null}
          {media.sha256 !== '' ? (
            <div>
              <dt>
                <Term definition="term.fingerprint.def">{t('media.fingerprint')}</Term>
              </dt>
              <dd className="voz-mono">{media.sha256.slice(0, 8)}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
      <AudioPlayer
        mediaAssetId={media.media_asset_id}
        seekToMs={seekToMs}
        seekNonce={seekNonce}
        onTimeUpdate={onTimeUpdate}
        durationMs={media.duration_ms}
      />
      <Waveform
        mediaAssetId={media.media_asset_id}
        currentMs={currentMs}
        onSeek={onSeek}
        onDuration={onDuration}
      />
      {children}
    </Panel>
  )
}
