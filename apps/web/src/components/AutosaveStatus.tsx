import { useSyncExternalStore } from 'react'
import { Button } from '@carbon/react'
import {
  CheckmarkFilled,
  ErrorFilled,
  InProgress,
  WarningAltFilled,
} from '@carbon/icons-react'

import type { SegmentDraftStore } from '../hooks/useSegmentDrafts'
import { useI18n } from '../i18n/i18n'

import './AutosaveStatus.scss'

const LABELS = {
  saved: 'autosave.saved',
  saving: 'autosave.saving',
  dirty: 'autosave.dirty',
  error: 'autosave.error',
  conflict: 'autosave.conflict',
} as const

const ICONS = {
  saved: CheckmarkFilled,
  saving: InProgress,
  dirty: WarningAltFilled,
  error: ErrorFilled,
  conflict: ErrorFilled,
} as const

export function AutosaveStatus({ drafts }: { drafts: SegmentDraftStore }) {
  const { t } = useI18n()
  const status = useSyncExternalStore(drafts.subscribe, drafts.getStatus)
  const Icon = ICONS[status]

  return (
    <p className={'voz-autosave voz-autosave--' + status} role="status">
      <Icon size={16} aria-hidden="true" />
      <span>{t(LABELS[status])}</span>
      {status === 'error' && (
        <Button kind="ghost" size="sm" onClick={drafts.retryAll}>
          {t('common.retry')}
        </Button>
      )}
    </p>
  )
}
