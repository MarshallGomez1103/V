import { translate } from '../i18n/i18n'

/** Texto accesible del orden de columnas (Carbon lo trae en inglés). */
export function sortLabel(
  _id: string,
  args?: { header?: unknown; sortDirection?: unknown; isSortHeader?: boolean },
): string {
  const header = typeof args?.header === 'string' ? args.header : ''
  if (!args?.isSortHeader || args.sortDirection === 'NONE') {
    return translate('mm.sort.asc', { header })
  }
  return args.sortDirection === 'ASC'
    ? translate('mm.sort.desc', { header })
    : translate('mm.sort.clear', { header })
}
