import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import {
  Button,
  FileUploaderDropContainer,
  FileUploaderItem,
  Form,
  ProgressBar,
  Stack,
  Tag,
  TextInput,
} from '@carbon/react'
import { Renew } from '@carbon/icons-react'

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
import { Notice } from './Notice'
import { Panel } from './Panel'
import './NewProjectCard.scss'

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
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  const createdProject = useRef<Project | null>(null)
  const controller = useRef<AbortController | null>(null)

  const titleId = useId()
  const nameId = useId()

  useEffect(() => {
    return () => {
      controller.current?.abort()
    }
  }, [])

  const busy = phase.kind === 'creating' || phase.kind === 'uploading'
  const trimmedName = name.trim()
  const canSubmit = !busy && trimmedName.length > 0 && file !== null

  const acceptFiles = useCallback((added: File[]) => {
    const first = added[0]
    if (!first) {
      return
    }
    setFile(first)
    createdProject.current = null
    setNotice(
      added.length > 1
        ? 'Solo se importa un archivo a la vez; se tomó "' + first.name + '".'
        : null,
    )
    setPhase((current) => (current.kind === 'done' ? { kind: 'idle' } : current))
  }, [])

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

  return (
    <Panel
      titleId={titleId}
      title={phase.kind === 'done' ? 'Grabación importada' : 'Importar grabación'}
      description={
        phase.kind === 'done'
          ? undefined
          : 'El archivo se procesa solo en este equipo y el original siempre se conserva intacto.'
      }
    >
      {phase.kind === 'done' ? (
        <Stack gap={5}>
          <Notice
            kind="success"
            title="Importación completa"
            subtitle={phase.result.media.filename}
          />
          <dl className="voz-meta">
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
                <Tag type="gray" size="sm">
                  {phase.result.media.sha256.slice(0, 8)}
                </Tag>
              </dd>
            </div>
          </dl>
          <div>
            <Button kind="tertiary" size="md" renderIcon={Renew} onClick={reset}>
              Importar otra grabación
            </Button>
          </div>
        </Stack>
      ) : (
        <Form onSubmit={handleSubmit} noValidate>
          <Stack gap={6}>
            <TextInput
              id={nameId}
              labelText="Nombre del proyecto"
              value={name}
              onChange={(event) => {
                setName(event.target.value)
              }}
              disabled={busy}
              required
              autoComplete="off"
              invalid={trimmedName.length === 0}
              invalidText="Escribe un nombre para el proyecto."
            />

            <div className="voz-dropzone">
              <FileUploaderDropContainer
                labelText="Suelta aquí tu audio o video, o haz clic para elegir un archivo"
                disabled={busy}
                multiple
                onAddFiles={(_event, { addedFiles }) => {
                  acceptFiles(addedFiles)
                }}
              />
            </div>
            <p className="voz-field-note">
              Cualquier formato compatible con FFmpeg.
            </p>

            {file ? (
              <FileUploaderItem
                name={file.name}
                status={busy ? 'uploading' : 'edit'}
                size="lg"
                iconDescription="Quitar archivo"
                disabled={busy}
                onDelete={() => {
                  setFile(null)
                  setNotice(null)
                  createdProject.current = null
                }}
              />
            ) : null}
            {file ? (
              <p className="voz-field-note">
                {'Archivo listo · ' + formatBytes(file.size)}
              </p>
            ) : null}

            {notice ? <Notice kind="info" title={notice} /> : null}

            {busy ? (
              <ProgressBar
                label="Progreso de la importación"
                {...(phase.kind === 'uploading'
                  ? { value: Math.round(phase.fraction * 100), max: 100 }
                  : {})}
                helperText={
                  phase.kind === 'creating'
                    ? 'Creando proyecto…'
                    : 'Subiendo ' + Math.round(phase.fraction * 100) + ' %'
                }
              />
            ) : null}

            {phase.kind === 'error' ? (
              <Notice
                kind="error"
                title="No se pudo importar"
                subtitle={phase.message}
                action={{
                  label: 'Reintentar',
                  disabled: !canSubmit,
                  onClick: () => void runImport(),
                }}
              />
            ) : null}

            <div>
              <Button type="submit" kind="primary" disabled={!canSubmit}>
                {busy ? 'Importando…' : 'Crear proyecto e importar'}
              </Button>
            </div>
          </Stack>
        </Form>
      )}
    </Panel>
  )
}
