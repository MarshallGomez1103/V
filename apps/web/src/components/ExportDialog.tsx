import { useEffect, useId, useState } from 'react'
import { Button, Modal, RadioTile, TileGroup, Toggle } from '@carbon/react'
import { Download } from '@carbon/icons-react'

import {
  downloadFrom,
  EXPORT_FORMATS,
  exportDocumentUrl,
  fetchExportPreview,
  supportsExportOptions,
  type ExportFormat,
} from '../api/exportDocument'
import { isAbortError } from '../api/errors'
import { useI18n } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { Busy } from './Busy'
import './ExportDialog.scss'

export interface ExportDialogProps {
  transcriptId: string
}

const FORMAT_HELP: Record<ExportFormat, MessageKey> = {
  txt: 'exp.format.txt',
  markdown: 'exp.format.markdown',
  srt: 'exp.format.srt',
  vtt: 'exp.format.vtt',
  json: 'exp.format.json',
}

type Preview =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'ready'; text: string; truncated: boolean }

/** Resultado de pedir la vista previa de una URL concreta; evita mostrar la de otra opción. */
interface Fetched {
  url: string
  preview: Preview
}

/** Modal de exportación; es un componente aparte para que su estado empiece de cero al abrir. */
function ExportModal({
  transcriptId,
  onClose,
}: ExportDialogProps & { onClose: () => void }) {
  const { t } = useI18n()
  const base = useId()
  const [format, setFormat] = useState<ExportFormat>('txt')
  const [timestamps, setTimestamps] = useState(false)
  const [groupBySpeaker, setGroupBySpeaker] = useState(false)
  const [fetched, setFetched] = useState<Fetched | null>(null)
  const optionsApply = supportsExportOptions(format)
  const url = exportDocumentUrl(transcriptId, { format, timestamps, groupBySpeaker })

  useEffect(() => {
    const controller = new AbortController()
    void fetchExportPreview(url, controller.signal)
      .then(({ text, truncated }) => {
        setFetched({ url, preview: { phase: 'ready', text, truncated } })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setFetched({ url, preview: { phase: 'error' } })
        }
      })
    return () => {
      controller.abort()
    }
  }, [url])

  const preview: Preview = fetched?.url === url ? fetched.preview : { phase: 'loading' }
  const label = t(`export.${format}`)

  return (
    <Modal
      open
      size="md"
      className="voz-export-modal"
      closeButtonLabel={t('common.close')}
      modalHeading={t('exp.title')}
      primaryButtonText={t('exp.download', { format: label })}
      secondaryButtonText={t('common.close')}
      onRequestClose={onClose}
      onSecondarySubmit={onClose}
      onRequestSubmit={() => {
        downloadFrom(url)
        onClose()
      }}
    >
      <div className="voz-export">
        <p className="voz-field-note">{t('exp.intro')}</p>

        <TileGroup
          legend={t('exp.format')}
          name={base + '-format'}
          valueSelected={format}
          onChange={(value: unknown) => {
            setFormat(value as ExportFormat)
          }}
        >
          {EXPORT_FORMATS.map((item) => (
            <RadioTile
              key={item.id}
              id={base + '-' + item.id}
              value={item.id}
              className="voz-export__format"
            >
              <span className="voz-export__tile">
                <strong>{t(item.label)}</strong>
                <span className="voz-export__tilehelp">{t(FORMAT_HELP[item.id])}</span>
              </span>
            </RadioTile>
          ))}
        </TileGroup>

        <fieldset className="voz-export__options" disabled={!optionsApply}>
          <legend className="cds--label">{t('exp.options')}</legend>
          <div className="voz-export__option">
            <Toggle
              id={base + '-timestamps'}
              size="sm"
              labelText={t('exp.timestamps.label')}
              labelA={t('exp.off')}
              labelB={t('exp.on')}
              toggled={optionsApply && timestamps}
              disabled={!optionsApply}
              aria-describedby={base + '-timestamps-help'}
              onToggle={setTimestamps}
            />
            <p id={base + '-timestamps-help'} className="voz-field-note">
              {t('exp.timestamps.help')}
            </p>
          </div>
          <div className="voz-export__option">
            <Toggle
              id={base + '-group'}
              size="sm"
              labelText={t('exp.group.label')}
              labelA={t('exp.off')}
              labelB={t('exp.on')}
              toggled={optionsApply && groupBySpeaker}
              disabled={!optionsApply}
              aria-describedby={base + '-group-help'}
              onToggle={setGroupBySpeaker}
            />
            <p id={base + '-group-help'} className="voz-field-note">
              {t('exp.group.help')}
            </p>
          </div>
          {optionsApply ? null : (
            <p className="voz-field-note" role="note">
              {t('exp.options.na')}
            </p>
          )}
        </fieldset>

        <section aria-labelledby={base + '-preview'}>
          <h3 id={base + '-preview'} className="cds--label">
            {t('exp.preview')}
          </h3>
          {preview.phase === 'loading' ? (
            <div role="status">
              <Busy description={t('exp.preview.loading')} />
            </div>
          ) : preview.phase === 'error' ? (
            <p className="voz-field-note" role="alert">
              {t('exp.preview.error')}
            </p>
          ) : (
            <>
              <pre className="voz-export__preview" tabIndex={0} aria-label={t('exp.preview')}>
                {preview.text}
              </pre>
              {preview.truncated ? (
                <p className="voz-field-note">{t('exp.preview.more')}</p>
              ) : null}
            </>
          )}
        </section>
      </div>
    </Modal>
  )
}

/** Botón «Exportar» que abre el modal con formato, opciones explicadas y vista previa. */
export function ExportDialog({ transcriptId }: ExportDialogProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        kind="tertiary"
        size="md"
        renderIcon={Download}
        onClick={() => {
          setOpen(true)
        }}
      >
        {t('export.label')}
      </Button>
      {open ? (
        <ExportModal
          transcriptId={transcriptId}
          onClose={() => {
            setOpen(false)
          }}
        />
      ) : null}
    </>
  )
}
