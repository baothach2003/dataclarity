import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchHealth, HealthCheckError } from './health.ts'

function stubFetch(response: Response): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchHealth', () => {
  it('GETs /health on the base URL and returns the status', async () => {
    const fetchMock = stubFetch(Response.json({ status: 'ok' }))

    const result = await fetchHealth('http://localhost:8000')

    expect(result).toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/health', {
      signal: undefined,
    })
  })

  it('does not double the slash when the base URL ends with one', async () => {
    const fetchMock = stubFetch(Response.json({ status: 'ok' }))

    await fetchHealth('http://localhost:8000/')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://localhost:8000/health')
  })

  it('rejects with the HTTP status when the backend answers with an error', async () => {
    stubFetch(new Response('boom', { status: 500 }))

    await expect(fetchHealth('http://localhost:8000')).rejects.toThrow(
      new HealthCheckError('HTTP 500'),
    )
  })

  it('rejects a body without a string status', async () => {
    stubFetch(Response.json({ healthy: true }))

    await expect(fetchHealth('http://localhost:8000')).rejects.toThrow(
      new HealthCheckError('unexpected response body'),
    )
  })

  it('rejects a body that is not JSON', async () => {
    stubFetch(new Response('<html>proxy error</html>', { status: 200 }))

    await expect(fetchHealth('http://localhost:8000')).rejects.toThrow(
      new HealthCheckError('unexpected response body'),
    )
  })
})
