import { useSyncExternalStore } from 'react'

import type { EditableSegment } from '../api/segments'
import type {
  SegmentDraftStatus,
  SegmentDraftStore,
} from '../hooks/useSegmentDrafts'

import './SegmentEditor.css'

interface SegmentEditorProps {
  segment: EditableSegment
  drafts: SegmentDraftStore
}

const STATUS_LABELS: Record<SegmentDraftStatus, string> = {
  idle: '',
  dirty: 'Sin guardar',
  saving: 'Guardando…',
  saved: 'Guardado',
  error: 'Error al guardar',
  conflict: 'Conflicto',
}

export function SegmentEditor({ segment, drafts }: SegmentEditorProps) {
  const draft = useSyncExternalStore(drafts.subscribe, () =>
    drafts.getDraft(segment.id),
  )
  const status: SegmentDraftStatus = draft?.status ?? 'idle'
  const inputId = 'segment-text-' + segment.id
  // ponytail: si la lista se recarga con una revisión más nueva, el borrador local manda.
  const value = draft ? draft.text : segment.text

  return (
    <div className="segment-editor" data-status={status}>
      <label className="segment-editor-label" htmlFor={inputId}>
        Texto del segmento {segment.id}
      </label>
      <textarea
        id={inputId}
        className="segment-editor-input"
        value={value}
        rows={1}
        aria-invalid={status === 'error' || status === 'conflict'}
        onChange={(event) => {
          drafts.edit(segment, event.target.value)
        }}
        onBlur={() => {
          drafts.flush(segment.id)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            drafts.revert(segment.id)
          }
        }}
      />
      {status !== 'idle' && (
        <p className="segment-editor-state">
          <span>{STATUS_LABELS[status]}</span>
          {status === 'error' && (
            <>
              {draft?.errorMessage ? ' — ' + draft.errorMessage + ' ' : ' '}
              <button
                type="button"
                onClick={() => {
                  drafts.retry(segment.id)
                }}
              >
                Reintentar
              </button>
            </>
          )}
        </p>
      )}
      {status === 'conflict' && draft?.conflict && (
        <div className="segment-editor-conflict" role="alert">
          <p>El segmento cambió en el servidor. Versión del servidor:</p>
          <blockquote>{draft.conflict.text}</blockquote>
          <div className="segment-editor-actions">
            <button
              type="button"
              onClick={() => {
                drafts.keepMine(segment.id)
              }}
            >
              Usar mi versión
            </button>
            <button
              type="button"
              onClick={() => {
                drafts.discard(segment.id)
              }}
            >
              Descartar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
