export type View = 'transcribir' | 'modelos' | 'proveedores'

export const NAV_ITEMS: readonly { id: View; label: string }[] = [
  { id: 'transcribir', label: 'Transcribir' },
  { id: 'modelos', label: 'Modelos' },
  { id: 'proveedores', label: 'Proveedores cloud' },
]
