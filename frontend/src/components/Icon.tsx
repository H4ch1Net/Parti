import type { ReactNode, SVGProps } from 'react'

/*
  Drafted icon set: 24-unit grid, 1.5 stroke, square caps, mitred joins.
  Status icons are shape-coded like drawing symbols: triangle = warning,
  diamond = error, circle = information.
*/

const ICONS: Record<string, ReactNode> = {
  setsquare: (
    <>
      <path d="M4 20V4l16 16z" />
      <path d="M8 16v-3.2l3.2 3.2z" />
      <path d="M4 8h2M4 12h2" />
    </>
  ),
  sun: (
    <>
      <path d="M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8z" />
      <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
    </>
  ),
  moon: <path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" />,
  contrast: (
    <>
      <path d="M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z" />
      <path d="M12 3v18a9 9 0 0 0 0-18z" fill="currentColor" stroke="none" />
    </>
  ),
  keyboard: (
    <>
      <path d="M3 6.5h18v11H3z" />
      <path d="M6.5 10h1M10 10h1M13.5 10h1M17 10h.5M7.5 14h9" />
    </>
  ),
  github: (
    <path
      fill="currentColor"
      stroke="none"
      d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02a9.6 9.6 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2z"
    />
  ),
  download: <path d="M12 3.5v11M7 9.5l5 5 5-5M4.5 20h15" />,
  link: (
    <>
      <path d="M10 14l4-4" />
      <path d="M8.5 11.5L6 14a3 3 0 0 0 4 4l2.5-2.5M15.5 12.5L18 10a3 3 0 0 0-4-4l-2.5 2.5" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  alert: (
    <>
      <path d="M12 3.5l9.5 16.5h-19z" />
      <path d="M12 9.5v5M12 16.8v1" />
    </>
  ),
  error: (
    <>
      <path d="M12 2.5l9.5 9.5-9.5 9.5L2.5 12z" />
      <path d="M12 7.5v5.5M12 15.3v1" />
    </>
  ),
  info: (
    <>
      <path d="M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z" />
      <path d="M12 10.5v6M12 7.3v1" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  fit: <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  clock: (
    <>
      <path d="M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z" />
      <path d="M12 7v5h4" />
    </>
  ),
  chevron: <path d="M9 5.5l6.5 6.5L9 18.5" />,
  reset: <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 9M4.5 4v5h5" />,
}

type Props = SVGProps<SVGSVGElement> & { name: string; size?: number }

export function Icon({ name, size = 16, ...rest }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {ICONS[name]}
    </svg>
  )
}

/** The Parti mark: a split plan with one room marked in redline. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="mark">
      <rect x="4.5" y="4.5" width="23" height="23" fill="var(--sheet)" stroke="var(--ink)" strokeWidth="2.5" />
      <path d="M4.5 18.5h23M14 4.5v14M20.5 18.5v9" stroke="var(--ink)" strokeWidth="1.6" fill="none" />
      <rect className="mark-room" x="16.4" y="7" width="8.6" height="9" fill="var(--accent)" />
    </svg>
  )
}

/** Structural grid bubble: a lettered circle, the drawing set's index marker. */
export function Bubble({ children, size = 'md', active = false }: { children: ReactNode; size?: 'sm' | 'md' | 'lg'; active?: boolean }) {
  return (
    <span className={`bubble bubble-${size} ${active ? 'is-active' : ''}`} aria-hidden="true">
      {children}
    </span>
  )
}
