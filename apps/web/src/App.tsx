import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Accordion,
  AccordionItem,
  Button,
  Column,
  Content,
  ContentSwitcher,
  Grid,
  Switch,
  Theme,
} from '@carbon/react'

import {
  cancelJob,
  createJob,
  JobApiError,
  PROCESSABLE_STATES,
} from './api/jobs'
import type { TranscriptSegment } from './api/jobs'
import { listSpeakers, type Speaker } from './api/speakers'
import { AppHeader } from './components/AppHeader'
import { AutosaveStatus } from './components/AutosaveStatus'
import { ClosedScreen } from './components/ClosedScreen'
import {
  DiarizationOptions,
  type DiarizationRequest,
} from './components/DiarizationOptions'
import { ExportMenu } from './components/ExportMenu'
import { GlossaryEditor } from './components/GlossaryEditor'
import { HealthStatus } from './components/HealthStatus'
import { JobScreen } from './components/JobScreen'
import { LivePreview } from './components/LivePreview'
import { MediaPanel } from './components/MediaPanel'
import { ModelManager } from './components/ModelManager'
import { NewProjectCard, type ImportResult } from './components/NewProjectCard'
import { Notice } from './components/Notice'
import { Panel } from './components/Panel'
import { ProfileSelector } from './components/ProfileSelector'
import { PropertiesPanel } from './components/PropertiesPanel'
import { ProvidersSettings } from './components/ProvidersSettings'
import { RecentJobs } from './components/RecentJobs'
import { ReviewQueue } from './components/ReviewQueue'
import { SegmentEditor } from './components/SegmentEditor'
import { SegmentList } from './components/SegmentList'
import { SegmentSpeakerSelect } from './components/SegmentSpeakerSelect'
import { ServerBanner } from './components/ServerBanner'
import { SpeakerTimeline } from './components/SpeakerTimeline'
import { SpeakersPanel } from './components/SpeakersPanel'
import { StyleInstructions } from './components/StyleInstructions'
import { TranscriptionOptionsSelector } from './components/TranscriptionOptionsSelector'
import { WordText } from './components/WordText'
import { useDiarizationModel } from './hooks/useDiarizationModel'
import { useJobEvents } from './hooks/useJobEvents'
import { useJobPreview } from './hooks/useJobPreview'
import { useRecentJobs, type RecentJob } from './hooks/useRecentJobs'
import { useSegmentDrafts } from './hooks/useSegmentDrafts'
import { useSeek } from './hooks/useSeek'
import { useServerStatus } from './hooks/useServerStatus'
import { translate, useI18n } from './i18n/i18n'
import type { MessageKey } from './i18n/messages'
import { NAV_ITEMS, type View } from './lib/navigation'
import { createPlayhead } from './lib/playhead'
import { useAppearance } from './theme/appearance'
import './App.scss'

const PAGE_KEYS: Record<View, { title: MessageKey; description: MessageKey }> = {
  transcribir: {
    title: 'page.transcribir.title',
    description: 'page.transcribir.description',
  },
  modelos: { title: 'page.modelos.title', description: 'page.modelos.description' },
  proveedores: {
    title: 'page.proveedores.title',
    description: 'page.proveedores.description',
  },
}

function viewFromHash(hash: string): View {
  const id = hash.replace(/^#/, '')
  return NAV_ITEMS.find((item) => item.id === id)?.id ?? 'transcribir'
}

/** Sección activa, sincronizada con el hash de la URL (enlaces y botón Atrás). */
function useView(): [View, (view: View) => void] {
  const [view, setView] = useState<View>(() => viewFromHash(window.location.hash))

  useEffect(() => {
    const onHashChange = () => {
      setView(viewFromHash(window.location.hash))
    }
    window.addEventListener('hashchange', onHashChange)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
    }
  }, [])

  const navigate = useCallback((next: View) => {
    setView(next)
    if (window.location.hash !== '#' + next) {
      window.location.hash = next
    }
  }, [])

  return [view, navigate]
}

function PageHeader({ view }: { view: View }) {
  const { t } = useI18n()
  const keys = PAGE_KEYS[view]
  return (
    <header className="voz-page__header">
      <h1 className="voz-page__title">{t(keys.title)}</h1>
      <p className="voz-page__description">{t(keys.description)}</p>
    </header>
  )
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

/** Una grabación abierta desde «guardadas»: solo se conoce lo que dicen proyecto y trabajo. */
function importFromRecent(item: RecentJob): ImportResult {
  return {
    project: item.project,
    media: {
      media_asset_id: item.job.media_asset_id,
      project_id: item.project.id,
      filename: item.project.name,
      media_type: null,
      duration_ms: null,
      sha256: '',
    },
  }
}

export function App() {
  const { t } = useI18n()
  const { resolved, accent } = useAppearance()
  const [closed, setClosed] = useState(false)
  const server = useServerStatus(!closed)
  const recent = useRecentJobs()
  const [imported, setImported] = useState<ImportResult | null>(null)
  const [openedJobId, setOpenedJobId] = useState<string | null>(null)
  // Mientras la persona no haya hecho nada, un trabajo en curso se retoma solo.
  const [skipResume, setSkipResume] = useState(false)
  const [optionId, setOptionId] = useState<string | null>(null)
  const [cloudConsent, setCloudConsent] = useState(true)
  const [profile, setProfile] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [jobError, setJobError] = useState<string | null>(null)
  const { seekToMs, seekNonce, seek } = useSeek()
  const [currentMs, setCurrentMs] = useState<number | undefined>(undefined)
  const drafts = useSegmentDrafts()
  const [modelsVersion, setModelsVersion] = useState(0)
  const refreshModels = useCallback(() => {
    setModelsVersion((version) => version + 1)
  }, [])
  const [diarization, setDiarization] = useState<DiarizationRequest>({
    enabled: false,
    speakers: {},
  })
  const [mode, setMode] = useState<'read' | 'edit'>('read')
  const [view, navigate] = useView()
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [speakersVersion, setSpeakersVersion] = useState(0)
  const [loadedSegments, setLoadedSegments] = useState<TranscriptSegment[]>([])

  const resume =
    !skipResume && imported === null && recent.phase === 'ready'
      ? recent.items.find((item) => PROCESSABLE_STATES.has(item.job.state))
      : undefined
  const baseImported = imported ?? (resume ? importFromRecent(resume) : null)
  // La duración de una grabación abierta desde «guardadas» la mide la forma de onda.
  const [measured, setMeasured] = useState<{ id: string; ms: number } | null>(null)
  const activeImported =
    baseImported !== null &&
    baseImported.media.duration_ms === null &&
    measured?.id === baseImported.media.media_asset_id
      ? { ...baseImported, media: { ...baseImported.media, duration_ms: measured.ms } }
      : baseImported
  const handleDuration = useCallback(
    (ms: number) => {
      if (baseImported !== null) {
        setMeasured({ id: baseImported.media.media_asset_id, ms })
      }
    },
    [baseImported],
  )
  const jobId = openedJobId ?? resume?.job.id ?? null

  const events = useJobEvents(jobId)
  const job = events.job
  const transcriptId = job?.transcript_id ?? null
  const processing = job !== null && PROCESSABLE_STATES.has(job.state)
  const completed = job?.state === 'COMPLETED'
  const diarizing = job?.state === 'DIARIZING' || job?.state === 'MERGING'
  const preview = useJobPreview(jobId, processing && transcriptId === null)
  const diarModel = useDiarizationModel(
    diarization.enabled && activeImported !== null && jobId === null,
    modelsVersion,
  )

  const reviewSegment = useCallback(
    (segment: TranscriptSegment) => {
      seek(segment.start_ms)
    },
    [seek],
  )
  const reloadSpeakers = useCallback(() => {
    setSpeakersVersion((version) => version + 1)
  }, [])
  // S7.07: la palabra actual se sigue con un store externo; solo re-renderiza
  // la palabra que entra y la que sale, no todas las filas.
  const playhead = useMemo(() => createPlayhead(), [])
  const handleTimeUpdate = useCallback(
    (ms: number) => {
      setCurrentMs(ms)
      playhead.set(ms)
    },
    [playhead],
  )
  const renderSegmentText = useCallback(
    (segment: TranscriptSegment, query: string) =>
      mode === 'edit' ? (
        <SegmentEditor segment={segment} drafts={drafts} query={query} />
      ) : (
        <WordText segment={segment} query={query} onSeek={seek} playhead={playhead} />
      ),
    [drafts, mode, playhead, seek],
  )
  const renderSegmentSpeaker = useMemo(
    () =>
      speakers.length > 0
        ? (segment: TranscriptSegment) => (
            <SegmentSpeakerSelect
              segmentId={segment.id}
              speakerId={segment.speaker_id}
              speakers={speakers}
              onChanged={reloadSpeakers}
            />
          )
        : undefined,
    [reloadSpeakers, speakers],
  )

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
      setOpenedJobId(created.id)
      setSkipResume(true)
    } catch (error: unknown) {
      setJobError(describeJobError(error))
    } finally {
      setCreating(false)
    }
  }, [cloudConsent, diarization, imported, optionId, profile, prompt])

  useEffect(() => {
    if (!transcriptId) {
      return
    }
    const controller = new AbortController()
    void listSpeakers(transcriptId, controller.signal)
      .then(setSpeakers)
      .catch(() => undefined)
    return () => {
      controller.abort()
    }
  }, [transcriptId, speakersVersion, completed])

  useEffect(() => {
    document.title = closed ? t('closed.doc') : t('app.title')
  }, [closed, t])

  const resetJob = () => {
    setOpenedJobId(null)
    setSkipResume(true)
    setSpeakers([])
    setLoadedSegments([])
    setMode('read')
    setJobError(null)
    setCurrentMs(undefined)
    playhead.set(undefined)
  }
  const changeFile = () => {
    resetJob()
    setImported(null)
    setOptionId(null)
  }
  const openRecent = (item: RecentJob) => {
    resetJob()
    setImported(importFromRecent(item))
    setOpenedJobId(item.job.id)
  }

  if (closed) {
    return <ClosedScreen />
  }

  const configDisabled = creating
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

  const transcriptTools =
    transcriptId && completed ? (
      <>
        <ContentSwitcher
          size="md"
          aria-label={t('work.mode.label')}
          selectedIndex={mode === 'read' ? 0 : 1}
          onChange={({ name }) => {
            setMode(name === 'edit' ? 'edit' : 'read')
          }}
        >
          <Switch name="read" text={t('work.mode.read')} />
          <Switch name="edit" text={t('work.mode.edit')} />
        </ContentSwitcher>
        <AutosaveStatus drafts={drafts} />
      </>
    ) : null

  const speakersPending = transcriptId !== null && diarizing

  return (
    <Theme
      theme={resolved}
      className="voz-app"
      {...{ 'data-accent': accent }}
    >
      <AppHeader
        view={view}
        onNavigate={navigate}
        jobActive={processing}
        onClosed={() => {
          setClosed(true)
        }}
      />

      <Content id="main-content" className="voz-content">
        {server.down ? (
          <div className="voz-banner">
            <ServerBanner onRetry={server.check} />
          </div>
        ) : null}
        <div hidden={view !== 'transcribir'}>
          <Grid narrow className={'voz-grid' + (jobId ? ' voz-grid--job' : '')}>
            <Column sm={4} md={8} lg={16}>
              <PageHeader view="transcribir" />
              {server.down ? null : <HealthStatus />}
            </Column>

            {activeImported === null ? (
              <>
                <Column sm={4} md={8} lg={10}>
                  <NewProjectCard
                    onImported={(result) => {
                      setImported(result)
                      setSkipResume(true)
                    }}
                  />
                </Column>
                <Column sm={4} md={8} lg={6}>
                  <RecentJobs state={recent} onOpen={openRecent} onRetry={recent.reload} />
                </Column>
              </>
            ) : jobId === null ? (
              <>
                <Column sm={4} md={8} lg={16}>
                  <MediaPanel
                    imported={activeImported}
                    showMeta
                    seekToMs={seekToMs}
                    seekNonce={seekNonce}
                    currentMs={currentMs ?? 0}
                    onTimeUpdate={handleTimeUpdate}
                    onSeek={seek}
                    onDuration={handleDuration}
                    onChangeFile={changeFile}
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
                      mediaAssetId={activeImported.media.media_asset_id}
                      value={optionId}
                      onChange={setOptionId}
                      onCloudConsentChange={setCloudConsent}
                      disabled={configDisabled}
                    />
                    <ProfileSelector
                      value={profile}
                      onChange={setProfile}
                      language={null}
                      disabled={configDisabled}
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
                          disabled={configDisabled}
                          model={diarModel}
                        />
                      </AccordionItem>
                      <AccordionItem title={t('cfg.style')} open>
                        <StyleInstructions
                          value={prompt}
                          onChange={setPrompt}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                      <AccordionItem title={t('cfg.glossary')}>
                        <GlossaryEditor
                          projectId={activeImported.project.id}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                    </Accordion>
                  </Panel>
                </Column>
                <Column sm={4} md={8} lg={16}>
                  <div className="voz-actionbar">
                    {jobError ? (
                      <Notice
                        kind="error"
                        title={t('cfg.error.title')}
                        subtitle={jobError}
                      />
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
            ) : (
              <>
                <Column sm={4} md={8} lg={16}>
                  <JobScreen
                    job={job}
                    loading={creating}
                    error={events.error}
                    onCancel={() => {
                      void cancelJob(jobId).catch(() => undefined)
                    }}
                    onAdjust={resetJob}
                  />
                  {transcriptId && job?.diarization_error_code ? (
                    <div className="voz-after">
                      <Notice
                        kind="warning"
                        role="status"
                        title={t('job.diarFailed.title')}
                        subtitle={t('job.diarFailed.body', { code: job.diarization_error_code })}
                      />
                    </div>
                  ) : null}
                </Column>

                <Column sm={4} md={8} lg={11}>
                  <div className="voz-workspace">
                    {transcriptId === null && processing && preview.available ? (
                      <LivePreview segments={preview.segments} />
                    ) : null}
                    {transcriptId ? (
                      <SegmentList
                        transcriptId={transcriptId}
                        onSeek={seek}
                        currentMs={currentMs}
                        renderText={renderSegmentText}
                        renderSpeaker={renderSegmentSpeaker}
                        speakers={speakers}
                        reloadKey={speakersVersion * 2 + (completed ? 1 : 0)}
                        onSegmentsLoaded={setLoadedSegments}
                        headerActions={transcriptTools}
                        notice={
                          speakersPending ? (
                            <Notice
                              kind="info"
                              role="status"
                              title={t('work.pending.title')}
                              subtitle={t('work.pending.body')}
                            />
                          ) : null
                        }
                      />
                    ) : null}
                    <MediaPanel
                      imported={activeImported}
                      titleId="audio-title"
                      title={t('work.playback.title')}
                      seekToMs={seekToMs}
                      seekNonce={seekNonce}
                      currentMs={currentMs ?? 0}
                      onTimeUpdate={handleTimeUpdate}
                      onSeek={seek}
                      onDuration={handleDuration}
                    >
                      {transcriptId ? (
                        <SpeakerTimeline
                          segments={loadedSegments}
                          speakers={speakers}
                          durationMs={activeImported.media.duration_ms}
                          playhead={playhead}
                          onSeek={seek}
                          speakersPending={speakersPending}
                        />
                      ) : null}
                    </MediaPanel>
                  </div>
                </Column>

                <Column sm={4} md={8} lg={5}>
                  <div className="voz-workspace">
                    <PropertiesPanel
                      imported={activeImported}
                      job={job}
                      tools={
                        transcriptId && completed ? (
                          <ExportMenu transcriptId={transcriptId} />
                        ) : null
                      }
                    />
                    {transcriptId ? (
                      <SpeakersPanel
                        transcriptId={transcriptId}
                        onChanged={reloadSpeakers}
                        pending={speakersPending}
                      />
                    ) : null}
                    {transcriptId ? (
                      <ReviewQueue segments={loadedSegments} onSelect={reviewSegment} />
                    ) : null}
                  </div>
                </Column>
              </>
            )}
          </Grid>
        </div>

        <div hidden={view !== 'modelos'}>
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader view="modelos" />
              <ModelManager onModelsChanged={refreshModels} />
            </Column>
          </Grid>
        </div>

        <div hidden={view !== 'proveedores'}>
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader view="proveedores" />
              <ProvidersSettings onChanged={refreshModels} />
            </Column>
          </Grid>
        </div>
      </Content>
    </Theme>
  )
}
