import { useCallback, useEffect, useMemo, useState } from 'react'

import { cancelJob, createJob, JobApiError } from './api/jobs'
import type { TranscriptSegment } from './api/jobs'
import { listSpeakers, type Speaker } from './api/speakers'
import { AudioPlayer } from './components/AudioPlayer'
import { AutosaveStatus } from './components/AutosaveStatus'
import {
  DiarizationOptions,
  type DiarizationRequest,
} from './components/DiarizationOptions'
import { ExportMenu } from './components/ExportMenu'
import { HealthStatus } from './components/HealthStatus'
import { JobScreen } from './components/JobScreen'
import { ModelManager } from './components/ModelManager'
import { NewProjectCard, type ImportResult } from './components/NewProjectCard'
import { SegmentEditor } from './components/SegmentEditor'
import { SegmentList } from './components/SegmentList'
import { SegmentSpeakerSelect } from './components/SegmentSpeakerSelect'
import { SpeakersPanel } from './components/SpeakersPanel'
import { TranscriptionOptionsSelector } from './components/TranscriptionOptionsSelector'
import { Waveform } from './components/Waveform'
import { WordText } from './components/WordText'
import { useJobEvents } from './hooks/useJobEvents'
import { useSegmentDrafts } from './hooks/useSegmentDrafts'
import { useSeek } from './hooks/useSeek'
import { createPlayhead } from './lib/playhead'

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
      <span />
    </span>
  )
}

function LockIcon() {
  return (
    <svg
      aria-hidden="true"
      className="lock-icon"
      viewBox="0 0 24 24"
      fill="none"
    >
      <path d="M7.5 10V7.5a4.5 4.5 0 0 1 9 0V10" />
      <rect x="5" y="10" width="14" height="11" rx="3" />
      <path d="M12 14.5v2" />
    </svg>
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
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [speakersVersion, setSpeakersVersion] = useState(0)
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
    if (!imported || !optionId) {
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
      })
      setJobId(job.id)
    } catch (error: unknown) {
      setJobError(describeJobError(error))
    } finally {
      setCreating(false)
    }
  }, [diarization, imported, optionId])

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#main" aria-label="VOZ, ir al inicio">
          <BrandMark />
          <span>VOZ</span>
        </a>
        <a className="topbar-link" href="#modelos">
          Modelos
        </a>
        <div className="privacy-badge">
          <LockIcon />
          <span>Local y privado</span>
        </div>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="eyebrow">
            <span className="eyebrow-dot" aria-hidden="true" />
            Tu audio. Tus palabras. Tu equipo.
          </div>
          <h1 id="hero-title">
            Escucha menos.
            <br />
            <span>Encuentra más.</span>
          </h1>
          <p className="hero-copy">
            VOZ es tu espacio local para convertir clases, entrevistas y
            grabaciones largas en texto editable, sin entregar tus archivos a
            terceros.
          </p>
        </section>

        <section className="workspace-grid" aria-label="Inicio de VOZ">
          <div className="workflow">
            <NewProjectCard onImported={setImported} />

            {imported ? (
              <article className="import-card options-card" aria-label="Transcribir">
                <div className="card-heading">
                  <div>
                    <p className="section-kicker">TRANSCRIBIR</p>
                    <h2>Elige el motor</h2>
                  </div>
                </div>
                <TranscriptionOptionsSelector
                  refreshKey={modelsVersion}
                  value={optionId}
                  onChange={setOptionId}
                  disabled={creating || jobId !== null}
                />
                <DiarizationOptions
                  value={diarization}
                  onChange={setDiarization}
                  disabled={creating || jobId !== null}
                />
                {jobError ? (
                  <p className="options-error" role="alert">
                    {jobError}
                  </p>
                ) : null}
                <div className="import-actions">
                  <button
                    type="button"
                    className="import-submit"
                    disabled={!optionId || creating || jobId !== null}
                    onClick={() => void startJob()}
                  >
                    {creating ? 'Creando…' : 'Transcribir'}
                  </button>
                </div>
              </article>
            ) : null}

            {imported ? (
              <article className="import-card audio-card" aria-label="Original">
                <div className="card-heading">
                  <div>
                    <p className="section-kicker">ORIGINAL</p>
                    <h2>{imported.media.filename}</h2>
                  </div>
                </div>
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
              </article>
            ) : null}

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
                {transcriptId ? (
                  <div className="transcript-tools">
                    <div
                      className="mode-toggle"
                      role="group"
                      aria-label="Modo de la transcripción"
                    >
                      <button
                        type="button"
                        aria-pressed={mode === 'read'}
                        onClick={() => {
                          setMode('read')
                        }}
                      >
                        Leer
                      </button>
                      <button
                        type="button"
                        aria-pressed={mode === 'edit'}
                        onClick={() => {
                          setMode('edit')
                        }}
                      >
                        Editar
                      </button>
                    </div>
                    <AutosaveStatus drafts={drafts} />
                    <ExportMenu transcriptId={transcriptId} />
                  </div>
                ) : null}
                {transcriptId && job?.diarization_error_code ? (
                  <p className="options-error" role="status">
                    No se pudo separar a los hablantes (
                    {job.diarization_error_code}); la transcripción está completa.
                  </p>
                ) : null}
                {transcriptId ? (
                  <SpeakersPanel
                    transcriptId={transcriptId}
                    onChanged={reloadSpeakers}
                  />
                ) : null}
                <SegmentList
                  transcriptId={transcriptId}
                  onSeek={seek}
                  currentMs={currentMs}
                  renderText={renderSegmentText}
                  reloadKey={speakersVersion}
                />
              </>
            ) : null}
          </div>

          <aside className="status-column" aria-label="Estado de la aplicación">
            <HealthStatus />

            <article className="promise-card">
              <p className="section-kicker">PRIVACIDAD POR DISEÑO</p>
              <h2>Lo tuyo se queda contigo.</h2>
              <p>
                VOZ prioriza motores locales y funciona sin Internet una vez
                estén instalados los modelos elegidos.
              </p>
              <ul>
                <li>
                  <span aria-hidden="true">01</span>
                  Original inmutable
                </li>
                <li>
                  <span aria-hidden="true">02</span>
                  Procesamiento recuperable
                </li>
                <li>
                  <span aria-hidden="true">03</span>
                  Proveedores intercambiables
                </li>
              </ul>
            </article>
          </aside>

          <div id="modelos" className="models-slot">
            <ModelManager onModelsChanged={refreshModels} />
          </div>
        </section>
      </main>

      <footer>
        <span>VOZ 0.1.0</span>
        <span>Hecho para trabajar en local</span>
      </footer>
    </div>
  )
}
