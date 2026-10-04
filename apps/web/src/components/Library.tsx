import { useId, useMemo, useState } from 'react'
import {
  Button,
  DataTable,
  IconButton,
  Modal,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  Tag,
  TextInput,
} from '@carbon/react'
import { Add, Edit, FolderOpen, TrashCan } from '@carbon/icons-react'

import { PROCESSABLE_STATES, type JobState } from '../api/jobs'
import { deleteProject, renameProject, type LibraryItem } from '../api/library'
import { ProjectError } from '../api/projects'
import type { LibraryState } from '../hooks/useLibrary'
import { localeOf, translate, useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { routeToHash } from '../lib/navigation'
import { parseIso } from '../lib/time'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { sortLabel } from './tableSort'
import './Library.scss'

interface LibraryProps {
  state: LibraryState
  onReload: () => void
  onOpen: (item: LibraryItem) => void
  onNew: () => void
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

const MAX_NAME = 200

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : translate('err.project.generic')
}

/** ¿Se puede abrir? Solo si ya hay un trabajo (con su texto o en curso). */
function openable(item: LibraryItem): boolean {
  return item.latest_job !== null
}

interface RenameDialogProps {
  item: LibraryItem
  onClose: () => void
  onDone: () => void
}

function RenameDialog({ item, onClose, onDone }: RenameDialogProps) {
  const { t } = useI18n()
  const id = useId()
  const [name, setName] = useState(item.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trimmed = name.trim()
  const invalid = trimmed.length < 1 || trimmed.length > MAX_NAME

  async function submit() {
    if (invalid || busy) {
      return
    }
    if (trimmed === item.name) {
      onClose()
      return
    }
    setBusy(true)
    setError(null)
    try {
      await renameProject(item.project_id, trimmed)
      onDone()
    } catch (caught) {
      setError(messageOf(caught))
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      size="sm"
      closeButtonLabel={t('common.close')}
      modalHeading={t('lib.rename.title')}
      primaryButtonText={t('lib.rename.save')}
      secondaryButtonText={t('common.cancel')}
      primaryButtonDisabled={invalid || busy}
      onRequestClose={onClose}
      onRequestSubmit={() => {
        void submit()
      }}
    >
      <TextInput
        id={id}
        labelText={t('lib.rename.label')}
        helperText={t('lib.rename.help')}
        maxLength={MAX_NAME}
        value={name}
        invalid={name !== '' && invalid}
        invalidText={t('lib.rename.invalid')}
        data-modal-primary-focus
        onChange={(event) => {
          setName(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            void submit()
          }
        }}
      />
      {error ? <Notice kind="error" title={t('lib.rename.error')} subtitle={error} /> : null}
    </Modal>
  )
}

interface DeleteDialogProps {
  item: LibraryItem
  onClose: () => void
  onDone: () => void
}

function DeleteDialog({ item, onClose, onDone }: DeleteDialogProps) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await deleteProject(item.project_id)
      onDone()
    } catch (caught) {
      // Ya no existe: el objetivo se cumplió igual.
      if (caught instanceof ProjectError && caught.code === 'project_not_found') {
        onDone()
        return
      }
      setError(messageOf(caught))
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      danger
      size="sm"
      closeButtonLabel={t('common.close')}
      modalHeading={t('lib.delete.title', { name: item.name })}
      primaryButtonText={t('lib.delete.confirm')}
      secondaryButtonText={t('common.cancel')}
      primaryButtonDisabled={busy}
      onRequestClose={onClose}
      onRequestSubmit={() => {
        void submit()
      }}
    >
      <p>{t('lib.delete.body')}</p>
      {error ? <Notice kind="error" title={t('lib.delete.error')} subtitle={error} /> : null}
    </Modal>
  )
}

/** Cabeceras de la tabla; la clave `actions` no se ordena. */
const COLUMNS = ['name', 'date', 'duration', 'state', 'speakers', 'actions'] as const

function compareCells(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b
  }
  return String(a).localeCompare(String(b))
}

/** Home: biblioteca de transcripciones con buscar, abrir, renombrar y eliminar. */
export function Library({ state, onReload, onOpen, onNew }: LibraryProps) {
  const { t, tn, lang } = useI18n()
  const [query, setQuery] = useState('')
  const [renaming, setRenaming] = useState<LibraryItem | null>(null)
  const [deleting, setDeleting] = useState<LibraryItem | null>(null)

  const items = useMemo(() => (state.phase === 'ready' ? state.items : []), [state])
  const needle = query.trim().toLocaleLowerCase()
  const visible = useMemo(
    () =>
      needle === ''
        ? items
        : items.filter((item) => item.name.toLocaleLowerCase().includes(needle)),
    [items, needle],
  )
  const byId = useMemo(() => new Map(items.map((item) => [item.project_id, item])), [items])

  const headers = COLUMNS.map((key) => ({ key, header: t(`lib.col.${key}`) }))
  const rows = visible.map((item) => ({
    id: item.project_id,
    name: item.name,
    date: item.created_at,
    duration: item.media?.duration_ms ?? -1,
    state: item.latest_job?.state ?? '',
    speakers: item.speaker_count ?? -1,
    actions: '',
  }))

  const newButton = (
    <Button kind="primary" size="md" renderIcon={Add} onClick={onNew}>
      {t('lib.new')}
    </Button>
  )

  if (state.phase === 'loading') {
    return (
      <Panel titleId="lib-title" title={t('lib.table')} actions={newButton} className="voz-library">
        <div role="status">
          <Busy description={t('lib.loading')} />
        </div>
      </Panel>
    )
  }
  if (state.phase === 'error') {
    return (
      <Panel titleId="lib-title" title={t('lib.table')} actions={newButton} className="voz-library">
        <Notice
          kind="error"
          title={t('lib.error.title')}
          subtitle={state.message ?? t('recent.error.generic')}
          action={{ label: t('common.retry'), onClick: onReload }}
        />
      </Panel>
    )
  }
  if (items.length === 0) {
    return (
      <Panel titleId="lib-title" title={t('lib.table')} actions={newButton} className="voz-library">
        <p className="voz-field-note">{t('lib.empty')}</p>
        <h3 className="voz-library__steps-title">{t('recent.steps')}</h3>
        <ol className="voz-library__steps">
          <li>{t('start.step1')}</li>
          <li>{t('start.step2')}</li>
          <li>{t('start.step3')}</li>
        </ol>
        <p className="voz-field-note">
          {t('start.models')} <a href="#/modelos">{t('start.models.link')}</a>
        </p>
      </Panel>
    )
  }

  const formatDate = (iso: string) => {
    const when = parseIso(iso)
    return when === null
      ? ''
      : new Date(when).toLocaleString(localeOf(lang), { dateStyle: 'medium', timeStyle: 'short' })
  }

  return (
    <>
      <Panel
        titleId="lib-title"
        title={t('lib.table')}
        description={tn('lib.count', items.length)}
        actions={newButton}
        className="voz-library"
      >
        <DataTable
          rows={rows}
          headers={headers}
          isSortable
          size="lg"
          sortRow={(a: unknown, b: unknown, { sortDirection }: { sortDirection: string }) =>
            sortDirection === 'DESC' ? compareCells(b, a) : compareCells(a, b)
          }
        >
          {({ rows: tableRows, headers: tableHeaders, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer>
              <TableToolbar aria-label={t('lib.table')}>
                <TableToolbarContent>
                  <TableToolbarSearch
                    persistent
                    labelText={t('lib.search.label')}
                    placeholder={t('lib.search.placeholder')}
                    closeButtonLabelText={t('lib.search.clear')}
                    value={query}
                    onChange={(event: unknown) => {
                      const target = (event as { target?: { value?: string } }).target
                      setQuery(target?.value ?? '')
                    }}
                  />
                </TableToolbarContent>
              </TableToolbar>
              <Table {...getTableProps()} aria-label={t('lib.table')}>
                <TableHead>
                  <TableRow>
                    {tableHeaders.map((header) => {
                      const { key, isSortable, ...headerProps } = getHeaderProps({
                        header,
                        isSortable: header.key !== 'actions',
                      })
                      return (
                        <TableHeader
                          key={key}
                          isSortable={isSortable === true}
                          translateWithId={sortLabel}
                          {...headerProps}
                        >
                          {header.header}
                        </TableHeader>
                      )
                    })}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tableRows.map((row) => {
                    const item = byId.get(row.id)
                    if (!item) {
                      return null
                    }
                    const { key, ...rowProps } = getRowProps({ row })
                    const job = item.latest_job
                    const can = openable(item)
                    return (
                      <TableRow key={key} {...rowProps}>
                        <TableCell>
                          <div className="voz-library__name">
                            {can && job ? (
                              <a
                                className="voz-library__link"
                                href={routeToHash({ name: 'trabajo', jobId: job.id })}
                                onClick={(event) => {
                                  if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                                    event.preventDefault()
                                    onOpen(item)
                                  }
                                }}
                              >
                                {item.name}
                              </a>
                            ) : (
                              <span>{item.name}</span>
                            )}
                            {item.segment_count !== null && item.segment_count > 0 ? (
                              <span className="voz-library__sub">
                                {tn('lib.segments', item.segment_count)}
                                {job?.model_id ? ' · ' + t('lib.model', { model: job.model_id }) : ''}
                              </span>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>{formatDate(item.created_at)}</TableCell>
                        <TableCell>
                          {item.media?.duration_ms == null ? '—' : formatDuration(item.media.duration_ms)}
                        </TableCell>
                        <TableCell>
                          {job ? (
                            <Tag type={tagFor(job.state)} size="md">
                              {t(`job.state.${job.state}`)}
                            </Tag>
                          ) : (
                            <span title={t('lib.state.none.hint')}>
                              <Tag type="gray" size="md">
                                {t('lib.state.none')}
                              </Tag>
                            </span>
                          )}
                        </TableCell>
                        <TableCell>{item.speaker_count === null ? '—' : item.speaker_count}</TableCell>
                        <TableCell>
                          <div className="voz-library__actions">
                            <Button
                              kind="tertiary"
                              size="sm"
                              renderIcon={FolderOpen}
                              disabled={!can}
                              aria-label={t('lib.open.named', { name: item.name })}
                              onClick={() => {
                                onOpen(item)
                              }}
                            >
                              {t('lib.open')}
                            </Button>
                            <IconButton
                              kind="ghost"
                              size="sm"
                              label={t('lib.rename.named', { name: item.name })}
                              onClick={() => {
                                setRenaming(item)
                              }}
                            >
                              <Edit />
                            </IconButton>
                            <IconButton
                              kind="ghost"
                              size="sm"
                              label={t('lib.delete.named', { name: item.name })}
                              onClick={() => {
                                setDeleting(item)
                              }}
                            >
                              <TrashCan />
                            </IconButton>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
              {visible.length === 0 ? (
                <p className="voz-field-note voz-library__none" role="status">
                  {t('lib.noResults', { query: query.trim() })}
                </p>
              ) : null}
            </TableContainer>
          )}
        </DataTable>
      </Panel>
      {renaming ? (
        <RenameDialog
          item={renaming}
          onClose={() => {
            setRenaming(null)
          }}
          onDone={() => {
            setRenaming(null)
            onReload()
          }}
        />
      ) : null}
      {deleting ? (
        <DeleteDialog
          item={deleting}
          onClose={() => {
            setDeleting(null)
          }}
          onDone={() => {
            setDeleting(null)
            onReload()
          }}
        />
      ) : null}
    </>
  )
}
