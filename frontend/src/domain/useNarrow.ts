// Whether the screen is phone-narrow (a chart's layout follows it: at 390 px five labelled columns do not
// fit). A browser without matchMedia (jsdom) is wide.

import { useEffect, useState } from 'react'

const QUERY = '(max-width: 600px)'

function matches(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches
}

export function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return
    }
    const list = window.matchMedia(QUERY)
    const changed = () => {
      setNarrow(list.matches)
    }
    list.addEventListener('change', changed)
    return () => {
      list.removeEventListener('change', changed)
    }
  }, [])
  return narrow
}
