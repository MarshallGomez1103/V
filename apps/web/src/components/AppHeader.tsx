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
import { HOME, isCurrent, NAV_ITEMS, routeToHash, type Route } from '../lib/navigation'
import { LanguageMenu, SettingsMenu } from './HeaderMenus'
import { ShutdownAction } from './ShutdownAction'
import './AppHeader.scss'

interface AppHeaderProps {
  route: Route
  onNavigate: (route: Route) => void
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
      width="24"
      height="19"
      aria-hidden="true"
      focusable="false"
    >
      <polygon points="0,0 4,0 10,11 16,0 20,0 12,16 8,16" fill="currentColor" />
    </svg>
  )
}

/** UI Shell de Carbon: marca, navegación por secciones y acciones globales. */
export function AppHeader({
  route,
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
  const go = (target: Route) => (event: { preventDefault: () => void }) => {
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
        href={routeToHash(HOME)}
        prefix=""
        onClick={go(HOME)}
        aria-label={t('nav.home')}
      >
        <BrandMark />
        <span className="voz-brand__name cds--visually-hidden">{t('app.name')}</span>
      </HeaderName>
      <HeaderNavigation aria-label={t('nav.sections')}>
        {NAV_ITEMS.map((item) => (
          <HeaderMenuItem
            key={item.route.name}
            href={routeToHash(item.route)}
            {...(isCurrent(item.route, route) ? { 'aria-current': 'page' as const } : {})}
            onClick={go(item.route)}
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
              key={item.route.name}
              href={routeToHash(item.route)}
              {...(isCurrent(item.route, route) ? { 'aria-current': 'page' as const } : {})}
              onClick={go(item.route)}
            >
              {t(item.label)}
            </SideNavLink>
          ))}
        </SideNavItems>
      </SideNav>
    </Header>
  )
}
