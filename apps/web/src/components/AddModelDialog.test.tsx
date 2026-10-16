import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api/customModels'
import { cancelModelTask, listModelTasks, type TaskView } from '../api/models'
import { setLang } from '../i18n/i18n'
import { AddModelDialog } from './AddModelDialog'

vi.mock('../api/customModels', async (original) => ({
  ...await original<typeof import('../api/customModels')>(),
  createCustomModelUpload: vi.fn(), uploadCustomModelFile: vi.fn(),
  previewCustomModelUpload: vi.fn(), previewCustomModel: vi.fn(),
  installCustomModel: vi.fn(), discardCustomModelUpload: vi.fn(),
}))
vi.mock('../api/models', async (original) => ({
  ...await original<typeof import('../api/models')>(),
  listModelTasks: vi.fn(), cancelModelTask: vi.fn(),
}))

const ID = 'a'.repeat(32)
const PREVIEW: api.CustomModelPreview = {
  id: ID, family: 'ctranslate2', license: 'User-declared: MIT', size_bytes: 8, file_count: 3,
  descriptor: { provider_id: 'faster-whisper', model_id: 'custom-' + ID, display_name: 'My voice', capabilities: ['transcription'], source: null, revision: null },
}
const TASK: TaskView = {
  id: 'task-1', key: 'faster-whisper:custom-' + ID, model_id: 'custom-' + ID,
  method: 'custom', origin: null, state: 'running', done_bytes: 4, total_bytes: 8,
  error_code: null, created_at: '', updated_at: '',
}

function file(path: string, data: string): File {
  const result = new File([data], path.split('/').at(-1) ?? 'file')
  Object.defineProperty(result, 'webkitRelativePath', { value: path })
  return result
}

function fillFolder() {
  fireEvent.change(screen.getByLabelText('Motor'), { target: { value: 'faster-whisper' } })
  fireEvent.change(screen.getByLabelText('Familia'), { target: { value: 'ctranslate2' } })
  fireEvent.change(screen.getByLabelText('Nombre del modelo'), { target: { value: 'My voice' } })
  fireEvent.change(screen.getByLabelText('Licencia declarada por ti (opcional)'), { target: { value: 'MIT' } })
  fireEvent.change(screen.getByLabelText('Elegir carpeta'), { target: { files: [
    file('Private folder/model.bin', 'abcd'), file('Private folder/config.json', '{}'),
    file('Private folder/tokenizer.json', '{}'), file('Private folder/README.md', 'readme'),
    file('Private folder/model.py', 'print(1)'),
  ] } })
}

beforeEach(() => {
  vi.resetAllMocks()
  Object.defineProperty(HTMLInputElement.prototype, 'webkitdirectory', { configurable: true, value: false })
  vi.mocked(listModelTasks).mockResolvedValue([])
  vi.mocked(api.createCustomModelUpload).mockResolvedValue({ id: ID, total_bytes: 8, file_count: 3 })
  vi.mocked(api.uploadCustomModelFile).mockResolvedValue(undefined)
  vi.mocked(api.previewCustomModelUpload).mockResolvedValue(PREVIEW)
  vi.mocked(api.previewCustomModel).mockResolvedValue(PREVIEW)
  vi.mocked(api.installCustomModel).mockResolvedValue(TASK)
  vi.mocked(api.discardCustomModelUpload).mockResolvedValue(undefined)
  vi.mocked(cancelModelTask).mockResolvedValue({ ...TASK, state: 'cancelled' })
})

afterEach(() => { cleanup(); Reflect.deleteProperty(HTMLInputElement.prototype, 'webkitdirectory') })

describe('AddModelDialog', () => {
  it('imports Whisper ONNX from the explorer with explicit encoder, decoder and tokens roles', async () => {
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} availableEngines={['sherpa-onnx-asr']} />)
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'sherpa-onnx ASR' }).disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('Motor'), { target: { value: 'sherpa-onnx-asr' } })
    fireEvent.change(screen.getByLabelText('Familia'), { target: { value: 'whisper' } })
    fireEvent.change(screen.getByLabelText('Nombre del modelo'), { target: { value: 'Whisper ONNX' } })
    fireEvent.change(screen.getByLabelText('Elegir carpeta'), { target: { files: [
      file('Private folder/tiny-encoder.int8.onnx', 'abcd'),
      file('Private folder/tiny-decoder.onnx', 'abcd'),
      file('Private folder/tokens.txt', 'abcd'),
    ] } })
    const submit = screen.getByRole<HTMLButtonElement>('button', { name: 'Copiar archivos y revisar' })
    expect(submit.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Archivo encoder relativo (Whisper ONNX)'), { target: { value: 'tiny-encoder.int8.onnx' } })
    fireEvent.change(screen.getByLabelText('Archivo decoder relativo (Whisper ONNX)'), { target: { value: 'tiny-decoder.onnx' } })
    expect(submit.disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('Archivo de tokens relativo (Whisper ONNX)'), { target: { value: 'missing.txt' } })
    expect(submit.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Archivo de tokens relativo (Whisper ONNX)'), { target: { value: 'tokens.txt' } })
    fireEvent.click(submit)
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
    expect(api.createCustomModelUpload).toHaveBeenCalledWith(expect.objectContaining({
      engine: 'sherpa-onnx-asr', family: 'whisper',
      file_roles: { encoder: 'tiny-encoder.int8.onnx', decoder: 'tiny-decoder.onnx', tokens: 'tokens.txt' },
    }), expect.any(AbortSignal))
  })

  it('requires explicit engine/family and shows selected size before any transfer', async () => {
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Copiar archivos y revisar' }).disabled).toBe(true)
    fillFolder()
    expect(screen.getByText('3 archivos · 8 B', { exact: false })).toBeTruthy()
    expect(screen.getByText(/2 archivos excluidos/)).toBeTruthy()
    expect(api.createCustomModelUpload).not.toHaveBeenCalled()
    const input = screen.getByLabelText('Elegir carpeta')
    expect(input.hasAttribute('webkitdirectory')).toBe(true)
    expect(input.hasAttribute('multiple')).toBe(true)
    await act(async () => { await Promise.resolve() })
  })

  it('uploads only compatible files, reviews license/size, then confirms and refreshes completed models once', async () => {
    const completed = vi.fn()
    render(<AddModelDialog onClose={vi.fn()} onCompleted={completed} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
    expect(api.createCustomModelUpload).toHaveBeenCalledWith(expect.objectContaining({
      engine: 'faster-whisper', family: 'ctranslate2', license: 'MIT',
      files: [{ name: 'model.bin', size_bytes: 4 }, { name: 'config.json', size_bytes: 2 }, { name: 'tokenizer.json', size_bytes: 2 }],
    }), expect.any(AbortSignal))
    expect(api.uploadCustomModelFile).toHaveBeenCalledTimes(3)
    expect(api.installCustomModel).not.toHaveBeenCalled()
    expect(screen.getByText('Declarada por ti: MIT')).toBeTruthy()
    vi.mocked(listModelTasks).mockResolvedValue([{ ...TASK, state: 'completed' }])
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e instalar' }))
    await screen.findByText('Modelo instalado.')
    expect(api.installCustomModel).toHaveBeenCalledWith(ID, expect.any(AbortSignal))
    await waitFor(() => { expect(completed).toHaveBeenCalledTimes(1) })
    expect(api.discardCustomModelUpload).toHaveBeenCalledWith(ID)
  })

  it('supports Hugging Face metadata preview without folder upload', async () => {
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Origen del modelo'), { target: { value: 'huggingface' } })
    fireEvent.change(screen.getByLabelText('Motor'), { target: { value: 'faster-whisper' } })
    fireEvent.change(screen.getByLabelText('Familia'), { target: { value: 'ctranslate2' } })
    fireEvent.change(screen.getByLabelText('Nombre del modelo'), { target: { value: 'HF model' } })
    fireEvent.change(screen.getByLabelText('Repositorio de Hugging Face'), { target: { value: 'org/model' } })
    fireEvent.click(screen.getByRole('button', { name: 'Revisar modelo' }))
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
    expect(api.previewCustomModel).toHaveBeenCalledWith(expect.objectContaining({ source_type: 'huggingface', source: 'org/model', license: 'unknown', revision: 'main' }), expect.any(AbortSignal))
    expect(api.createCustomModelUpload).not.toHaveBeenCalled()
  })

  it('supports TTS URL and requires Matcha acoustic/vocoder roles', async () => {
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Origen del modelo'), { target: { value: 'url' } })
    fireEvent.change(screen.getByLabelText('Motor'), { target: { value: 'sherpa-onnx-tts' } })
    fireEvent.change(screen.getByLabelText('Familia'), { target: { value: 'matcha' } })
    fireEvent.change(screen.getByLabelText('Nombre del modelo'), { target: { value: 'TTS' } })
    fireEvent.change(screen.getByLabelText('URL de archivo'), { target: { value: 'http://127.0.0.1/model.tar.bz2' } })
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Revisar modelo' }).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Archivo acústico relativo (Matcha)'), { target: { value: 'acoustic.onnx' } })
    fireEvent.change(screen.getByLabelText('Archivo vocoder relativo (Matcha)'), { target: { value: 'vocoder.onnx' } })
    fireEvent.click(screen.getByRole('button', { name: 'Revisar modelo' }))
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
    expect(api.previewCustomModel).toHaveBeenCalledWith(expect.objectContaining({ engine: 'sherpa-onnx-tts', family: 'matcha', file_roles: { acoustic_model: 'acoustic.onnx', vocoder: 'vocoder.onnx', tokens: 'tokens.txt' } }), expect.any(AbortSignal))
  })

  it('cancels an active job and cleans the folder after terminal state', async () => {
    const completed = vi.fn()
    render(<AddModelDialog onClose={vi.fn()} onCompleted={completed} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar e instalar' }))
    await screen.findByText('Instalando y validando el modelo…')
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await screen.findByText('Importación cancelada.')
    expect(cancelModelTask).toHaveBeenCalledWith(TASK.id)
    expect(completed).not.toHaveBeenCalled()
    await waitFor(() => { expect(api.discardCustomModelUpload).toHaveBeenCalledWith(ID) })
  })

  it('aborts an uploading file and deletes the partial session on cancellation', async () => {
    let signal: AbortSignal | undefined
    vi.mocked(api.uploadCustomModelFile).mockImplementation((_id, _index, _file, options) => {
      signal = options?.signal
      return new Promise<void>((_resolve, reject) => {
        signal?.addEventListener('abort', () => { reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
      })
    })
    const close = vi.fn()
    render(<AddModelDialog onClose={close} onCompleted={vi.fn()} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await screen.findByText('Copiando archivos a V…')
    await waitFor(() => { expect(signal).toBeDefined() })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => { expect(close).toHaveBeenCalled() })
    expect(signal?.aborted).toBe(true)
    expect(api.discardCustomModelUpload).toHaveBeenCalledWith(ID)
  })

  it('does not transfer files if cancelled while the upload ID is pending', async () => {
    let resolve!: (value: api.CustomModelUploadReceipt) => void
    vi.mocked(api.createCustomModelUpload).mockImplementation(() => new Promise((done) => { resolve = done }))
    const close = vi.fn()
    render(<AddModelDialog onClose={close} onCompleted={vi.fn()} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await waitFor(() => { expect(resolve).toBeDefined() })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await act(async () => { resolve({ id: ID, total_bytes: 8, file_count: 3 }); await Promise.resolve() })
    expect(api.uploadCustomModelFile).not.toHaveBeenCalled()
    expect(api.discardCustomModelUpload).toHaveBeenCalledWith(ID)
  })

  it('never renders raw server errors and lets the user retry', async () => {
    vi.mocked(api.previewCustomModelUpload).mockRejectedValueOnce(new Error('/private/SECRET raw'))
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await screen.findByText('No se pudo importar el modelo. Revisa los datos y vuelve a intentarlo.')
    expect(document.body.textContent).not.toContain('SECRET')
    expect(api.discardCustomModelUpload).toHaveBeenCalledWith(ID)
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
  })

  it('shows live upload progress', async () => {
    let advance: ((bytes: number) => void) | undefined
    let finish: (() => void) | undefined
    vi.mocked(api.uploadCustomModelFile).mockImplementationOnce((_id, _index, _file, options) => {
      advance = options?.onProgress
      return new Promise<void>((resolve) => { finish = resolve })
    })
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    fillFolder()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar archivos y revisar' }))
    await waitFor(() => { expect(advance).toBeDefined() })
    act(() => { advance?.(2) })
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('25')
    await act(async () => { finish?.(); await Promise.resolve() })
    await screen.findByRole('button', { name: 'Confirmar e instalar' })
  })

  it('uses English labels and restores focus to its opener', async () => {
    setLang('en')
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const view = render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    expect(screen.getByRole('dialog', { name: 'Add a custom model' })).toBeTruthy()
    expect(screen.getByLabelText('Engine')).toBeTruthy()
    await act(async () => { await Promise.resolve() })
    view.unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('reports unsupported folder selection without accepting a host path', async () => {
    Reflect.deleteProperty(HTMLInputElement.prototype, 'webkitdirectory')
    render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} />)
    expect(screen.getByText(/Este navegador no permite elegir carpetas/)).toBeTruthy()
    expect(screen.queryByLabelText(/ruta.*servidor/i)).toBeNull()
    await act(async () => { await Promise.resolve() })
  })

  it('disables unavailable engines and reports missing runtimes', async () => {
    const view = render(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} availableEngines={['whisper-cpp']} />)
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'Faster Whisper' }).disabled).toBe(true)
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'whisper.cpp' }).disabled).toBe(false)
    view.rerender(<AddModelDialog onClose={vi.fn()} onCompleted={vi.fn()} availableEngines={[]} />)
    expect(screen.getByText('No hay motores compatibles disponibles. Instala un runtime antes de importar.')).toBeTruthy()
    expect(api.createCustomModelUpload).not.toHaveBeenCalled()
    await act(async () => { await Promise.resolve() })
  })
})
