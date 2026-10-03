import type { ReactNode } from 'react'
import { Icon } from './Icon'

type SegmentedProps<T extends string | number> = {
  label: string
  value: T
  options: { value: T; label: ReactNode; title?: string }[]
  onChange: (v: T) => void
  size?: 'sm' | 'md'
}

export function Segmented<T extends string | number>({ label, value, options, onChange, size = 'md' }: SegmentedProps<T>) {
  return (
    <div className={`segmented segmented-${size}`} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          title={o.title}
          className={o.value === value ? 'is-on' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

type StepperProps = { label: string; value: number; min?: number; max?: number; onChange: (v: number) => void; hint?: string }

export function Stepper({ label, value, min = 0, max = 12, onChange, hint }: StepperProps) {
  return (
    <div className={`stepper ${value === 0 ? 'is-zero' : ''}`}>
      <span className="stepper-label">
        {label}
        {hint && <small>{hint}</small>}
      </span>
      <div className="stepper-controls">
        <button type="button" aria-label={`Decrease ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}>
          <Icon name="minus" size={14} />
        </button>
        <output aria-live="polite" aria-label={label}>
          {value}
        </output>
        <button type="button" aria-label={`Increase ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
          <Icon name="plus" size={14} />
        </button>
      </div>
    </div>
  )
}

export function Spinner({ size = 14 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd>{children}</kbd>
}

export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
export const MOD = isMac ? '⌘' : 'Ctrl'

type SectionHeadProps = { index: string; title: string; id?: string; note?: ReactNode; children?: ReactNode }

/** Sheet section header: grid bubble, title, a rule running to the edge, optional tools. */
export function SectionHead({ index, title, id, note, children }: SectionHeadProps) {
  return (
    <div className="section-head">
      <span className="bubble bubble-sm" aria-hidden="true">
        {index}
      </span>
      <h2 id={id}>{title}</h2>
      {note && <span className="section-note">{note}</span>}
      <span className="section-rule" aria-hidden="true" />
      {children}
    </div>
  )
}
