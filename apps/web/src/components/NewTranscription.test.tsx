import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createJob } from '../api/jobs'
import { setLang } from '../i18n/i18n'
import { NewTranscription } from './NewTranscription'
import type { ImportResult } from './NewProjectCard'
import type { DiarizationRequest } from './DiarizationOptions'

vi.mock('../api/jobs', async (original) => ({ ...await original<typeof import('../api/jobs')>(), createJob: vi.fn() }))
vi.mock('../hooks/useDiarizationModel', () => ({ useDiarizationModel: () => ({ status: 'ready' }) }))
vi.mock('./MediaPanel', () => ({ MediaPanel: () => null }))
vi.mock('./GlossaryEditor', () => ({ GlossaryEditor: () => <div>Glossary control</div> }))
vi.mock('./ProfileSelector', () => ({ ProfileSelector: ({ value, onChange }: { value: string | null; onChange: (value: string) => void }) => (
  <select aria-label="Profile control" value={value ?? ''} onChange={(event) => { onChange(event.target.value) }}>
    <option value="">Default</option><option value="academic">Academic</option>
  </select>
) }))
vi.mock('./StyleInstructions', () => ({ StyleInstructions: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
  <input aria-label="Prompt control" value={value} onChange={(event) => { onChange(event.target.value) }} />
) }))
vi.mock('./DiarizationOptions', () => ({ DiarizationOptions: ({ onChange }: { onChange: (value: DiarizationRequest) => void }) => (
  <input type="checkbox" aria-label="Diarization control" onChange={(event) => { onChange({ enabled: event.target.checked, speakers: {} }) }} />
) }))
vi.mock('./TranscriptionOptionsSelector', () => ({ TranscriptionOptionsSelector: ({ onChange, onSelectedOptionChange, onCloudConsentChange }: {
  onChange: (id: string | null) => void
  onSelectedOptionChange?: (option: { provider_id: string; cloud?: boolean } | null) => void
  onCloudConsentChange?: (ok: boolean) => void
}) => (
  <>
    <button onClick={() => { onChange('opaque-fw'); onSelectedOptionChange?.({ provider_id: 'faster-whisper' }); onCloudConsentChange?.(true) }}>Choose FW</button>
    <button onClick={() => { onChange('opaque-asr'); onSelectedOptionChange?.({ provider_id: 'sherpa-onnx-asr' }); onCloudConsentChange?.(true) }}>Choose ASR</button>
    <button onClick={() => { onChange('opaque-cloud'); onSelectedOptionChange?.({ provider_id: 'openai', cloud: true }); onCloudConsentChange?.(false) }}>Choose cloud</button>
    <button onClick={() => { onCloudConsentChange?.(true) }}>Consent cloud</button>
  </>
) }))

const IMPORTED: ImportResult = {
  project: { id: 'project', name: 'Fixture', created_at: '' },
  media: { project_id: 'project', media_asset_id: 'media', filename: 'fixture.wav', media_type: 'audio/wav', duration_ms: 1000, sha256: 'a'.repeat(64) },
}

beforeEach(() => { vi.resetAllMocks() })
afterEach(cleanup)

describe('NewTranscription ASR restrictions', () => {
  it('hides unsupported controls and omits prior profile/prompt while retaining diarization', async () => {
    render(<NewTranscription header={null} modelsVersion={0} initialImported={IMPORTED} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose FW' }))
    fireEvent.change(screen.getByLabelText('Profile control'), { target: { value: 'academic' } })
    fireEvent.change(screen.getByLabelText('Prompt control'), { target: { value: 'Prior prompt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Choose ASR' }))
    expect(screen.queryByLabelText('Profile control')).toBeNull()
    expect(screen.queryByLabelText('Prompt control')).toBeNull()
    expect(screen.queryByText('Glossary control')).toBeNull()
    expect(screen.getByText(/experimental.*perfiles.*instrucciones.*glosario/i)).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Diarization control'))
    fireEvent.click(screen.getByRole('button', { name: 'Transcribir' }))
    await waitFor(() => { expect(createJob).toHaveBeenCalledOnce() })
    expect(vi.mocked(createJob).mock.calls[0]?.[0]).toEqual({
      project_id: 'project', media_asset_id: 'media', option_id: 'opaque-asr', language: null,
      diarization: { enabled: true, speakers: {} },
    })
  })

  it('keeps supported controls and prior values when switching back to FW', () => {
    render(<NewTranscription header={null} modelsVersion={0} initialImported={IMPORTED} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose FW' }))
    fireEvent.change(screen.getByLabelText('Profile control'), { target: { value: 'academic' } })
    fireEvent.click(screen.getByRole('button', { name: 'Choose ASR' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose FW' }))
    expect(screen.getByLabelText<HTMLSelectElement>('Profile control').value).toBe('academic')
    expect(screen.getByLabelText('Prompt control')).toBeTruthy()
    expect(screen.getByText('Glossary control')).toBeTruthy()
  })

  it('shows the experimental limitation in English', () => {
    setLang('en')
    render(<NewTranscription header={null} modelsVersion={0} initialImported={IMPORTED} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose ASR' }))
    expect(screen.getByText(/experimental.*profiles.*prompts.*glossar/i)).toBeTruthy()
  })
})

describe('NewTranscription cloud consent', () => {
  it('blocks a cloud option until consent and then sends it explicitly', async () => {
    render(<NewTranscription header={null} modelsVersion={0} initialImported={IMPORTED} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose cloud' }))
    expect(screen.getByRole('button', { name: 'Transcribir' }).hasAttribute('disabled')).toBe(true)
    expect(createJob).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Consent cloud' }))
    fireEvent.click(screen.getByRole('button', { name: 'Transcribir' }))
    await waitFor(() => { expect(createJob).toHaveBeenCalledOnce() })
    expect(vi.mocked(createJob).mock.calls[0]?.[0]).toMatchObject({ option_id: 'opaque-cloud', cloud_consent: true })
  })

  it('does not send the consent field for a local option', async () => {
    render(<NewTranscription header={null} modelsVersion={0} initialImported={IMPORTED} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose FW' }))
    fireEvent.click(screen.getByRole('button', { name: 'Transcribir' }))
    await waitFor(() => { expect(createJob).toHaveBeenCalledOnce() })
    expect(vi.mocked(createJob).mock.calls[0]?.[0]).not.toHaveProperty('cloud_consent')
  })
})
