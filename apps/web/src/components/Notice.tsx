import type { ReactNode } from 'react'
import { ActionableNotification, InlineNotification } from '@carbon/react'

import { useI18n } from '../i18n/i18n'

const KIND_LABELS = {
  error: 'common.notice.error',
  info: 'common.notice.info',
  success: 'common.notice.success',
  warning: 'common.notice.warning',
} as const

export interface NoticeProps {
  kind: 'error' | 'info' | 'success' | 'warning'
  title: string
  subtitle?: string
  /** `alert` interrumpe al lector de pantalla; `status` espera su turno. */
  role?: 'alert' | 'status'
  /** Acción única (p. ej. «Reintentar»); Carbon no admite botones como hijos. */
  action?: { label: string; onClick: () => void; disabled?: boolean }
  className?: string
  /** Contenido de solo lectura (texto, etiquetas): nunca controles interactivos. */
  children?: ReactNode
}

/** Notificación Carbon en línea, de bajo contraste y sin botón de cierre. */
export function Notice({
  kind,
  title,
  subtitle,
  role = kind === 'error' ? 'alert' : 'status',
  action,
  className,
  children,
}: NoticeProps) {
  const { t } = useI18n()
  const common = {
    kind,
    lowContrast: true,
    hideCloseButton: true,
    role,
    title,
    statusIconDescription: t(KIND_LABELS[kind]),
    ...(subtitle === undefined ? {} : { subtitle }),
    ...(className === undefined ? {} : { className }),
  }
  if (action) {
    return (
      <ActionableNotification
        {...common}
        inline
        hasFocus={false}
        actionButtonLabel={action.label}
        onActionButtonClick={action.onClick}
      >
        {children}
      </ActionableNotification>
    )
  }
  return <InlineNotification {...common}>{children}</InlineNotification>
}
