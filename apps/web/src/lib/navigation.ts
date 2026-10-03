import type { MessageKey } from '../i18n/messages'

export type View = 'transcribir' | 'modelos' | 'proveedores'

export const NAV_ITEMS: readonly { id: View; label: MessageKey }[] = [
  { id: 'transcribir', label: 'nav.transcribir' },
  { id: 'modelos', label: 'nav.modelos' },
  { id: 'proveedores', label: 'nav.proveedores' },
]
