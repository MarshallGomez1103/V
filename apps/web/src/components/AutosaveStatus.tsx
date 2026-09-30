import { useSyncExternalStore } from 'react'

import type { SegmentDraftStore } from '../hooks/useSegmentDrafts'

import './SegmentEditor.css'

const LABELS = {
  saved: 'Todo guardado',
  saving: 'Guardando…',
  dirty: 'Cambios sin guardar',
  error: 'Error al guardar',
  conflict: 'Conflicto: elige qué versión conservar',
} as const

export function AutosaveStatus({ drafts }: { drafts: SegmentDraftStore }) {
  const status = useSyncExternalStore(drafts.subscribe, drafts.getStatus)

  return (
    <p className={'autosave-status autosave-' + status} role="status">
      {LABELS[status]}
      {status === 'error' && (
        <>
          {' — '}
          <button type="button" className="autosave-retry" onClick={drafts.retryAll}>
            Reintentar
          </button>
        </>
      )}
    </p>
  )
}
