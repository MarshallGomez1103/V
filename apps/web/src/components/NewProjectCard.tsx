import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from 'react'

import { isAbortError } from '../api/errors'
import {
  uploadMedia,
  UploadError,
  describeUploadError,
  type MediaAssetSummary,
} from '../api/media'
import {
  createProject,
  ProjectError,
  describeProjectError,
  type Project,
} from '../api/projects'

export interface ImportResult {
  project: Project
  media: MediaAssetSummary
}

export interface NewProjectCardProps {
  onImported: (result: ImportResult) => void
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'creating' }
  | { kind: 'uploading'; fraction: number }
  | { kind: 'error'; message: string }
  | { kind: 'done'; result: ImportResult }

const waveformHeights = [28, 52, 36, 68, 42, 78, 54, 32, 64, 86, 48, 70, 38, 58, 30]

function defaultProjectName(): string {
  return 'Grabación ' + new Date().toLocaleDateString('es', { dateStyle: 'short' })
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return bytes + ' B'
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return value.toFixed(value >= 10 ? 0 : 1) + ' ' + units[unit]
}

function formatDuration(durationMs: number | null): string {
  if (durationMs === null) {
    return '—'
  }
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours > 0
    ? hours + ':' + pad(minutes) + ':' + pad(seconds)
    : pad(minutes) + ':' + pad(seconds)
}

function describeMediaType(mediaType: string | null): string {
  if (mediaType === null) {
    return 'Desconocido'
  }
  if (mediaType === 'audio') {
    return 'Audio'
  }
  if (mediaType === 'video') {
    return 'Video'
  }
  return mediaType
}

function describeError(error: unknown): string {
  if (error instanceof UploadError) {
    return describeUploadError(error.code)
  }
  if (error instanceof ProjectError) {
    return describeProjectError(error.code)
  }
  return 'No se pudo importar el archivo.'
}

export function NewProjectCard({ onImported }: NewProjectCardProps) {
  const [name, setName] = useState(defaultProjectName)
  const [file, setFile] = useState<File | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)
  const createdProject = useRef<Project | null>(null)
  const controller = useRef<AbortController | null>(null)

  const titleId = useId()
  const nameId = useId()
  const descriptionId = useId()
  const fileInputId = useId()

  useEffect(() => {
    return () => {
      controller.current?.abort()
    }
  }, [])

  const busy = phase.kind === 'creating' || phase.kind === 'uploading'
  const trimmedName = name.trim()
  const canSubmit = !busy && trimmedName.length > 0 && file !== null

  const acceptFiles = useCallback((list: FileList | null) => {
    if (!list || list.length === 0) {
      return
    }
    const first = list[0]
    if (!first) {
      return
    }
    setFile(first)
    createdProject.current = null
    setNotice(
      list.length > 1
        ? 'Solo se importa un archivo a la vez; se tomó "' + first.name + '".'
        : null,
    )
    setPhase((current) => (current.kind === 'done' ? { kind: 'idle' } : current))
  }, [])

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    acceptFiles(event.target.files)
    event.target.value = ''
  }

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current += 1
    if (!busy) {
      setDragActive(true)
    }
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = busy ? 'none' : 'copy'
    }
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) {
      setDragActive(false)
    }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current = 0
    setDragActive(false)
    if (!busy) {
      acceptFiles(event.dataTransfer.files)
    }
  }

  const runImport = async () => {
    if (!file || trimmedName.length === 0) {
      return
    }

    const abort = new AbortController()
    controller.current = abort

    try {
      let project = createdProject.current
      if (!project) {
        setPhase({ kind: 'creating' })
        project = await createProject(trimmedName, abort.signal)
        createdProject.current = project
      }

      setPhase({ kind: 'uploading', fraction: 0 })
      const media = await uploadMedia(project.id, file, {
        signal: abort.signal,
        onProgress: (fraction) => {
          setPhase({ kind: 'uploading', fraction })
        },
      })

      const result: ImportResult = { project, media }
      setPhase({ kind: 'done', result })
      onImported(result)
    } catch (error: unknown) {
      if (isAbortError(error) || (error instanceof UploadError && error.code === 'aborted')) {
        return
      }
      setPhase({ kind: 'error', message: describeError(error) })
    } finally {
      if (controller.current === abort) {
        controller.current = null
      }
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (canSubmit) {
      void runImport()
    }
  }

  const reset = () => {
    setFile(null)
    setNotice(null)
    createdProject.current = null
    setName(defaultProjectName())
    setPhase({ kind: 'idle' })
  }

  const dropZoneClass =
    'drop-zone' +
    (dragActive ? ' drop-zone--active' : '') +
    (file ? ' drop-zone--filled' : '')

  return (
    <article className="import-card" aria-labelledby={titleId}>
      <div className="card-heading">
        <div>
          <p className="section-kicker">NUEVO PROYECTO</p>
          <h2 id={titleId}>Trae una grabación</h2>
        </div>
      </div>

      {phase.kind === 'done' ? (
        <div className="import-summary" role="status" aria-live="polite">
          <h3>Importación completa</h3>
          <dl className="import-summary-list">
            <div>
              <dt>Proyecto</dt>
              <dd>{phase.result.project.name}</dd>
            </div>
            <div>
              <dt>Archivo</dt>
              <dd>{phase.result.media.filename}</dd>
            </div>
            <div>
              <dt>Duración</dt>
              <dd>{formatDuration(phase.result.media.duration_ms)}</dd>
            </div>
            <div>
              <dt>Tipo</dt>
              <dd>{describeMediaType(phase.result.media.media_type)}</dd>
            </div>
            <div>
              <dt>Huella</dt>
              <dd>
                <code>{phase.result.media.sha256.slice(0, 8)}</code>
              </dd>
            </div>
          </dl>
          <button type="button" onClick={reset}>
            Importar otra grabación
          </button>
        </div>
      ) : (
        <form className="import-form" onSubmit={handleSubmit} noValidate>
          <div className="import-field">
            <label htmlFor={nameId}>Nombre del proyecto</label>
            <input
              id={nameId}
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value)
              }}
              disabled={busy}
              required
              autoComplete="off"
              aria-invalid={trimmedName.length === 0}
            />
          </div>

          <div
            className={dropZoneClass}
            aria-describedby={descriptionId}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="wave-preview" aria-hidden="true">
              {waveformHeights.map((height, index) => (
                <span key={height + '-' + index} style={{ height: height + '%' }} />
              ))}
            </div>

            {file ? (
              <>
                <h3>Archivo listo</h3>
                <p id={descriptionId} className="import-file">
                  <span className="import-file-name">{file.name}</span>
                  <span className="import-file-size">{formatBytes(file.size)}</span>
                </p>
              </>
            ) : (
              <>
                <h3>Suelta aquí tu audio o video</h3>
                <p id={descriptionId}>
                  Cualquier formato compatible con FFmpeg. El archivo se procesa
                  solo en este equipo.
                </p>
              </>
            )}

            <input
              ref={fileInputRef}
              id={fileInputId}
              className="import-file-input"
              type="file"
              accept="audio/*,video/*"
              aria-label="Archivo de audio o video"
              onChange={handleInputChange}
              disabled={busy}
              hidden
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              {file ? 'Cambiar archivo' : 'Importar archivo'}
            </button>
            <small>El archivo original siempre se conservará intacto.</small>
          </div>

          {notice ? (
            <p className="import-notice" role="status">
              {notice}
            </p>
          ) : null}

          {phase.kind === 'creating' || phase.kind === 'uploading' ? (
            <div className="import-progress" role="status" aria-live="polite">
              <progress
                value={phase.kind === 'uploading' ? phase.fraction : undefined}
                max={1}
                aria-label="Progreso de la importación"
              />
              <span>
                {phase.kind === 'creating'
                  ? 'Creando proyecto…'
                  : 'Subiendo ' + Math.round(phase.fraction * 100) + ' %'}
              </span>
            </div>
          ) : null}

          {phase.kind === 'error' ? (
            <div className="import-error" role="alert">
              <p>{phase.message}</p>
              <button type="button" onClick={() => void runImport()} disabled={!canSubmit}>
                Reintentar
              </button>
            </div>
          ) : null}

          <div className="import-actions">
            <button type="submit" className="import-submit" disabled={!canSubmit}>
              {busy ? 'Importando…' : 'Crear proyecto e importar'}
            </button>
          </div>
        </form>
      )}
    </article>
  )
}
