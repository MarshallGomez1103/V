import { errors } from './messages/errors'
import { job } from './messages/job'
import { library } from './messages/library'
import { models } from './messages/models'
import { shell } from './messages/shell'
import { transcribe } from './messages/transcribe'
import { workspace } from './messages/workspace'

/** Cada mensaje es [español, inglés]; `{nombre}` marca una variable. */
export type Pair = readonly [string, string]
export type Catalog = Readonly<Record<string, Pair>>

export const MESSAGES = {
  ...shell,
  ...transcribe,
  ...job,
  ...workspace,
  ...library,
  ...models,
  ...errors,
} as const

export type MessageKey = keyof typeof MESSAGES
