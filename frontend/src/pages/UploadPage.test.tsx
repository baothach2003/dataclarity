import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UploadPage } from './UploadPage.tsx'
import * as limitsApi from '../api/limits.ts'
import * as runsApi from '../api/runs.ts'
import { ApiError } from '../api/errors.ts'
import type { RunUpload } from '../api/runs.ts'
import type { RunCreated } from '../types/contracts.ts'

vi.mock('../api/runs.ts', () => ({ createRun: vi.fn() }))
vi.mock('../api/limits.ts', () => ({ fetchLimits: vi.fn() }))

beforeEach(() => {
  vi.mocked(limitsApi.fetchLimits).mockResolvedValue({ maxUploadMb: 50 })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function csvFile(name = 'sales.csv', size = 1024): File {
  const file = new File(['a,b\n1,2\n'], name, { type: 'text/csv' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function selectFile(file: File) {
  const input = document.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) {
    throw new Error('file input not found')
  }
  fireEvent.change(input, { target: { files: [file] } })
}

describe('UploadPage', () => {
  it("states and checks the server's own limit (6A: one source of truth)", async () => {
    vi.mocked(limitsApi.fetchLimits).mockResolvedValue({ maxUploadMb: 10 })
    const createRun = vi.mocked(runsApi.createRun)
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={vi.fn()} />)

    expect(await screen.findByText('CSV only, up to 10MB')).toBeDefined()
    selectFile(csvFile('sales.csv', 11 * 1024 * 1024))

    expect(screen.getByText('This file is too large')).toBeDefined()
    expect(createRun).not.toHaveBeenCalled()
    expect(vi.mocked(limitsApi.fetchLimits).mock.calls[0]?.[0]).toBe('http://localhost:8000')
  })

  // The 6A-6D review (B3): an unknown limit is never shown as a limit. Until
  // the server answers, and if it never does, the hint names none; the client
  // refuses only what no server accepts (the SPECS ceiling, SEC-1), and says so.
  it('names no limit while the server has not said one, and checks only the ceiling', async () => {
    let fail: ((reason: Error) => void) | undefined
    vi.mocked(limitsApi.fetchLimits).mockReturnValue(new Promise((_, reject) => { fail = reject }))
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={vi.fn()} />)

    expect(screen.getByText('CSV only')).toBeDefined()
    await act(async () => {
      fail?.(new Error('HTTP 500'))
      await Promise.resolve()
    })
    expect(vi.mocked(limitsApi.fetchLimits)).toHaveBeenCalledTimes(1)
    expect(screen.getByText('CSV only')).toBeDefined()
    expect(screen.queryByText(/up to/)).toBeNull()

    selectFile(csvFile('sales.csv', 61 * 1024 * 1024))
    expect(screen.getByText(/^Files over 50\.0MB are never accepted/)).toBeDefined()
  })

  it('rejects a non-CSV file client-side without calling the API', () => {
    const createRun = vi.mocked(runsApi.createRun)
    const onUploaded = vi.fn()
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={onUploaded} />)

    selectFile(csvFile('sales.xlsx'))

    expect(screen.getByText('Only CSV files are supported')).toBeDefined()
    expect(createRun).not.toHaveBeenCalled()
    expect(onUploaded).not.toHaveBeenCalled()
  })

  it('rejects an oversized file client-side without calling the API', () => {
    const createRun = vi.mocked(runsApi.createRun)
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={vi.fn()} />)

    selectFile(csvFile('sales.csv', 51 * 1024 * 1024))

    expect(screen.getByText('This file is too large')).toBeDefined()
    expect(createRun).not.toHaveBeenCalled()
  })

  it('uploads a valid file, shows progress, and reports the created run', async () => {
    let reportProgress: ((p: { loaded: number; total: number }) => void) | undefined
    let resolveUpload: ((run: RunCreated) => void) | undefined
    const upload: RunUpload = {
      promise: new Promise((resolve) => {
        resolveUpload = resolve
      }),
      cancel: vi.fn(),
    }
    vi.mocked(runsApi.createRun).mockImplementation((_baseUrl, _file, onProgress) => {
      reportProgress = onProgress
      return upload
    })
    const onUploaded = vi.fn()
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={onUploaded} />)

    selectFile(csvFile('sales.csv', 1000))
    expect(screen.getByText(/sales\.csv/)).toBeDefined()

    reportProgress?.({ loaded: 500, total: 1000 })
    expect(await screen.findByText('Uploading… 50%')).toBeDefined()

    resolveUpload?.({ run_id: 'run-1', filename: 'sales.csv', size_bytes: 1000, status: 'uploaded' })
    await vi.waitFor(() => {
      expect(onUploaded).toHaveBeenCalledWith({
        runId: 'run-1',
        filename: 'sales.csv',
        sizeBytes: 1000,
      })
    })
  })

  it('shows the server error when the upload fails', async () => {
    const upload: RunUpload = {
      promise: Promise.reject(new ApiError('EMPTY_FILE', 'The file is empty.')),
      cancel: vi.fn(),
    }
    vi.mocked(runsApi.createRun).mockReturnValue(upload)
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={vi.fn()} />)

    selectFile(csvFile())

    expect(await screen.findByText('This file has no data')).toBeDefined()
  })

  it('cancels the upload and returns to the drop zone', () => {
    const cancel = vi.fn()
    const upload: RunUpload = { promise: new Promise(() => undefined), cancel }
    vi.mocked(runsApi.createRun).mockReturnValue(upload)
    render(<UploadPage baseUrl="http://localhost:8000" onUploaded={vi.fn()} />)

    selectFile(csvFile())
    fireEvent.click(screen.getByText('Cancel'))

    expect(cancel).toHaveBeenCalled()
    expect(screen.getByText(/Drop your CSV here/)).toBeDefined()
  })

  it('shows a configuration notice and does nothing when the base URL is missing', () => {
    const createRun = vi.mocked(runsApi.createRun)
    render(<UploadPage baseUrl={undefined} onUploaded={vi.fn()} />)

    expect(screen.getByText('Backend not configured')).toBeDefined()
    selectFile(csvFile())
    expect(createRun).not.toHaveBeenCalled()
  })
})
