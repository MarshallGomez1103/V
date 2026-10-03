import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Accordion,
  AccordionItem,
  Button,
  Column,
  Content,
  ContentSwitcher,
  Grid,
  ListItem,
  Switch,
  Theme,
  UnorderedList,
} from '@carbon/react'

import { cancelJob, createJob, JobApiError } from './api/jobs'
import type { TranscriptSegment } from './api/jobs'
import { listSpeakers, type Speaker } from './api/speakers'
import { AppHeader } from './components/AppHeader'
import { AudioPlayer } from './components/AudioPlayer'
import { AutosaveStatus } from './components/AutosaveStatus'
import {
  DiarizationOptions,
  type DiarizationRequest,
} from './components/DiarizationOptions'
import { ExportMenu } from './components/ExportMenu'
import { GlossaryEditor } from './components/GlossaryEditor'
import { HealthStatus } from './components/HealthStatus'
import { JobScreen } from './components/JobScreen'
import { ModelManager } from './components/ModelManager'
import { NewProjectCard, type ImportResult } from './components/NewProjectCard'
import { Notice } from './components/Notice'
import { Panel } from './components/Panel'
import { ProfileSelector } from './components/ProfileSelector'
import { ProvidersSettings } from './components/ProvidersSettings'
import { ReviewQueue } from './components/ReviewQueue'
import { SegmentEditor } from './components/SegmentEditor'
import { SegmentList } from './components/SegmentList'
import { SegmentSpeakerSelect } from './components/SegmentSpeakerSelect'
import { SpeakersPanel } from './components/SpeakersPanel'
import { TranscriptionOptionsSelector } from './components/TranscriptionOptionsSelector'
import { Waveform } from './components/Waveform'
import { WordText } from './components/WordText'
import { useColorScheme } from './hooks/useColorScheme'
import { useJobEvents } from './hooks/useJobEvents'
import { useSegmentDrafts } from './hooks/useSegmentDrafts'
import { useSeek } from './hooks/useSeek'
import { NAV_ITEMS, type View } from './lib/navigation'
import { createPlayhead } from './lib/playhead'
import './App.scss'

const PAGE_TEXT: Record<View, { title: string; description: string }> = {
  transcribir: {
    title: 'Transcribir',
    description:
      'Importa una grabación, elige el motor y obtén texto editable. Todo se procesa en este equipo.',
  },
  modelos: {
    title: 'Modelos',
    description:
      'Instala, reutiliza o elimina los modelos de este equipo. Funcionan sin Internet una vez instalados.',
  },
  proveedores: {
    title: 'Proveedores cloud',
    description:
      'Opcional. Solo si eliges un proveedor para una transcripción concreta, tu audio sale de este equipo.',
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
  const { title, description } = PAGE_TEXT[view]
  return (
    <header className="voz-page__header">
      <h1 className="voz-page__title">{title}</h1>
      <p className="voz-page__description">{description}</p>
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
  return 'No se pudo crear la transcripción.'
}

export function App() {
  const [imported, setImported] = useState<ImportResult | null>(null)
  const [optionId, setOptionId] = useState<string | null>(null)
  const [cloudConsent, setCloudConsent] = useState(true)
  const [profile, setProfile] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [jobError, setJobError] = useState<string | null>(null)
  const events = useJobEvents(jobId)
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
  const scheme = useColorScheme()
  const [view, navigate] = useView()
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [speakersVersion, setSpeakersVersion] = useState(0)
  const [loadedSegments, setLoadedSegments] = useState<TranscriptSegment[]>([])
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
    (segment: TranscriptSegment, query: string) => (
      <>
        {speakers.length > 0 ? (
          <SegmentSpeakerSelect
            segmentId={segment.id}
            speakerId={segment.speaker_id}
            speakers={speakers}
            onChanged={reloadSpeakers}
          />
        ) : null}
        {mode === 'edit' ? (
          <SegmentEditor segment={segment} drafts={drafts} query={query} />
        ) : (
          <WordText
            segment={segment}
            query={query}
            onSeek={seek}
            playhead={playhead}
          />
        )}
      </>
    ),
    [drafts, mode, playhead, reloadSpeakers, seek, speakers],
  )

  const startJob = useCallback(async () => {
    if (!imported || !optionId || !cloudConsent) {
      return
    }
    setCreating(true)
    setJobError(null)
    try {
      const job = await createJob({
        project_id: imported.project.id,
        media_asset_id: imported.media.media_asset_id,
        option_id: optionId,
        language: null, // ponytail: idioma autodetectado; selector de idioma en un corte posterior
        diarization,
        ...(profile ? { profile } : {}),
      })
      setJobId(job.id)
    } catch (error: unknown) {
      setJobError(describeJobError(error))
    } finally {
      setCreating(false)
    }
  }, [cloudConsent, diarization, imported, optionId, profile])

  const job = events.job
  const transcriptId = job?.state === 'COMPLETED' ? job.transcript_id : null

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
  }, [transcriptId, speakersVersion])

  const configDisabled = creating || jobId !== null

  const transcriptTools = transcriptId ? (
    <>
      <ContentSwitcher
        size="md"
        aria-label="Modo de la transcripción"
        selectedIndex={mode === 'read' ? 0 : 1}
        onChange={({ name }) => {
          setMode(name === 'edit' ? 'edit' : 'read')
        }}
      >
        <Switch name="read" text="Leer" />
        <Switch name="edit" text="Editar" />
      </ContentSwitcher>
      <AutosaveStatus drafts={drafts} />
      <ExportMenu transcriptId={transcriptId} />
    </>
  ) : null

  return (
    <Theme theme={scheme} className="voz-app">
      <AppHeader view={view} onNavigate={navigate} />

      <Content id="main-content" className="voz-content">
        <div hidden={view !== 'transcribir'}>
          <Grid narrow className={'voz-grid' + (jobId ? ' voz-grid--job' : '')}>
            <Column sm={4} md={8} lg={16}>
              <PageHeader view="transcribir" />
              <HealthStatus />
            </Column>

            <Column sm={4} md={8} lg={imported ? 16 : 10}>
              <NewProjectCard onImported={setImported} />
            </Column>

            {imported ? null : (
              <Column sm={4} md={8} lg={6}>
                <Panel titleId="privacy-title" title="Privacidad por diseño">
                  <p className="voz-field-note">
                    VOZ prioriza motores locales y funciona sin Internet una vez
                    estén instalados los modelos elegidos.
                  </p>
                  <UnorderedList>
                    <ListItem>Original inmutable</ListItem>
                    <ListItem>Procesamiento recuperable</ListItem>
                    <ListItem>Proveedores intercambiables</ListItem>
                  </UnorderedList>
                </Panel>
              </Column>
            )}

            {imported ? (
              <>
                <Column sm={4} md={8} lg={6} className="voz-col-config">
                  <Panel
                    titleId="options-title"
                    title="Configuración"
                    description="Motor, perfil y opciones de esta transcripción."
                  >
                    <Accordion isFlush>
                      <AccordionItem title="Motor de transcripción" open>
                        <TranscriptionOptionsSelector
                          refreshKey={modelsVersion}
                          mediaAssetId={imported.media.media_asset_id}
                          value={optionId}
                          onChange={setOptionId}
                          onCloudConsentChange={setCloudConsent}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                      <AccordionItem title="Perfil de calidad" open>
                        <ProfileSelector
                          value={profile}
                          onChange={setProfile}
                          language={null}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                      <AccordionItem title="Hablantes" open>
                        <DiarizationOptions
                          value={diarization}
                          onChange={setDiarization}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                      <AccordionItem title="Glosario del proyecto">
                        <GlossaryEditor
                          projectId={imported.project.id}
                          disabled={configDisabled}
                        />
                      </AccordionItem>
                    </Accordion>
                    {jobError ? (
                      <Notice
                        kind="error"
                        title="No se pudo crear la transcripción"
                        subtitle={jobError}
                      />
                    ) : null}
                    <div>
                      <Button
                        kind="primary"
                        size="lg"
                        disabled={
                          !optionId || !cloudConsent || creating || jobId !== null
                        }
                        onClick={() => void startJob()}
                      >
                        {creating ? 'Creando…' : 'Transcribir'}
                      </Button>
                    </div>
                  </Panel>
                </Column>

                <Column sm={4} md={8} lg={10}>
                  <div className="voz-workspace">
                    <Panel
                      titleId="audio-title"
                      title={imported.media.filename}
                      description="Original"
                    >
                      <AudioPlayer
                        mediaAssetId={imported.media.media_asset_id}
                        seekToMs={seekToMs}
                        seekNonce={seekNonce}
                        onTimeUpdate={handleTimeUpdate}
                      />
                      <Waveform
                        mediaAssetId={imported.media.media_asset_id}
                        currentMs={currentMs ?? 0}
                        onSeek={seek}
                      />
                    </Panel>

                    {jobId ? (
                      <>
                        <JobScreen
                          job={job}
                          loading={creating}
                          error={events.error}
                          onCancel={() => {
                            void cancelJob(jobId).catch(() => undefined)
                          }}
                        />
                        {transcriptId && job?.diarization_error_code ? (
                          <Notice
                            kind="warning"
                            role="status"
                            title="No se pudo separar a los hablantes"
                            subtitle={
                              '(' +
                              job.diarization_error_code +
                              '); la transcripción está completa.'
                            }
                          />
                        ) : null}
                        <SegmentList
                          transcriptId={transcriptId}
                          onSeek={seek}
                          currentMs={currentMs}
                          renderText={renderSegmentText}
                          reloadKey={speakersVersion}
                          onSegmentsLoaded={setLoadedSegments}
                          headerActions={transcriptTools}
                        />
                        {transcriptId ? (
                          <ReviewQueue
                            segments={loadedSegments}
                            onSelect={reviewSegment}
                          />
                        ) : null}
                        {transcriptId ? (
                          <SpeakersPanel
                            transcriptId={transcriptId}
                            onChanged={reloadSpeakers}
                          />
                        ) : null}
                      </>
                    ) : null}
                  </div>
                </Column>
              </>
            ) : null}
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

      <footer className="voz-footer">
        <span>VOZ 0.1.0</span>
        <span>Hecho para trabajar en local</span>
      </footer>
    </Theme>
  )
}
