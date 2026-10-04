// The server's upload limit for the Upload page (PROJECT_PLAN 6A), or null
// while GET /api/limits has not answered, and for good if it fails: an
// unknown limit is never shown as one (6A-6D review B3). The page then checks
// only the SPECS ceiling, which no server exceeds, and the server enforces its
// own limit either way (SEC-1).

import { useEffect, useState } from 'react'
import { fetchLimits } from '../api/limits.ts'
import { UPLOAD_CEILING_MB } from '../domain/upload.ts'

export function useUploadLimit(baseUrl: string | undefined): number | null {
  const [limitMb, setLimitMb] = useState<number | null>(null)
  useEffect(() => {
    if (!baseUrl) {
      return
    }
    const controller = new AbortController()
    fetchLimits(baseUrl, controller.signal)
      .then((limits) => {
        setLimitMb(Math.min(limits.maxUploadMb, UPLOAD_CEILING_MB))
      })
      .catch(() => {
        // Stays unknown: an unreadable limit is no reason to block an upload
        // the server may accept.
      })
    return () => {
      controller.abort()
    }
  }, [baseUrl])
  return limitMb
}
