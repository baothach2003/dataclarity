// The charts' chrome in the app's tokens (the display review's R3, 2026-10-16): Recharts draws its tooltip white with
// a label that inherits the page's ink, and its ticks #666 - unreadable once dark mode is selected. Every chart's
// tooltip takes these, its axes `fill: 'var(--text-secondary)'`.

import type { CSSProperties } from 'react'

export const TOOLTIP_STYLE: CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

export const TOOLTIP_LABEL: CSSProperties = { color: 'var(--text-primary)' }
