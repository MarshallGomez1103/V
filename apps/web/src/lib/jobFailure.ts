import { translate, translateCode } from '../i18n/i18n'

/** Mensaje de un trabajo fallido según su `error_code`; sin código o con uno nuevo, uno seguro. */
export function failureMessage(code: string | null): string {
  return code === null ? translate('job.fail.generic') : translateCode('job.fail.', code, 'job.fail.code')
}
