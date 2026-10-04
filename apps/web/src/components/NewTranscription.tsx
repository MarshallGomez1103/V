import { useCallback, useState, type ReactNode } from 'react'
import { Accordion, AccordionItem, Button, Column, Grid } from '@carbon/react'

import { createJob, JobApiError, type JobView } from '../api/jobs'
import { useDiarizationModel } from '../hooks/useDiarizationModel'
import { useSeek } from '../hooks/useSeek'
import { translate, useI18n } from '../i18n/i18n'
import { DiarizationOptions, type DiarizationRequest } from './DiarizationOptions'
import { GlossaryEditor } from './GlossaryEditor'
import { MediaPanel } from './MediaPanel'
import { NewProjectCard, type ImportResult } from './NewProjectCard'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { ProfileSelector } from './ProfileSelector'
import { StyleInstructions } from './StyleInstructions'
import { TranscriptionOptionsSelector } from './TranscriptionOptionsSelector'

interface NewTranscriptionProps {
  /** Cabecera de la página (título, estado de la API). */
  header: ReactNode
  /** Grabación ya importada con la que se abre (p. ej. «Ajustar» tras un fallo). */
  initialImported?: ImportResult | null
  /** Cambia cuando se instala o quita un modelo: refresca las opciones de motor. */
  modelsVersion: number
  onCreated: (job: JobView, imported: ImportResult) => void
}

function describeJobError(error: unknown): string {
  if (error instanceof JobApiError) {
    const reasons = error.blockingReasons?.length
      ? ' (' + error.blockingReasons.join(', ') + ')'
      : ''
    return error.message + reasons
  }
  return translate('err.job.create')
}

/** `#/nueva`: importar una grabación, elegir motor y opciones, y crear el trabajo. */
export function NewTranscription({
  header,
  initialImported = null,
  modelsVersion,
  onCreated,
}: NewTranscriptionProps) {
  const { t } = useI18n()
  const [imported, setImported] = useState<ImportResult | null>(initialImported)
  const [optionId, setOptionId] = useState<string | null>(null)
  const [cloudConsent, setCloudConsent] = useState(true)
  const [profile, setProfile] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [jobError, setJobError] = useState<string | null>(null)
  const [diarization, setDiarization] = useState<DiarizationRequest>({
    enabled: false,
    speakers: {},
  })
  const { seekToMs, seekNonce, seek } = useSeek()
  const [currentMs, setCurrentMs] = useState(0)
  // La duración de una grabación abierta sin medir la mide la forma de onda.
  const [measured, setMeasured] = useState<{ id: string; ms: number } | null>(null)
  const active =
    imported !== null &&
    imported.media.duration_ms === null &&
    measured?.id === imported.media.media_asset_id
      ? { ...imported, media: { ...imported.media, duration_ms: measured.ms } }
      : imported
  const handleDuration = useCallback(
    (ms: number) => {
      if (imported !== null) {
        setMeasured({ id: imported.media.media_asset_id, ms })
      }
    },
    [imported],
  )
  const diarModel = useDiarizationModel(diarization.enabled && active !== null, modelsVersion)

  const startJob = useCallback(async () => {
    if (!imported || !optionId || !cloudConsent) {
      return
    }
    setCreating(true)
    setJobError(null)
    try {
      const created = await createJob({
        project_id: imported.project.id,
        media_asset_id: imported.media.media_asset_id,
        option_id: optionId,
        language: null, // ponytail: idioma autodetectado; selector de idioma en un corte posterior
        diarization,
        ...(profile ? { profile } : {}),
        ...(prompt.trim() !== '' ? { prompt: prompt.trim() } : {}),
      })
      onCreated(created, imported)
    } catch (error: unknown) {
      setJobError(describeJobError(error))
    } finally {
      setCreating(false)
    }
  }, [cloudConsent, diarization, imported, onCreated, optionId, profile, prompt])

  const diarBlocked = diarization.enabled && diarModel.status !== 'ready'
  const canStart = optionId !== null && cloudConsent && !creating && !diarBlocked
  const whyNot = creating
    ? null
    : optionId === null
      ? t('cfg.why.option')
      : !cloudConsent
        ? t('cfg.why.consent')
        : diarBlocked
          ? t('diar.blocked')
          : null

  return (
    <Grid narrow className="voz-grid">
      <Column sm={4} md={8} lg={16}>
        {header}
      </Column>

      {active === null ? (
        <>
          <Column sm={4} md={8} lg={10}>
            <NewProjectCard
              onImported={(result) => {
                setImported(result)
              }}
            />
          </Column>
          <Column sm={4} md={8} lg={6}>
            <Panel titleId="start-title" title={t('start.title')}>
              <ol className="voz-steps">
                <li>{t('start.step1')}</li>
                <li>{t('start.step2')}</li>
                <li>{t('start.step3')}</li>
              </ol>
              <p className="voz-field-note">
                {t('start.models')} <a href="#/modelos">{t('start.models.link')}</a>
              </p>
            </Panel>
          </Column>
        </>
      ) : (
        <>
          <Column sm={4} md={8} lg={16}>
            <MediaPanel
              imported={active}
              showMeta
              seekToMs={seekToMs}
              seekNonce={seekNonce}
              currentMs={currentMs}
              onTimeUpdate={setCurrentMs}
              onSeek={seek}
              onDuration={handleDuration}
              onChangeFile={() => {
                setImported(null)
                setOptionId(null)
              }}
            />
          </Column>
          <Column sm={4} md={8} lg={8}>
            <Panel
              titleId="options-title"
              title={t('cfg.engine.title')}
              description={t('cfg.engine.desc')}
            >
              <TranscriptionOptionsSelector
                refreshKey={modelsVersion}
                mediaAssetId={active.media.media_asset_id}
                value={optionId}
                onChange={setOptionId}
                onCloudConsentChange={setCloudConsent}
                disabled={creating}
              />
              <ProfileSelector
                value={profile}
                onChange={setProfile}
                language={null}
                disabled={creating}
              />
            </Panel>
          </Column>
          <Column sm={4} md={8} lg={8}>
            <Panel
              titleId="extras-title"
              title={t('cfg.options.title')}
              description={t('cfg.options.desc')}
            >
              <Accordion isFlush>
                <AccordionItem title={t('spk.title')} open>
                  <DiarizationOptions
                    value={diarization}
                    onChange={setDiarization}
                    disabled={creating}
                    model={diarModel}
                  />
                </AccordionItem>
                <AccordionItem title={t('cfg.style')} open>
                  <StyleInstructions value={prompt} onChange={setPrompt} disabled={creating} />
                </AccordionItem>
                <AccordionItem title={t('cfg.glossary')}>
                  <GlossaryEditor projectId={active.project.id} disabled={creating} />
                </AccordionItem>
              </Accordion>
            </Panel>
          </Column>
          <Column sm={4} md={8} lg={16}>
            <div className="voz-actionbar">
              {jobError ? (
                <Notice kind="error" title={t('cfg.error.title')} subtitle={jobError} />
              ) : null}
              <div className="voz-actionbar__row">
                <Button
                  kind="primary"
                  size="lg"
                  disabled={!canStart}
                  onClick={() => void startJob()}
                >
                  {creating ? t('cfg.starting') : t('cfg.start')}
                </Button>
                {whyNot ? (
                  <p className="voz-field-note" role="status">
                    {whyNot}
                  </p>
                ) : null}
              </div>
            </div>
          </Column>
        </>
      )}
    </Grid>
  )
}
