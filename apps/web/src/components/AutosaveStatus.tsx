import { useSyncExternalStore } from 'react'
import { Button } from '@carbon/react'
import {
  CheckmarkFilled,
  ErrorFilled,
  InProgress,
  WarningAltFilled,
} from '@carbon/icons-react'

import type { SegmentDraftStore } from '../hooks/useSegmentDrafts'

import './AutosaveStatus.scss'

const LABELS = {
  saved: 'Todo guardado',
  saving: 'Guardando…',
  dirty: 'Cambios sin guardar',
  error: 'Error al guardar',
  conflict: 'Conflicto: elige qué versión conservar',
} as const

const ICONS = {
  saved: CheckmarkFilled,
  saving: InProgress,
  dirty: WarningAltFilled,
  error: ErrorFilled,
  conflict: ErrorFilled,
} as const

export function AutosaveStatus({ drafts }: { drafts: SegmentDraftStore }) {
  const status = useSyncExternalStore(drafts.subscribe, drafts.getStatus)
  const Icon = ICONS[status]

  return (
    <p className={'voz-autosave voz-autosave--' + status} role="status">
      <Icon size={16} aria-hidden="true" />
      <span>{LABELS[status]}</span>
      {status === 'error' && (
        <Button kind="ghost" size="sm" onClick={drafts.retryAll}>
          Reintentar
        </Button>
      )}
    </p>
  )
}
