import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Button, Modal, ProgressBar, Select, SelectItem, TextInput } from '@carbon/react'

import {
  createCustomModelUpload, customModelError, discardCustomModelUpload,
  installCustomModel, previewCustomModel, previewCustomModelUpload,
  selectFolderFiles, uploadCustomModelFile,
  type CustomModelMetadata, type CustomModelPreview,
} from '../api/customModels'
import { isAbortError } from '../api/errors'
import { cancelModelTask, capabilityLabel, ModelApiError, type TaskView } from '../api/models'
import { isActiveTask, useModelTasks } from '../hooks/useModelTasks'
import { useI18n } from '../i18n/i18n'
import { formatBytes } from '../lib/formatBytes'
import { Busy } from './Busy'
import { Notice } from './Notice'
import './AddModelDialog.scss'

export interface AddModelDialogProps {
  onClose: () => void
  onCompleted: () => void
  availableEngines?: readonly string[]
}

const FAMILIES: Record<string, readonly string[]> = {
  'faster-whisper': ['ctranslate2'],
  'whisper-cpp': ['ggml'],
  'sherpa-onnx-tts': ['kitten', 'kokoro', 'vits', 'matcha'],
  'sherpa-onnx-asr': ['whisper', 'nemo_transducer'],
}
type Phase = 'form' | 'uploading' | 'preparing' | 'preview' | 'starting' | 'job'
type Source = 'folder' | 'huggingface' | 'url'

export function AddModelDialog({ onClose, onCompleted, availableEngines }: AddModelDialogProps) {
  const { t } = useI18n()
  const id = useId()
  const opener = useRef(document.activeElement)
  const mounted = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const uploadId = useRef<string | null>(null)
  const jobRef = useRef<TaskView | null>(null)
  const notified = useRef<string | null>(null)
  const [manual, setManual] = useState(false)
  const [sourceType, setSourceType] = useState<Source>('folder')
  const [source, setSource] = useState('')
  const [revision, setRevision] = useState('main')
  const [engine, setEngine] = useState('')
  const [family, setFamily] = useState('')
  const [name, setName] = useState('')
  const [license, setLicense] = useState('')
  const [acoustic, setAcoustic] = useState('')
  const [vocoder, setVocoder] = useState('')
  const [tokens, setTokens] = useState('tokens.txt')
  const [encoder, setEncoder] = useState('')
  const [decoder, setDecoder] = useState('')
  const [joiner, setJoiner] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [phase, setPhase] = useState<Phase>('form')
  const [preview, setPreview] = useState<CustomModelPreview | null>(null)
  const [initialTask, setInitialTask] = useState<TaskView | null>(null)
  const [doneBytes, setDoneBytes] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [cleanupFailed, setCleanupFailed] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const { tasks, track, error: pollingError, refresh } = useModelTasks()
  const task = tasks.find((item) => item.id === initialTask?.id) ?? initialTask
  const active = task !== null && isActiveTask(task)
  const folderSupported = 'webkitdirectory' in document.createElement('input')
  const selection = useMemo(() => {
    if (!files.length || !engine) return null
    try { return selectFolderFiles(files, engine) } catch { return null }
  }, [files, engine])

  const cleanupUpload = useCallback(async () => {
    const pending = uploadId.current
    if (pending === null) return true
    try {
      await discardCustomModelUpload(pending)
      if (uploadId.current === pending) uploadId.current = null
      if (mounted.current) setCleanupFailed(false)
      return true
    } catch {
      if (mounted.current) setCleanupFailed(true)
      return false
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    const original = opener.current
    return () => {
      mounted.current = false
      controller.current?.abort()
      const current = jobRef.current
      if (current !== null && isActiveTask(current)) {
        void cancelModelTask(current.id).catch(() => undefined).finally(() => { void cleanupUpload() })
      } else { void cleanupUpload() }
      if (original instanceof HTMLElement && original.isConnected) original.focus()
    }
  }, [cleanupUpload])

  useEffect(() => {
    jobRef.current = task
    if (task === null || isActiveTask(task) || notified.current === task.id) return
    notified.current = task.id
    void cleanupUpload()
    if (task.state === 'completed') onCompleted()
  }, [task, onCompleted, cleanupUpload])

  const failureText = (caught: unknown) => caught instanceof ModelApiError
    ? customModelError(caught.code).message : t('addModel.error')

  const selectedSourceType = manual ? sourceType
    : /^(?:https:\/\/huggingface\.co\/)?[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(source.trim()) ? 'huggingface' : 'url'

  const review = async () => {
    if (phase !== 'form') return
    setError(null)
    setPhase('preparing')
    const aborter = new AbortController()
    controller.current = aborter
    if (!await cleanupUpload()) { if (mounted.current) setPhase('form'); return }
    if (aborter.signal.aborted || !mounted.current) return
    const metadata: CustomModelMetadata = {
      engine: manual ? engine : 'auto', family: manual ? family : '',
      display_name: name.trim(), license: license.trim() || 'unknown',
      file_roles: !manual ? {} : engine === 'sherpa-onnx-asr'
        ? { encoder: encoder.trim(), decoder: decoder.trim(), tokens: tokens.trim(), ...(family === 'nemo_transducer' ? { joiner: joiner.trim() } : {}) }
        : family === 'matcha' ? { acoustic_model: acoustic.trim(), vocoder: vocoder.trim(), tokens: tokens.trim() } : {},
    }
    try {
      let prepared: CustomModelPreview
      if (selectedSourceType === 'folder') {
        if (selection === null) return
        setPhase('uploading')
        setDoneBytes(0)
        const receipt = await createCustomModelUpload({ ...metadata,
          files: selection.files.map(({ name: filename, file }) => ({ name: filename, size_bytes: file.size })),
        }, aborter.signal)
        uploadId.current = receipt.id
        if (aborter.signal.aborted || !mounted.current) { await cleanupUpload(); return }
        let transferred = 0
        for (const [index, selected] of selection.files.entries()) {
          const before = transferred
          await uploadCustomModelFile(receipt.id, index, selected.file, {
            signal: aborter.signal, onProgress: (bytes) => { setDoneBytes(before + bytes) },
          })
          transferred += selected.file.size
        }
        setPhase('preparing')
        prepared = await previewCustomModelUpload(receipt.id, aborter.signal)
      } else {
        setPhase('preparing')
        prepared = await previewCustomModel({ ...metadata, source_type: selectedSourceType, source: source.trim(), revision: revision.trim() || 'main' }, aborter.signal)
      }
      if (!aborter.signal.aborted && mounted.current) { setPreview(prepared); setPhase('preview') }
    } catch (caught: unknown) {
      await cleanupUpload()
      if (mounted.current && !isAbortError(caught)) { setError(failureText(caught)); setPhase('form') }
    }
  }

  const install = async () => {
    if (preview === null || phase !== 'preview') return
    setError(null)
    setPhase('starting')
    const aborter = new AbortController()
    controller.current = aborter
    try {
      const created = await installCustomModel(preview.id, aborter.signal)
      jobRef.current = created
      setInitialTask(created)
      track(created)
      setPhase('job')
    } catch (caught: unknown) {
      if (mounted.current && !isAbortError(caught)) { setError(failureText(caught)); setPhase('preview') }
    }
  }

  const close = async () => {
    if (phase === 'starting' || cancelling) return
    if (active && task !== null) {
      setCancelling(true)
      setError(null)
      try {
        const cancelled = await cancelModelTask(task.id)
        setInitialTask(cancelled)
        track(cancelled)
      }
      catch (caught: unknown) { setError(failureText(caught)) }
      finally { setCancelling(false) }
      return
    }
    controller.current?.abort()
    if (await cleanupUpload()) onClose()
  }

  const canReview = !manual ? Boolean(source.trim()) : Boolean(engine && family && name.trim()
    && (availableEngines === undefined || availableEngines.includes(engine))
    && (sourceType === 'folder' ? folderSupported && selection !== null : source.trim())
    && (family !== 'matcha' || (acoustic.trim() && vocoder.trim() && tokens.trim()))
    && (engine !== 'sherpa-onnx-asr' || (
      encoder.trim() && decoder.trim() && tokens.trim() && (family !== 'nemo_transducer' || joiner.trim())
      && (sourceType !== 'folder' || [encoder, decoder, tokens, ...(family === 'nemo_transducer' ? [joiner] : [])].every((role) => selection?.files.some(({ name }) => name === role.trim())))
    )))
  const licenseLabel = (value: string) => value.toLowerCase() === 'unknown'
    ? t('addModel.unknown') : t('addModel.declared', { license: value.replace(/^User-declared: /, '') })
  const busy = phase === 'uploading' || phase === 'preparing' || phase === 'starting'
  const terminal = task !== null && !isActiveTask(task)
  const status = phase === 'uploading' ? t('addModel.uploading')
    : phase === 'preparing' ? t('addModel.preparing')
    : cancelling ? t('addModel.cancelling')
    : task?.state === 'queued' ? t('addModel.queued') : t('addModel.installing')
  const total = phase === 'uploading' ? selection?.totalBytes ?? 0 : task?.total_bytes ?? 0
  const done = phase === 'uploading' ? doneBytes : task?.done_bytes ?? 0

  return (
    <Modal open passiveModal size="md" className="voz-add-model"
      modalHeading={t('addModel.title')} closeButtonLabel={t('common.close')}
      preventCloseOnClickOutside onRequestClose={() => { void close() }}>
      {phase === 'form' ? (
        <form className="voz-add-model__form" onSubmit={(event) => { event.preventDefault(); if (canReview) void review() }}>
          <Button kind="ghost" type="button" onClick={() => { if (!manual && source.trim()) setSourceType(selectedSourceType); setManual(!manual); setError(null) }}>
            {t(manual ? 'addModel.guided' : 'addModel.manual')}
          </Button>
          {!manual ? (
            <>
              <TextInput id={id + '-link'} labelText={t('addModel.link')} helperText={t('addModel.linkHelp')}
                value={source} maxLength={2048} autoComplete="off" spellCheck={false}
                onChange={(event) => { setSource(event.target.value); setError(null) }} required />
              <TextInput id={id + '-optional-name'} labelText={t('addModel.optionalName')} value={name} maxLength={128}
                onChange={(event) => { setName(event.target.value) }} />
              <TextInput id={id + '-optional-license'} labelText={t('addModel.license')} helperText={t('addModel.licenseHelp')}
                value={license} maxLength={512} onChange={(event) => { setLicense(event.target.value) }} />
            </>
          ) : (
            <>
              <Select id={id + '-source'} labelText={t('addModel.source')} value={sourceType}
                onChange={(event) => { setSourceType(event.target.value as Source); setSource(''); setError(null) }}>
                <SelectItem value="folder" text={t('addModel.folder')} />
                <SelectItem value="huggingface" text={t('addModel.hf')} />
                <SelectItem value="url" text={t('addModel.url')} />
              </Select>
              <Select id={id + '-engine'} labelText={t('addModel.engine')} value={engine}
                onChange={(event) => { const next = event.target.value; setEngine(next); setFamily(FAMILIES[next]?.length === 1 ? FAMILIES[next][0] ?? '' : '') }}>
                <SelectItem value="" text={t('addModel.choose')} />
                <SelectItem value="faster-whisper" text="Faster Whisper" disabled={availableEngines !== undefined && !availableEngines.includes('faster-whisper')} />
                <SelectItem value="whisper-cpp" text="whisper.cpp" disabled={availableEngines !== undefined && !availableEngines.includes('whisper-cpp')} />
                <SelectItem value="sherpa-onnx-tts" text="sherpa-onnx TTS" disabled={availableEngines !== undefined && !availableEngines.includes('sherpa-onnx-tts')} />
                <SelectItem value="sherpa-onnx-asr" text="sherpa-onnx ASR" disabled={availableEngines !== undefined && !availableEngines.includes('sherpa-onnx-asr')} />
              </Select>
              {availableEngines !== undefined && !availableEngines.some((item) => Object.hasOwn(FAMILIES, item))
                ? <Notice kind="warning" title={t('addModel.noEngines')} /> : null}
              <Select id={id + '-family'} labelText={t('addModel.family')} value={family} disabled={!engine}
                onChange={(event) => { setFamily(event.target.value) }}>
                <SelectItem value="" text={t('addModel.choose')} />
                {(FAMILIES[engine] ?? []).map((item) => <SelectItem key={item} value={item} text={item} />)}
              </Select>
              <TextInput id={id + '-name'} labelText={t('addModel.name')} value={name} maxLength={128}
                onChange={(event) => { setName(event.target.value) }} required />
              <TextInput id={id + '-license'} labelText={t('addModel.license')} helperText={t('addModel.licenseHelp')}
                value={license} maxLength={512} onChange={(event) => { setLicense(event.target.value) }} />
              {sourceType === 'folder' ? (
                <div className="voz-add-model__folder">
                  <label htmlFor={id + '-folder'}>{t('addModel.folder')}</label>
                  <input id={id + '-folder'} type="file" multiple {...{ webkitdirectory: '' }} disabled={!folderSupported}
                    onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); setError(null) }} />
                  <p className="voz-field-note">{t('addModel.folderHelp')}</p>
                  {!folderSupported ? <Notice kind="warning" title={t('addModel.folderUnsupported')} /> : null}
                  {selection !== null ? (
                    <>
                      <p role="status">{t('addModel.selected', { count: selection.files.length, size: formatBytes(selection.totalBytes) })}</p>
                      {selection.ignoredCount > 0 ? <p className="voz-field-note">{t('addModel.excluded', { count: selection.ignoredCount })}</p> : null}
                    </>
                  ) : files.length > 0 && engine ? <Notice kind="error" title={t('addModel.error')} /> : null}
                </div>
              ) : (
                <>
                  <TextInput id={id + '-remote'} labelText={t(sourceType === 'url' ? 'addModel.url' : 'addModel.hf')}
                    value={source} maxLength={2048} autoComplete="off" spellCheck={false}
                    onChange={(event) => { setSource(event.target.value) }} required />
                  {sourceType === 'huggingface' ? <TextInput id={id + '-revision'} labelText={t('addModel.revision')}
                    value={revision} maxLength={255} onChange={(event) => { setRevision(event.target.value) }} />
                    : <p className="voz-field-note">{t('addModel.urlHelp')}</p>}
                </>
              )}
              {family === 'matcha' ? (
                <>
                  <TextInput id={id + '-acoustic'} labelText={t('addModel.acoustic')} value={acoustic} maxLength={512}
                    onChange={(event) => { setAcoustic(event.target.value) }} required />
                  <TextInput id={id + '-vocoder'} labelText={t('addModel.vocoder')} value={vocoder} maxLength={512}
                    onChange={(event) => { setVocoder(event.target.value) }} required />
                  <TextInput id={id + '-tokens'} labelText={t('addModel.tokens')} value={tokens} maxLength={512}
                    onChange={(event) => { setTokens(event.target.value) }} required />
                </>
              ) : null}
              {engine === 'sherpa-onnx-asr' && (family === 'whisper' || family === 'nemo_transducer') ? (
                <>
                  <TextInput id={id + '-encoder'} labelText={t('addModel.encoder')} value={encoder} maxLength={512}
                    onChange={(event) => { setEncoder(event.target.value) }} required />
                  <TextInput id={id + '-decoder'} labelText={t('addModel.decoder')} value={decoder} maxLength={512}
                    onChange={(event) => { setDecoder(event.target.value) }} required />
                  {family === 'nemo_transducer' ? (
                    <TextInput id={id + '-joiner'} labelText={t('addModel.joiner')} value={joiner} maxLength={512}
                      onChange={(event) => { setJoiner(event.target.value) }} required />
                  ) : null}
                  <TextInput id={id + '-asr-tokens'} labelText={t('addModel.asrTokens')} value={tokens} maxLength={512}
                    onChange={(event) => { setTokens(event.target.value) }} required />
                  {family === 'nemo_transducer' ? <p className="voz-field-note">{t('addModel.nemoLanguage')}</p> : null}
                </>
              ) : null}
            </>
          )}
          <Button type="submit" disabled={!canReview}>{t(!manual ? 'addModel.checkLink' : sourceType === 'folder' ? 'addModel.copyReview' : 'addModel.review')}</Button>
        </form>
      ) : phase === 'preview' && preview !== null ? (
        <div className="voz-add-model__preview">
          <p>{t('addModel.preview')}</p>
          <p>{t('addModel.selected', { count: preview.file_count, size: formatBytes(preview.size_bytes) })}</p>
          <p>{preview.descriptor.display_name} · {preview.descriptor.provider_id} · {preview.family}</p>
          <p>{preview.descriptor.capabilities.map((capability) => capabilityLabel(capability, t)).join(' · ')}</p>
          <p className="voz-field-note">{t('addModel.suggested')}</p>
          {preview.descriptor.provider_id === 'sherpa-onnx-asr' ? <p className="voz-field-note">{t('addModel.experimental')}</p> : null}
          <p>{licenseLabel(preview.license)}</p>
          {selectedSourceType === 'folder' ? <p className="voz-field-note">{t('addModel.expiry')}</p> : null}
          <div className="voz-add-model__actions">
            <Button onClick={() => { void install() }}>{t('addModel.install')}</Button>
            <Button kind="ghost" onClick={() => { void cleanupUpload().then((clean) => { if (clean) { setPreview(null); setPhase('form'); setError(null) } }) }}>{t('addModel.back')}</Button>
          </div>
        </div>
      ) : terminal ? (
        <Notice kind={task.state === 'completed' ? 'success' : task.state === 'cancelled' ? 'info' : 'error'}
          title={task.state === 'completed' ? t('addModel.completed') : task.state === 'cancelled' ? t('addModel.cancelled') : customModelError(task.error_code).message} />
      ) : (
        <div role="status" className="voz-add-model__progress">
          {busy && phase !== 'uploading' ? <Busy description={status} />
            : <ProgressBar label={status} {...(total > 0 ? { value: Math.min(100, Math.floor(done / total * 100)) } : {})}
              helperText={formatBytes(done) + ' / ' + formatBytes(total)} />}
        </div>
      )}
      {error ? <Notice kind="error" title={error} /> : null}
      {pollingError && active ? <Notice kind="error" title={t('addModel.taskError')}
        action={{ label: t('common.retry'), onClick: refresh }} /> : null}
      {cleanupFailed ? <Notice kind="error" title={t('addModel.cleanupError')}
        action={{ label: t('common.retry'), onClick: () => { void cleanupUpload() } }} /> : null}
      <div className="voz-add-model__actions">
        <Button kind="ghost" disabled={phase === 'starting' || cancelling} onClick={() => { void close() }}>
          {terminal ? t('common.close') : t('common.cancel')}
        </Button>
      </div>
    </Modal>
  )
}
