import {
  Header,
  HeaderContainer,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderMenuItem,
  HeaderName,
  HeaderNavigation,
  SideNav,
  SideNavItems,
  SideNavLink,
  SkipToContent,
  Tag,
} from '@carbon/react'
import { Locked } from '@carbon/icons-react'

import { NAV_ITEMS, type View } from '../lib/navigation'
import './AppHeader.scss'

interface AppHeaderProps {
  view: View
  onNavigate: (view: View) => void
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

/** UI Shell de Carbon: marca, navegación por secciones e indicador de privacidad. */
export function AppHeader({ view, onNavigate }: AppHeaderProps) {
  return (
    <HeaderContainer
      render={({ isSideNavExpanded, onClickSideNavExpand }) => {
        const go = (target: View) => (event: { preventDefault: () => void }) => {
          event.preventDefault()
          onNavigate(target)
          if (isSideNavExpanded) {
            onClickSideNavExpand()
          }
        }
        return (
          <Header aria-label="VOZ">
            <SkipToContent href="#main-content">Saltar al contenido</SkipToContent>
            <HeaderMenuButton
              aria-label="Menú de secciones"
              isActive={isSideNavExpanded}
              onClick={onClickSideNavExpand}
            />
            <HeaderName
              href="#transcribir"
              prefix=""
              onClick={go('transcribir')}
              aria-label="VOZ, ir a Transcribir"
            >
              <BrandMark />
              <span className="voz-brand__name">VOZ</span>
            </HeaderName>
            <HeaderNavigation aria-label="Secciones de VOZ">
              {NAV_ITEMS.map((item) => (
                <HeaderMenuItem
                  key={item.id}
                  href={'#' + item.id}
                  {...(view === item.id ? { 'aria-current': 'page' as const } : {})}
                  onClick={go(item.id)}
                >
                  {item.label}
                </HeaderMenuItem>
              ))}
            </HeaderNavigation>
            <HeaderGlobalBar>
              <div className="voz-privacy">
                <Tag type="green" size="md" renderIcon={Locked}>
                  Local y privado
                </Tag>
              </div>
            </HeaderGlobalBar>
            <SideNav
              aria-label="Menú de secciones"
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
                    {item.label}
                  </SideNavLink>
                ))}
              </SideNavItems>
            </SideNav>
          </Header>
        )
      }}
    />
  )
}
