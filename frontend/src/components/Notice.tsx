// The Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`):
// tone = info / warning / error / success, optional actions.

import type { ReactNode } from 'react'
import { AlertTriangleIcon, CheckCircleIcon, InfoIcon, XCircleIcon } from './Icon.tsx'

export type NoticeTone = 'info' | 'warning' | 'error' | 'success'

interface NoticeProps {
  tone: NoticeTone
  title: string
  children?: ReactNode
  actions?: ReactNode
}

const ICONS: Record<NoticeTone, typeof InfoIcon> = {
  info: InfoIcon,
  warning: AlertTriangleIcon,
  error: XCircleIcon,
  success: CheckCircleIcon,
}

export function Notice({ tone, title, children, actions }: NoticeProps) {
  const ToneIcon = ICONS[tone]
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <ToneIcon className="notice__icon" />
      <div className="notice__body">
        <p className="notice__title">{title}</p>
        {children !== undefined && <p className="notice__detail">{children}</p>}
      </div>
      {actions !== undefined && <div className="notice__actions">{actions}</div>}
    </div>
  )
}
