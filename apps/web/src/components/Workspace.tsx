import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import {
  Breadcrumb,
  BreadcrumbItem,
  Column,
  ContentSwitcher,
  Grid,
  Switch,
} from '@carbon/react'

import { cancelJob, PROCESSABLE_STATES } from '../api/jobs'
import type { JobView, TranscriptSegment } from '../api/jobs'
import type { LibraryItem } from '../api/library'
import type { LibraryState } from '../hooks/useLibrary'
import { listSpeakers, rediarize, type RediarizeRequest, type Speaker } from '../api/speakers'
import { useJobEvents } from '../hooks/useJobEvents'
import { useJobPreview } from '../hooks/useJobPreview'
import { useSegmentDrafts } from '../hooks/useSegmentDrafts'
import { useSeek } from '../hooks/useSeek'
import { useI18n } from '../i18n/i18n'
import { createPlayhead } from '../lib/playhead'
import type { Sample, Turn } from '../lib/speakerTurns'
import { AutosaveStatus } from './AutosaveStatus'
import { Busy } from './Busy'
import { JobScreen } from './JobScreen'
import { LivePreview } from './LivePreview'
import { MediaPanel } from './MediaPanel'
import type { ImportResult } from './NewProjectCard'
import { Notice } from './Notice'
import { PropertiesPanel } from './PropertiesPanel'
import { ReviewQueue } from './ReviewQueue'
import { SegmentEditor } from './SegmentEditor'
import { SegmentList } from './SegmentList'
import { SegmentSpeakerSelect } from './SegmentSpeakerSelect'
import { SpeakerTimeline } from './SpeakerTimeline'
import { SpeakersPanel } from './SpeakersPanel'
import { WordText } from './WordText'

const ExportDialog = lazy(() => import('./ExportDialog').then((m) => ({ default: m.ExportDialog })))

interface WorkspaceProps {
  jobId: string
  /** Grabación recién importada en esta sesión (si coincide, evita esperar a la biblioteca). */
  seed: ImportResult | null
  /** Proyectos conocidos: dan el nombre y la duración al abrir por URL. */
  library: LibraryState
  onAdjust: (imported: ImportResult) => void
  onGoHome: () => void
  onOpenModels: () => void
}

/** Proyecto + medio de un trabajo, a partir de la sesión actual o de la biblioteca. */
function resolveImported(
  job: JobView,
  seed: ImportResult | null,
  items: readonly LibraryItem[] | undefined,
): ImportResult | null {
  if (seed !== null && seed.media.media_asset_id === job.media_asset_id) {
    return seed
  }
  const item = items?.find((candidate) => candidate.project_id === job.project_id)
  if (item === undefined) {
    return null
  }
  const media = item.media?.media_asset_id === job.media_asset_id ? item.media : null
  return {
    project: { id: item.project_id, name: item.name, created_at: item.created_at },
    media: {
      media_asset_id: job.media_asset_id,
      project_id: item.project_id,
      filename: media?.filename ?? item.name,
      media_type: null,
      duration_ms: media?.duration_ms ?? null,
      sha256: '',
    },
  }
}

/** `#/t/<jobId>`: progreso, transcripción, reproductor, propiedades, hablantes y revisión. */
export function Workspace({
  jobId,
  seed,
  library,
  onAdjust,
  onGoHome,
  onOpenModels,
}: WorkspaceProps) {
  const { t } = useI18n()
  const events = useJobEvents(jobId)
  const job = events.job
  const transcriptId = job?.transcript_id ?? null
  const processing = job !== null && PROCESSABLE_STATES.has(job.state)
  const completed = job?.state === 'COMPLETED'
  const diarizing = job?.state === 'DIARIZING' || job?.state === 'MERGING'
  const preview = useJobPreview(jobId, processing && transcriptId === null)

  const [mode, setMode] = useState<'read' | 'edit'>('read')
  const drafts = useSegmentDrafts()
  const { seekToMs, seekNonce, stopAtMs, seek } = useSeek()
  const [currentMs, setCurrentMs] = useState<number | undefined>(undefined)
  const playhead = useMemo(() => createPlayhead(), [])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [speakersVersion, setSpeakersVersion] = useState(0)
  const [loadedSegments, setLoadedSegments] = useState<TranscriptSegment[]>([])
  const [speakerFilter, setSpeakerFilter] = useState<string | null>(null)
  const [focus, setFocus] = useState<{ segmentId: string; nonce: number } | null>(null)
  const [recalcJobId, setRecalcJobId] = useState<string | null>(null)
  const recalc = useJobEvents(recalcJobId)

  // La duración de una grabación abierta sin medir la mide la forma de onda.
  const [measured, setMeasured] = useState<{ id: string; ms: number } | null>(null)
  const baseImported = job === null ? null : resolveImported(job, seed, library.phase === 'ready' ? library.items : undefined)
  const imported =
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

  // Recálculo de hablantes: el trabajo que devuelve el servidor se sigue como cualquier otro.
  const recalcState = recalcJobId === null ? null : recalc.job?.state
  const recalcRunning =
    recalcJobId !== null &&
    (recalc.job === null ? recalc.error === null : PROCESSABLE_STATES.has(recalc.job.state))
  const recalcFailed = recalcState === 'FAILED' || recalcState === 'CANCELLED'
  const recalcDone = recalcState === 'COMPLETED'
  const recalcPct =
    recalc.job === null
      ? null
      : Math.round(100 * (recalc.job.stage_progress ?? recalc.job.progress))

  const reloadSpeakers = useCallback(() => {
    setSpeakersVersion((version) => version + 1)
  }, [])
  const reloadKey = speakersVersion * 4 + (completed ? 1 : 0) + (recalcDone ? 2 : 0)

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
  }, [transcriptId, speakersVersion, completed, recalcDone])

  const handleTimeUpdate = useCallback(
    (ms: number) => {
      setCurrentMs(ms)
      playhead.set(ms)
    },
    [playhead],
  )

  /** Lleva el audio y la lista al segmento: seek + reproducir + scroll + resaltado. */
  const focusSegment = useCallback(
    (segmentId: string, startMs: number, stopMs?: number) => {
      const segment = loadedSegments.find((item) => item.id === segmentId)
      if (segment !== undefined) {
        setSpeakerFilter((current) =>
          current !== null && segment.speaker_id !== current ? null : current,
        )
      }
      seek(startMs, stopMs)
      setFocus((previous) => ({ segmentId, nonce: (previous?.nonce ?? 0) + 1 }))
    },
    [loadedSegments, seek],
  )
  const reviewSegment = useCallback(
    (segment: TranscriptSegment) => {
      focusSegment(segment.id, segment.start_ms)
    },
    [focusSegment],
  )
  const jumpToTurn = useCallback(
    (turn: Turn) => {
      focusSegment(turn.segment_id, turn.start_ms)
    },
    [focusSegment],
  )
  const playSample = useCallback(
    (sample: Sample) => {
      focusSegment(sample.segment_id, sample.start_ms, sample.end_ms)
    },
    [focusSegment],
  )

  const startRecalc = useCallback(
    async (request: RediarizeRequest) => {
      if (transcriptId === null) {
        return
      }
      const created = await rediarize(transcriptId, request)
      setRecalcJobId(created.id)
    },
    [transcriptId],
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

  if (job === null) {
    return (
      <Grid narrow className="voz-grid">
        <Column sm={4} md={8} lg={16}>
          {events.error !== null ? (
            <Notice
              kind="error"
              title={t('work.notfound.title')}
              subtitle={t('work.notfound.body')}
              action={{ label: t('work.notfound.back'), onClick: onGoHome }}
            />
          ) : (
            <div role="status">
              <Busy description={t('work.loading')} />
            </div>
          )}
        </Column>
      </Grid>
    )
  }

  if (imported === null) {
    return (
      <Grid narrow className="voz-grid">
        <Column sm={4} md={8} lg={16}>
          {library.phase === 'ready' ? (
            <Notice
              kind="error"
              title={t('work.notfound.title')}
              subtitle={t('work.notfound.body')}
              action={{ label: t('work.notfound.back'), onClick: onGoHome }}
            />
          ) : (
            <div role="status">
              <Busy description={t('work.loading')} />
            </div>
          )}
        </Column>
      </Grid>
    )
  }

  const speakersPending = (transcriptId !== null && diarizing) || recalcRunning
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

  return (
    <Grid narrow className="voz-grid voz-grid--job">
      <Column sm={4} md={8} lg={16}>
        <div className="voz-crumbs">
          <Breadcrumb aria-label={t('nav.crumbs')} noTrailingSlash>
            <BreadcrumbItem href="#/">{t('work.crumb.home')}</BreadcrumbItem>
            <BreadcrumbItem isCurrentPage>{imported.project.name}</BreadcrumbItem>
          </Breadcrumb>
        </div>
        <JobScreen
          job={job}
          error={events.error}
          onCancel={() => {
            void cancelJob(jobId).catch(() => undefined)
          }}
          onAdjust={() => {
            onAdjust(imported)
          }}
        />
        {transcriptId && job.diarization_error_code ? (
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
              reloadKey={reloadKey}
              onSegmentsLoaded={setLoadedSegments}
              headerActions={transcriptTools}
              speakerFilter={speakerFilter}
              onClearFilter={() => {
                setSpeakerFilter(null)
              }}
              focus={focus}
              notice={
                diarizing ? (
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
            imported={imported}
            titleId="audio-title"
            title={t('work.playback.title')}
            seekToMs={seekToMs}
            seekNonce={seekNonce}
            stopAtMs={stopAtMs}
            currentMs={currentMs ?? 0}
            onTimeUpdate={handleTimeUpdate}
            onSeek={seek}
            onDuration={handleDuration}
          >
            {transcriptId ? (
              <SpeakerTimeline
                segments={loadedSegments}
                speakers={speakers}
                durationMs={imported.media.duration_ms}
                playhead={playhead}
                onSeek={seek}
                speakersPending={speakersPending}
                selectedId={speakerFilter}
              />
            ) : null}
          </MediaPanel>
        </div>
      </Column>

      <Column sm={4} md={8} lg={5}>
        <div className="voz-workspace">
          <PropertiesPanel
            imported={imported}
            job={job}
            tools={
              transcriptId && completed ? (
                <Suspense fallback={<Busy description={t('common.loading')} />}>
                  <ExportDialog transcriptId={transcriptId} />
                </Suspense>
              ) : null
            }
          />
          {transcriptId ? (
            <SpeakersPanel
              transcriptId={transcriptId}
              onChanged={reloadSpeakers}
              pending={speakersPending && !recalcRunning}
              segments={loadedSegments}
              playhead={playhead}
              filterId={speakerFilter}
              onFilter={setSpeakerFilter}
              onJump={jumpToTurn}
              onSample={playSample}
              refreshKey={(completed ? 1 : 0) + (recalcDone ? 2 : 0)}
              recalc={{
                phase: recalcRunning ? 'running' : recalcFailed ? 'failed' : 'idle',
                pct: recalcPct,
                error: recalc.job?.error_code ?? null,
              }}
              {...(completed ? { onRecalculate: startRecalc } : {})}
              onOpenModels={onOpenModels}
            />
          ) : null}
          {transcriptId ? (
            <ReviewQueue segments={loadedSegments} onSelect={reviewSegment} />
          ) : null}
        </div>
      </Column>
    </Grid>
  )
}
