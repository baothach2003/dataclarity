// The stage 1 endpoints this UI drives (docs/SPECS.md section 8), following
// the typed-client pattern of api/health.ts: every response body is checked,
// not trusted, before it is handed back as a typed value.

import type {
  AnalyzeSchemaResponse,
  CleaningPlan,
  ExecuteResponse,
  PlanResponse,
  PreviewResponse,
  ProfileContract,
  RunCreated,
} from '../types/contracts.ts'
import { errorFromBody, throwApiError, UnreachableError } from './errors.ts'

function trimSlash(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

async function parseJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T
  } catch {
    throw new UnreachableError('unexpected response body')
  }
}

async function getJson<T>(baseUrl: string, path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${trimSlash(baseUrl)}${path}`, { signal })
  if (!response.ok) {
    await throwApiError(response)
  }
  return parseJson<T>(response)
}

async function postJson<T>(
  baseUrl: string,
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${trimSlash(baseUrl)}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
    signal,
  })
  if (!response.ok) {
    await throwApiError(response)
  }
  return parseJson<T>(response)
}

export interface UploadProgress {
  loaded: number
  total: number
}

export interface RunUpload {
  promise: Promise<RunCreated>
  cancel: () => void
}

/** POST /api/runs (multipart), with upload progress (design/mockups/Upload ·
 * states (spec).png "uploading" state): fetch has no cross-browser
 * upload-progress event, so this is the one call in the client built on
 * XMLHttpRequest instead of fetch. */
export function createRun(
  baseUrl: string,
  file: File,
  onProgress?: (progress: UploadProgress) => void,
): RunUpload {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<RunCreated>((resolve, reject) => {
    xhr.open('POST', `${trimSlash(baseUrl)}/api/runs`)
    xhr.responseType = 'json'
    if (onProgress) {
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          onProgress({ loaded: event.loaded, total: event.total })
        }
      })
    }
    xhr.addEventListener('error', () => {
      reject(new UnreachableError('the upload could not reach the server'))
    })
    xhr.addEventListener('abort', () => {
      reject(new UnreachableError('the upload was cancelled'))
    })
    xhr.addEventListener('load', () => {
      const body: unknown = xhr.response
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as RunCreated)
      } else {
        reject(errorFromBody(xhr.status, body))
      }
    })
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
  return { promise, cancel: () => { xhr.abort() } }
}

export function getProfile(
  baseUrl: string,
  runId: string,
  signal?: AbortSignal,
): Promise<ProfileContract> {
  return getJson<ProfileContract>(baseUrl, `/api/runs/${runId}/profile`, signal)
}

export function analyzeSchema(
  baseUrl: string,
  runId: string,
  signal?: AbortSignal,
): Promise<AnalyzeSchemaResponse> {
  return postJson<AnalyzeSchemaResponse>(baseUrl, `/api/runs/${runId}/analyze-schema`, null, signal)
}

export function proposePlan(baseUrl: string, runId: string, signal?: AbortSignal): Promise<PlanResponse> {
  return postJson<PlanResponse>(baseUrl, `/api/runs/${runId}/plan`, null, signal)
}

export function previewPlan(
  baseUrl: string,
  runId: string,
  plan: CleaningPlan,
  signal?: AbortSignal,
): Promise<PreviewResponse> {
  return postJson<PreviewResponse>(baseUrl, `/api/runs/${runId}/preview`, plan, signal)
}

/** GET /api/runs/{id}/download/cleaned.csv, as a Blob the caller turns into a
 * download (there is no `<a href>` target: the request needs no body, but the
 * response is binary and errors still come back as the JSON envelope). */
export async function downloadCleanedCsv(baseUrl: string, runId: string): Promise<Blob> {
  const response = await fetch(`${trimSlash(baseUrl)}/api/runs/${runId}/download/cleaned.csv`)
  if (!response.ok) {
    await throwApiError(response)
  }
  return response.blob()
}

export function executePlan(
  baseUrl: string,
  runId: string,
  plan: CleaningPlan,
  signal?: AbortSignal,
): Promise<ExecuteResponse> {
  return postJson<ExecuteResponse>(baseUrl, `/api/runs/${runId}/execute`, plan, signal)
}
