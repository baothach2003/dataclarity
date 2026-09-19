import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HealthStatus } from './HealthStatus.tsx'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('HealthStatus', () => {
  it('shows a checking state, then the backend status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'ok' })))

    render(<HealthStatus baseUrl="http://localhost:8000" />)

    expect(screen.getByRole('status').textContent).toBe('Backend: checking…')
    expect(await screen.findByText('Backend: ok')).toBeDefined()
  })

  it('shows the reason when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    render(<HealthStatus baseUrl="http://localhost:8000" />)

    expect(await screen.findByText('Backend: unreachable (Failed to fetch)')).toBeDefined()
  })

  it('shows the reason when the backend answers with an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    render(<HealthStatus baseUrl="http://localhost:8000" />)

    expect(await screen.findByText('Backend: unreachable (HTTP 503)')).toBeDefined()
  })

  it('says the URL is not configured and makes no request when it is missing', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<HealthStatus baseUrl={undefined} />)

    expect(screen.getByRole('status').textContent).toBe(
      'Backend: not configured (set VITE_API_BASE_URL in .env)',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
