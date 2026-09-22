// Upload page (docs/SPECS.md section 4.1; design/mockups/Upload.png,
// "Upload · states (spec).png"). Client-side type/size check, then the upload
// with progress, then the caller (App.tsx) moves on to Analyzing.

import { useRef, useState } from 'react'
import type { DragEvent, KeyboardEvent } from 'react'
import { createRun } from '../api/runs.ts'
import type { RunUpload } from '../api/runs.ts'
import { describeError } from '../domain/errorCopy.ts'
import { formatBytes, UPLOAD_CEILING_MB, validateFile } from '../domain/upload.ts'
import { FileIcon, InfoIcon } from '../components/Icon.tsx'
import { Notice } from '../components/Notice.tsx'
import { Stepper } from '../components/Stepper.tsx'

type State =
  | { kind: 'idle' }
  | { kind: 'drag-over' }
  | { kind: 'uploading'; file: File; loaded: number; total: number; upload: RunUpload }
  | { kind: 'error'; error: unknown; fileSizeBytes?: number }

export interface UploadedRun {
  runId: string
  filename: string
  sizeBytes: number
}

interface UploadPageProps {
  baseUrl: string | undefined
  onUploaded: (run: UploadedRun) => void
}

export function UploadPage({ baseUrl, onUploaded }: UploadPageProps) {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const inputRef = useRef<HTMLInputElement>(null)

  function openPicker() {
    inputRef.current?.click()
  }

  function startUpload(file: File) {
    const problem = validateFile(file)
    if (problem) {
      setState({ kind: 'error', error: problem, fileSizeBytes: file.size })
      return
    }
    if (!baseUrl) {
      return
    }
    const upload = createRun(baseUrl, file, (progress) => {
      setState((current) =>
        current.kind === 'uploading'
          ? { ...current, loaded: progress.loaded, total: progress.total }
          : current,
      )
    })
    setState({ kind: 'uploading', file, loaded: 0, total: file.size, upload })
    upload.promise
      .then((run) => {
        onUploaded({ runId: run.run_id, filename: run.filename, sizeBytes: run.size_bytes })
      })
      .catch((error: unknown) => {
        setState({ kind: 'error', error, fileSizeBytes: file.size })
      })
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    const { files } = event.dataTransfer
    const file = files.length > 0 ? files[0] : undefined
    if (file) {
      startUpload(file)
    } else {
      setState({ kind: 'idle' })
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (state.kind === 'idle') {
      setState({ kind: 'drag-over' })
    }
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (state.kind === 'drag-over') {
      setState({ kind: 'idle' })
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openPicker()
    }
  }

  return (
    <div className="app-shell">
      <Stepper collectStatus="active" />
      <div className="page upload-page">
        <div className="upload-page__intro">
          <h1 className="page__title">Upload a sales or inventory file</h1>
          <p className="page__subtitle">
            We profile it, propose a cleaning plan, and you review every change before anything
            runs.
          </p>
        </div>

        {!baseUrl && (
          <Notice tone="error" title="Backend not configured">
            Set VITE_API_BASE_URL in .env and reload.
          </Notice>
        )}

        {state.kind === 'uploading' ? (
          <div className="upload-progress">
            <div className="upload-progress__row">
              <span>
                <FileIcon /> {state.file.name}
              </span>
              <span>
                {formatBytes(state.loaded)} / {formatBytes(state.total)}
              </span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{
                  width: `${String(state.total > 0 ? (state.loaded / state.total) * 100 : 0)}%`,
                }}
              />
            </div>
            <div className="upload-progress__status">
              <span>
                Uploading…{' '}
                {state.total > 0 ? Math.round((state.loaded / state.total) * 100) : 0}%
              </span>
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  state.upload.cancel()
                  setState({ kind: 'idle' })
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div
            className={'dropzone' + (state.kind === 'drag-over' ? ' dropzone--drag-over' : '')}
            role="button"
            tabIndex={0}
            aria-label="Drop your CSV here or browse for a file"
            onClick={openPicker}
            onKeyDown={handleKeyDown}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <FileIcon className="dropzone__icon" />
            {state.kind === 'drag-over' ? (
              <p>
                <strong>Release to upload</strong>
              </p>
            ) : (
              <p>
                Drop your CSV here or <span className="dropzone__browse">browse</span>
              </p>
            )}
            <span className="dropzone__hint">CSV only, up to {UPLOAD_CEILING_MB}MB</span>
            <input
              ref={inputRef}
              type="file"
              accept=".csv"
              hidden
              onClick={(event) => {
                event.stopPropagation()
              }}
              onChange={(event) => {
                const files = event.target.files
                const file = files && files.length > 0 ? files[0] : undefined
                event.target.value = ''
                if (file) {
                  startUpload(file)
                }
              }}
            />
          </div>
        )}

        {state.kind === 'error' &&
          (() => {
            const copy = describeError(state.error, { fileSizeBytes: state.fileSizeBytes })
            return (
              <Notice
                tone="error"
                title={copy.title}
                actions={
                  <button type="button" className="button button--secondary" onClick={openPicker}>
                    Choose another file
                  </button>
                }
              >
                {copy.detail}
              </Notice>
            )
          })()}

        <div className="notice notice--info">
          <InfoIcon className="notice__icon" />
          <div className="notice__body">
            <p className="notice__title">Your data stays on our server</p>
            <p className="notice__detail">
              Only a small sample (at most 30 rows plus column summaries) is sent to the AI to
              suggest a plan. Files are deleted automatically after 24 hours.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
