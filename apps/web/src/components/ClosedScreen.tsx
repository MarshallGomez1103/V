import { Theme } from '@carbon/react'
import { Power } from '@carbon/icons-react'

import { useI18n } from '../i18n/i18n'
import { useAppearance } from '../theme/appearance'
import './ClosedScreen.scss'

/** Pantalla final tras cerrar el servidor: la pestaña ya no tiene a quién hablarle. */
export function ClosedScreen() {
  const { t } = useI18n()
  const { resolved, accent } = useAppearance()
  return (
    <Theme theme={resolved} className="voz-closed" data-accent={accent}>
      <main className="voz-closed__body" role="status">
        <Power size={32} aria-hidden="true" />
        <h1 className="voz-closed__title">{t('closed.title')}</h1>
        <p className="voz-closed__text">{t('closed.body')}</p>
      </main>
    </Theme>
  )
}
