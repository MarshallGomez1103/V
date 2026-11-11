import { useEffect, useState } from 'react'

import { getHealth } from '../api/health'
import { useI18n } from '../i18n/i18n'

/**
 * Versión de V en Ajustes. Es informativa: mientras carga o si la lectura falla no se muestra
 * nada. Consulta `/api/health` solo al abrir el menú.
 */
export function AppVersion({ active }: { active: boolean }) {
  const { t } = useI18n()
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    if (!active) {
      return
    }
    const controller = new AbortController()
    getHealth(controller.signal)
      .then((health) => {
        setVersion(health.version ?? null)
      })
      .catch(() => undefined)
    return () => {
      controller.abort()
    }
  }, [active])

  if (version === null || version === '') {
    return null
  }

  return <p className="voz-version">{t('settings.version', { version: 'v' + version })}</p>
}
