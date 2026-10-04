import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchLimits, LimitsError } from './limits.ts'

function stubFetch(response: Response): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchLimits', () => {
  it("GETs /api/limits and returns the server's upload limit", async () => {
    const fetchMock = stubFetch(Response.json({ max_upload_mb: 20 }))

    await expect(fetchLimits('http://localhost:8000/')).resolves.toEqual({ maxUploadMb: 20 })
    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/limits')
  })

  it('rejects an error status', async () => {
    stubFetch(new Response('boom', { status: 500 }))

    await expect(fetchLimits('http://localhost:8000')).rejects.toThrow(new LimitsError('HTTP 500'))
  })

  it.each([
    ['a missing limit', {}],
    ['a limit that is not a number', { max_upload_mb: '20' }],
    ['a limit of zero', { max_upload_mb: 0 }],
    ['a fractional limit', { max_upload_mb: 1.5 }],
  ])('rejects %s - the body is checked, not trusted', async (_label, body) => {
    stubFetch(Response.json(body))

    await expect(fetchLimits('http://localhost:8000')).rejects.toThrow(
      new LimitsError('unexpected response body'),
    )
  })
})
