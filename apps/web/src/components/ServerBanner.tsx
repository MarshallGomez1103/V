import { ActionableNotification } from '@carbon/react'

import { useI18n } from '../i18n/i18n'

/** Aviso global cuando el servidor local no responde (en vez de dejar la pantalla en blanco). */
export function ServerBanner({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n()
  return (
    <ActionableNotification
      kind="error"
      lowContrast
      inline
      hideCloseButton
      hasFocus={false}
      role="alert"
      className="voz-serverbanner"
      statusIconDescription={t('common.notice.error')}
      title={t('down.title')}
      subtitle={t('down.body')}
      actionButtonLabel={t('down.retry')}
      onActionButtonClick={onRetry}
    />
  )
}
