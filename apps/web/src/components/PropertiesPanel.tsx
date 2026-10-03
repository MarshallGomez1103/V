import type { ReactNode } from 'react'
import { Button } from '@carbon/react'

import type { JobView } from '../api/jobs'
import { useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { mediaTypeLabel } from '../lib/media'
import type { ImportResult } from './NewProjectCard'
import { Term } from './Hint'
import { Panel } from './Panel'
import { DeviceLabel, PrecisionLabel, ProcessingProfileLabel } from './TechTerms'
import './PropertiesPanel.scss'

interface PropertiesPanelProps {
  imported: ImportResult
  job: JobView | null
  /** Exportar, Leer/Editar… (solo cuando hay transcripción terminada). */
  tools?: ReactNode
  onAdjust?: (() => void) | undefined
}

function Row({ label, hint, children }: { label: string; hint?: 'term.fingerprint.def' | 'term.language.def' | 'term.qprofile.def' | undefined; children: ReactNode }) {
  return (
    <div className="voz-props__row">
      <dt>{hint ? <Term definition={hint}>{label}</Term> : label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** Propiedades de la transcripción (archivo, idioma, modelo, hablantes…), a la derecha del texto. */
export function PropertiesPanel({ imported, job, tools, onAdjust }: PropertiesPanelProps) {
  const { t } = useI18n()
  const { media, project } = imported
  const selection = job?.selection
  const execution = selection?.execution
  const quality = selection?.quality_profile
  const prompt = typeof selection?.prompt === 'string' && selection.prompt !== '' ? selection.prompt : null
  const speakersOn = selection?.diarization?.enabled === true

  return (
    <Panel titleId="props-title" title={t('props.title')} description={t('props.description')}>
      <dl className="voz-props">
        {media.sha256 !== '' ? <Row label={t('props.file')}>{media.filename}</Row> : null}
        <Row label={t('props.project')}>{project.name}</Row>
        {media.duration_ms !== null ? (
          <Row label={t('media.duration')}>{formatDuration(media.duration_ms)}</Row>
        ) : null}
        {media.media_type !== null ? (
          <Row label={t('media.type')}>{t(mediaTypeLabel(media.media_type))}</Row>
        ) : null}
        {media.sha256 !== '' ? (
          <Row label={t('media.fingerprint')} hint="term.fingerprint.def">
            <span className="voz-mono">{media.sha256.slice(0, 8)}</span>
          </Row>
        ) : null}
        {selection ? (
          <>
            <Row label={t('props.language')} hint="term.language.def">
              {selection.language ? selection.language : t('props.language.auto')}
            </Row>
            <Row label={t('job.fig.model')}>{selection.model_id}</Row>
            {selection.profile?.name ? (
              <Row label={t('job.fig.profile')}>
                <ProcessingProfileLabel name={selection.profile.name} />
              </Row>
            ) : null}
            {quality ? (
              <Row label={t('props.quality')} hint="term.qprofile.def">
                {quality.name === 'academic'
                  ? t('profile.academic.label')
                  : quality.name === 'default'
                    ? t('profile.default.label')
                    : quality.name}
              </Row>
            ) : null}
            {execution?.device ? (
              <Row label={t('job.fig.device')}>
                <DeviceLabel device={execution.device} />
                {typeof execution.precision === 'string' ? (
                  <>
                    {' · '}
                    <PrecisionLabel precision={execution.precision} />
                  </>
                ) : null}
              </Row>
            ) : null}
            <Row label={t('spk.title')}>
              {speakersOn ? t('props.speakers.on') : t('props.speakers.off')}
            </Row>
            {prompt !== null ? (
              <Row label={t('props.prompt')}>
                <span className="voz-props__prompt" title={prompt}>
                  {prompt}
                </span>
              </Row>
            ) : null}
            {selection.glossary && selection.glossary.length > 0 ? (
              <Row label={t('props.glossary')}>
                {t('props.glossary.count', { n: selection.glossary.length })}
              </Row>
            ) : null}
          </>
        ) : null}
      </dl>
      {tools || onAdjust ? (
        <div className="voz-props__actions">
          {tools}
          {onAdjust ? (
            <Button kind="ghost" size="md" onClick={onAdjust} title={t('job.adjust.why')}>
              {t('job.adjust')}
            </Button>
          ) : null}
        </div>
      ) : null}
    </Panel>
  )
}
