/**
 * Cliente del glosario por proyecto (S13.01): `GET`/`PUT /api/projects/{id}/glossary`.
 * Sesga al motor hacia esos términos; nunca reescribe el texto transcrito.
 */
import { translate, translateCode } from '../i18n/i18n'
import { readErrorCode } from './errors'

export interface Glossary {
  terms: string[]
  max_terms: number
  max_term_length: number
  /** Ids de motores que usan el glosario; los demás lo ignoran. */
  applies_to: string[]
}

export class GlossaryError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'GlossaryError'
    this.code = code
  }
}

function isGlossary(value: unknown): value is Glossary {
  return (
    typeof value === 'object' &&
    value !== null &&
    'terms' in value &&
    Array.isArray(value.terms) &&
    value.terms.every((term) => typeof term === 'string') &&
    'max_terms' in value &&
    typeof value.max_terms === 'number' &&
    'max_term_length' in value &&
    typeof value.max_term_length === 'number' &&
    'applies_to' in value &&
    Array.isArray(value.applies_to) &&
    value.applies_to.every((id) => typeof id === 'string')
  )
}

async function request(
  projectId: string,
  init: RequestInit,
): Promise<Glossary> {
  const response = await fetch(
    '/api/projects/' + encodeURIComponent(projectId) + '/glossary',
    init,
  )
  let body: unknown
  try {
    body = (await response.json()) as unknown
  } catch {
    body = undefined
  }
  if (!response.ok) {
    const code = readErrorCode(body) ?? 'http_' + String(response.status)
    throw new GlossaryError(code, translateCode('err.glossary.', code, 'err.glossary.generic'))
  }
  if (!isGlossary(body)) {
    throw new GlossaryError('invalid_response', translate('err.glossary.invalid'))
  }
  return body
}

export function getGlossary(
  projectId: string,
  signal?: AbortSignal,
): Promise<Glossary> {
  return request(projectId, {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
}

export function putGlossary(
  projectId: string,
  terms: string[],
  signal?: AbortSignal,
): Promise<Glossary> {
  return request(projectId, {
    method: 'PUT',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ terms }),
    ...(signal ? { signal } : {}),
  })
}
