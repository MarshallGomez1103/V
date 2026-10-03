import {
  Header,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderMenuItem,
  HeaderName,
  HeaderNavigation,
  SideNav,
  SideNavItems,
  SideNavLink,
  SkipToContent,
} from '@carbon/react'

import { useState } from 'react'

import { useI18n } from '../i18n/i18n'
import { NAV_ITEMS, type View } from '../lib/navigation'
import { LanguageMenu, SettingsMenu } from './HeaderMenus'
import { ShutdownAction } from './ShutdownAction'
import './AppHeader.scss'

interface AppHeaderProps {
  view: View
  onNavigate: (view: View) => void
  /** Hay una transcripción en curso (el cierre del servidor la avisa). */
  jobActive?: boolean
  /** El servidor se cerró desde el botón de la cabecera. */
  onClosed?: () => void
}

function BrandMark() {
  return (
    <svg
      className="voz-brand__mark"
      viewBox="0 0 20 16"
      width="20"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="0" y="5" width="2.5" height="6" fill="currentColor" />
      <rect x="4.5" y="2" width="2.5" height="12" fill="currentColor" />
      <rect x="9" y="0" width="2.5" height="16" fill="currentColor" />
      <rect x="13.5" y="2" width="2.5" height="12" fill="currentColor" />
      <rect x="18" y="5" width="2" height="6" fill="currentColor" />
    </svg>
  )
}

/** UI Shell de Carbon: marca, navegación por secciones y acciones globales. */
export function AppHeader({
  view,
  onNavigate,
  jobActive = false,
  onClosed,
}: AppHeaderProps) {
  const { t } = useI18n()
  // Estado propio del menú lateral: `HeaderContainer` trata su `render` como componente y
  // lo remontaría en cada render del padre (cerrando menús y diálogos abiertos).
  const [isSideNavExpanded, setSideNavExpanded] = useState(false)
  const onClickSideNavExpand = () => {
    setSideNavExpanded((current) => !current)
  }
  const go = (target: View) => (event: { preventDefault: () => void }) => {
    event.preventDefault()
    onNavigate(target)
    if (isSideNavExpanded) {
      onClickSideNavExpand()
    }
  }
  return (
    <Header aria-label={t('app.name')}>
      <SkipToContent href="#main-content">{t('app.skip')}</SkipToContent>
      <HeaderMenuButton
        aria-label={t('nav.menu')}
        isActive={isSideNavExpanded}
        onClick={onClickSideNavExpand}
      />
      <HeaderName
        href="#transcribir"
        prefix=""
        onClick={go('transcribir')}
        aria-label={t('nav.home')}
      >
        <BrandMark />
        <span className="voz-brand__name">{t('app.name')}</span>
      </HeaderName>
      <HeaderNavigation aria-label={t('nav.sections')}>
        {NAV_ITEMS.map((item) => (
          <HeaderMenuItem
            key={item.id}
            href={'#' + item.id}
            {...(view === item.id ? { 'aria-current': 'page' as const } : {})}
            onClick={go(item.id)}
          >
            {t(item.label)}
          </HeaderMenuItem>
        ))}
      </HeaderNavigation>
      <HeaderGlobalBar>
        <LanguageMenu />
        <SettingsMenu />
        <ShutdownAction
          jobActive={jobActive}
          onClosed={() => {
            onClosed?.()
          }}
        />
      </HeaderGlobalBar>
      <SideNav
        aria-label={t('nav.menu')}
        expanded={isSideNavExpanded}
        isPersistent={false}
        onSideNavBlur={onClickSideNavExpand}
      >
        <SideNavItems>
          {NAV_ITEMS.map((item) => (
            <SideNavLink
              key={item.id}
              href={'#' + item.id}
              {...(view === item.id ? { 'aria-current': 'page' as const } : {})}
              onClick={go(item.id)}
            >
              {t(item.label)}
            </SideNavLink>
          ))}
        </SideNavItems>
      </SideNav>
    </Header>
  )
}
