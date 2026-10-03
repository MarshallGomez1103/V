import type { ReactNode } from 'react'
import { ActionableNotification, InlineNotification } from '@carbon/react'

const KIND_LABELS = {
  error: 'Error',
  info: 'Información',
  success: 'Correcto',
  warning: 'Advertencia',
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
  const common = {
    kind,
    lowContrast: true,
    hideCloseButton: true,
    role,
    title,
    statusIconDescription: KIND_LABELS[kind],
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
