import { useLayoutEffect, useRef } from 'react'
import { formatArea } from '../lib/units'
import type { Candidate, Units } from '../types'
import { Bubble } from './Icon'

function Thumb({ svg }: { svg: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current?.querySelector('svg')
    const plan = el?.getAttribute('data-plan')
    if (!el || !plan) return
    const [x, y, w, h] = plan.split(' ').map(Number)
    const pad = Math.max(w, h) * 0.06
    el.setAttribute('viewBox', `${x - pad} ${y - pad} ${w + 2 * pad} ${h + 2 * pad}`)
  }, [svg])
  return <div ref={ref} className="thumb" dangerouslySetInnerHTML={{ __html: svg }} />
}

type Props = {
  candidates: Candidate[]
  drawings: Record<string, string[]>
  selectedId: string | null
  units: Units
  onSelect: (id: string) => void
}

export function VariantStrip({ candidates, drawings, selectedId, units, onSelect }: Props) {
  return (
    <div className="variants" role="listbox" aria-label="Plan variants" aria-orientation="horizontal">
      {candidates.map((c) => (
        <button
          key={c.id}
          type="button"
          role="option"
          aria-selected={c.id === selectedId}
          className={`variant ${c.id === selectedId ? 'is-selected' : ''}`}
          onClick={() => onSelect(c.id)}
          title={`${c.label} · ${c.strategy}`}
        >
          <span className="variant-head">
            <Bubble active={c.id === selectedId}>{c.label.replace('Variant ', '')}</Bubble>
            <span className="variant-score">
              <strong>{Math.round(c.score.total)}</strong>
              <small className={`grade-${c.score.grade}`}>{c.score.grade}</small>
            </span>
          </span>
          <Thumb svg={drawings[c.id]?.[0] ?? ''} />
          <span className="variant-sub">
            {c.strategy} · {formatArea(c.footprint.area_sqm * c.floors, units, 0)}
          </span>
        </button>
      ))}
    </div>
  )
}
