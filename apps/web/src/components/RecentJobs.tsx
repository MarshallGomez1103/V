import { Button, Tag } from '@carbon/react'
import { FolderOpen } from '@carbon/icons-react'

import { PROCESSABLE_STATES, type JobState } from '../api/jobs'
import type { RecentJob, RecentJobsState } from '../hooks/useRecentJobs'
import { localeOf, useI18n } from '../i18n/i18n'
import { parseIso } from '../lib/time'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './RecentJobs.scss'

interface RecentJobsProps {
  state: RecentJobsState
  onOpen: (item: RecentJob) => void
  onRetry: () => void
}

function tagFor(state: JobState): 'green' | 'red' | 'blue' | 'gray' {
  if (state === 'COMPLETED') {
    return 'green'
  }
  if (state === 'FAILED') {
    return 'red'
  }
  return PROCESSABLE_STATES.has(state) ? 'blue' : 'gray'
}

/** Transcripciones guardadas en este equipo: abrirlas de nuevo tras recargar o reiniciar. */
export function RecentJobs({ state, onOpen, onRetry }: RecentJobsProps) {
  const { t, lang } = useI18n()
  return (
    <Panel titleId="recent-title" title={t('recent.title')} description={t('recent.description')}>
      {state.phase === 'loading' ? (
        <div role="status">
          <Busy description={t('recent.loading')} />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={t('recent.error.title')}
          subtitle={state.message ?? t('recent.error.generic')}
          action={{ label: t('common.retry'), onClick: onRetry }}
        />
      ) : state.items.length === 0 ? (
        <>
          <p className="voz-field-note">{t('recent.empty')}</p>
          <h3 className="voz-recent__steps-title">{t('recent.steps')}</h3>
          <ol className="voz-recent__steps">
            <li>{t('start.step1')}</li>
            <li>{t('start.step2')}</li>
            <li>{t('start.step3')}</li>
          </ol>
          <p className="voz-field-note">
            {t('start.models')} <a href="#modelos">{t('start.models.link')}</a>
          </p>
        </>
      ) : (
        <ul className="voz-recent">
          {state.items.map((item) => {
            const when = parseIso(item.job.created_at)
            return (
              <li key={item.job.id} className="voz-recent__item">
                <div className="voz-recent__info">
                  <span className="voz-recent__name">{item.project.name}</span>
                  <span className="voz-recent__meta">
                    {when === null
                      ? ''
                      : new Date(when).toLocaleString(localeOf(lang), {
                          dateStyle: 'medium',
                          timeStyle: 'short',
                        })}
                  </span>
                </div>
                <Tag type={tagFor(item.job.state)} size="md">
                  {t(`job.state.${item.job.state}`)}
                </Tag>
                <Button
                  kind="tertiary"
                  size="sm"
                  renderIcon={FolderOpen}
                  onClick={() => {
                    onOpen(item)
                  }}
                >
                  {t('recent.open')}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
