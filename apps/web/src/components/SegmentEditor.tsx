import { useSyncExternalStore } from 'react'
import { Button } from '@carbon/react'

import type { EditableSegment } from '../api/segments'
import { findMatches } from '../lib/segmentSearch'
import type {
  SegmentDraftStatus,
  SegmentDraftStore,
} from '../hooks/useSegmentDrafts'

import { Notice } from './Notice'
import './SegmentEditor.scss'

interface SegmentEditorProps {
  segment: EditableSegment
  drafts: SegmentDraftStore
  // Búsqueda activa: se resalta con <mark> en una capa detrás del textarea.
  query?: string
}

const STATUS_LABELS: Record<SegmentDraftStatus, string> = {
  idle: '',
  dirty: 'Sin guardar',
  saving: 'Guardando…',
  saved: 'Guardado',
  error: 'Error al guardar',
  conflict: 'Conflicto',
}

export function SegmentEditor({ segment, drafts, query = '' }: SegmentEditorProps) {
  const draft = useSyncExternalStore(drafts.subscribe, () =>
    drafts.getDraft(segment.id),
  )
  const status: SegmentDraftStatus = draft?.status ?? 'idle'
  const inputId = 'segment-text-' + segment.id
  // ponytail: si la lista se recarga con una revisión más nueva, el borrador local manda.
  const value = draft ? draft.text : segment.text
  const ranges = query.trim() === '' ? [] : findMatches(value, query)

  return (
    <div className="segment-editor" data-status={status}>
      <label className="segment-editor-label" htmlFor={inputId}>
        Texto del segmento {segment.id}
      </label>
      <div className="segment-editor-field">
        {ranges.length > 0 ? (
          <div className="segment-editor-backdrop" aria-hidden="true">
            {ranges.flatMap((range, i) => [
              value.slice(i === 0 ? 0 : (ranges[i - 1]?.end ?? 0), range.start),
              <mark key={range.start} className="segment-match">
                {value.slice(range.start, range.end)}
              </mark>,
            ])}
            {value.slice(ranges[ranges.length - 1]?.end ?? 0)}
          </div>
        ) : null}
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
      </div>
      {status !== 'idle' && (
        <p className="segment-editor-state">
          <span>{STATUS_LABELS[status]}</span>
          {status === 'error' && (
            <>
              {draft?.errorMessage ? ' — ' + draft.errorMessage + ' ' : ' '}
              <Button
                kind="ghost"
                size="sm"
                onClick={() => {
                  drafts.retry(segment.id)
                }}
              >
                Reintentar
              </Button>
            </>
          )}
        </p>
      )}
      {status === 'conflict' && draft?.conflict && (
        <div className="segment-editor-conflict" role="alert">
          <Notice
            kind="warning"
            role="status"
            title="El segmento cambió en el servidor. Versión del servidor:"
          />
          <blockquote className="segment-editor-server">
            {draft.conflict.text}
          </blockquote>
          <div className="segment-editor-actions">
            <Button
              kind="primary"
              size="sm"
              onClick={() => {
                drafts.keepMine(segment.id)
              }}
            >
              Usar mi versión
            </Button>
            <Button
              kind="tertiary"
              size="sm"
              onClick={() => {
                drafts.discard(segment.id)
              }}
            >
              Descartar
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
