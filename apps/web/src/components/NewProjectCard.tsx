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
  TextInput,
} from '@carbon/react'

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
import { localeOf, useI18n, type Lang, type Translate } from '../i18n/i18n'
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

function defaultProjectName(t: Translate, lang: Lang): string {
  return t('import.defaultName', {
    date: new Date().toLocaleDateString(localeOf(lang), { dateStyle: 'short' }),
  })
}

/** Tamaño binario legible del archivo elegido (KB, MB…). */
function formatFileSize(bytes: number): string {
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

function describeError(error: unknown, t: Translate): string {
  if (error instanceof UploadError) {
    return describeUploadError(error.code)
  }
  if (error instanceof ProjectError) {
    return describeProjectError(error.code)
  }
  return t('err.upload.generic')
}

export function NewProjectCard({ onImported }: NewProjectCardProps) {
  const { t, lang } = useI18n()
  const [name, setName] = useState(() => defaultProjectName(t, lang))
  const [nameEdited, setNameEdited] = useState(false)
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

  // El nombre sugerido sigue al idioma mientras nadie lo haya tocado.
  const suggested = defaultProjectName(t, lang)
  const shownName = nameEdited ? name : suggested

  const busy = phase.kind === 'creating' || phase.kind === 'uploading'
  const trimmedName = shownName.trim()
  const canSubmit = !busy && trimmedName.length > 0 && file !== null

  const acceptFiles = useCallback(
    (added: File[]) => {
      const first = added[0]
      if (!first) {
        return
      }
      setFile(first)
      createdProject.current = null
      setNotice(added.length > 1 ? t('import.multiple', { name: first.name }) : null)
      setPhase({ kind: 'idle' })
    },
    [t],
  )

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

      setPhase({ kind: 'idle' })
      onImported({ project, media })
    } catch (error: unknown) {
      if (isAbortError(error) || (error instanceof UploadError && error.code === 'aborted')) {
        return
      }
      setPhase({ kind: 'error', message: describeError(error, t) })
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

  return (
    <Panel titleId={titleId} title={t('import.title')} description={t('import.description')}>
      <Form onSubmit={handleSubmit} noValidate>
        <Stack gap={6}>
          <div className="voz-dropzone">
            <FileUploaderDropContainer
              labelText={t('import.drop')}
              disabled={busy}
              multiple
              onAddFiles={(_event, { addedFiles }) => {
                acceptFiles(addedFiles)
              }}
            />
            <p className="voz-field-note">{t('import.formats')}</p>
          </div>

          {file ? (
            <div className="voz-importfile">
              <FileUploaderItem
                name={file.name}
                status={busy ? 'uploading' : 'edit'}
                size="lg"
                iconDescription={t('import.removeFile')}
                disabled={busy}
                onDelete={() => {
                  setFile(null)
                  setNotice(null)
                  createdProject.current = null
                }}
              />
              <p className="voz-field-note">
                {t('import.fileReady', { size: formatFileSize(file.size) })}
              </p>
            </div>
          ) : null}

          <TextInput
            id={nameId}
            labelText={t('import.projectName')}
            helperText={t('import.projectName.help')}
            value={shownName}
            onChange={(event) => {
              setName(event.target.value)
              setNameEdited(true)
            }}
            disabled={busy}
            required
            autoComplete="off"
            invalid={trimmedName.length === 0}
            invalidText={t('import.projectName.invalid')}
          />

          {notice ? <Notice kind="info" title={notice} /> : null}

          {busy ? (
            <ProgressBar
              label={t('import.progress.label')}
              {...(phase.kind === 'uploading'
                ? { value: Math.round(phase.fraction * 100), max: 100 }
                : {})}
              helperText={
                phase.kind === 'creating'
                  ? t('import.creating')
                  : t('import.uploading', { pct: Math.round(phase.fraction * 100) })
              }
            />
          ) : null}

          {phase.kind === 'error' ? (
            <Notice
              kind="error"
              title={t('import.error.title')}
              subtitle={phase.message}
              action={{
                label: t('common.retry'),
                disabled: !canSubmit,
                onClick: () => void runImport(),
              }}
            />
          ) : null}

          <div>
            <Button type="submit" kind="primary" disabled={!canSubmit}>
              {busy ? t('import.submitting') : t('import.submit')}
            </Button>
            {file === null ? (
              <p className="voz-field-note voz-importfile__why">{t('import.submit.why')}</p>
            ) : null}
          </div>
        </Stack>
      </Form>
    </Panel>
  )
}
