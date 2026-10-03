import { useState } from 'react'
import { formatArea, formatDims, formatLength, signedPercent } from '../lib/units'
import type { Candidate, Units } from '../types'
import { ExportPanel } from './ExportPanel'
import { Icon } from './Icon'

export type DetailTab = 'score' | 'rooms' | 'checks' | 'export'

type Props = {
  candidate: Candidate
  targetArea: number
  units: Units
  tab: DetailTab
  onTab: (t: DetailTab) => void
  selectedRoom: string | null
  hoverRoom: string | null
  onSelectRoom: (id: string | null) => void
  onHoverRoom: (id: string | null) => void
  shareUrl: string
  briefPrompt: string
}

const GRADE_LABEL = { excellent: 'Excellent', good: 'Good', fair: 'Fair', weak: 'Weak' }

export function DetailsPanel(p: Props) {
  const c = p.candidate
  const total = c.rooms.reduce((s, r) => s + r.area_sqm, 0)
  const errors = c.validation.issues.filter((i) => i.severity === 'error')
  const warnings = c.validation.issues.filter((i) => i.severity === 'warning')
  const tabs: { id: DetailTab; label: string; count?: number }[] = [
    { id: 'score', label: 'Score' },
    { id: 'rooms', label: 'Rooms', count: c.rooms.length },
    { id: 'checks', label: 'Checks', count: errors.length + warnings.length },
    { id: 'export', label: 'Export' },
  ]

  return (
    <section className="panel details" aria-labelledby="details-title">
      <header className="details-head">
        <div>
          <h2 id="details-title">{c.label}</h2>
          <p className="muted small">
            {c.strategy}
            {c.floors > 1 && ` · ${c.floors} levels`}
          </p>
        </div>
        <ScoreDial value={c.score.total} grade={c.score.grade} />
      </header>

      <dl className="stats">
        <div>
          <dt>Area</dt>
          <dd>
            {formatArea(total, p.units, 1)}
            <small className={Math.abs(total / p.targetArea - 1) > 0.05 ? 'delta warn' : 'delta'}>{signedPercent(total / p.targetArea - 1)}</small>
          </dd>
        </div>
        <div>
          <dt>Footprint</dt>
          <dd className="nowrap-metric">
            {p.units === 'metric'
              ? `${c.footprint.width_m.toFixed(1)} × ${c.footprint.depth_m.toFixed(1)} m`
              : `${formatLength(c.footprint.width_m, p.units)} × ${formatLength(c.footprint.depth_m, p.units)}`}
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd className={errors.length ? 'status-bad' : 'status-ok'}>
            <Icon name={errors.length ? 'error' : 'check'} size={14} />
            {errors.length ? `${errors.length} error${errors.length > 1 ? 's' : ''}` : warnings.length ? `${warnings.length} note${warnings.length > 1 ? 's' : ''}` : 'Passes'}
          </dd>
        </div>
      </dl>

      <div className="tabs" role="tablist" aria-label="Plan details">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={p.tab === t.id}
            aria-controls={`tabpanel-${t.id}`}
            className={p.tab === t.id ? 'is-on' : ''}
            onClick={() => p.onTab(t.id)}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && <span className="tab-count">{t.count}</span>}
          </button>
        ))}
      </div>

      <div className="tabpanel" role="tabpanel" id={`tabpanel-${p.tab}`} aria-labelledby={`tab-${p.tab}`}>
        {p.tab === 'score' && <ScoreView candidate={c} />}
        {p.tab === 'rooms' && <RoomsTable {...p} total={total} />}
        {p.tab === 'checks' && <ChecksList candidate={c} onSelectRoom={p.onSelectRoom} onHoverRoom={p.onHoverRoom} />}
        {p.tab === 'export' && <ExportPanel candidate={c} units={p.units} shareUrl={p.shareUrl} briefPrompt={p.briefPrompt} />}
      </div>
    </section>
  )
}

function ScoreDial({ value, grade }: { value: number; grade: Candidate['score']['grade'] }) {
  const r = 22
  const circ = 2 * Math.PI * r
  return (
    <div className={`dial grade-${grade}`} title={`Overall score ${value.toFixed(1)} / 100`}>
      <div className="dial-ring">
        <svg viewBox="0 0 56 56" width="52" height="52" aria-hidden="true">
          <circle cx="28" cy="28" r={r} className="dial-track" />
          <circle cx="28" cy="28" r={r} className="dial-value" strokeDasharray={`${(circ * value) / 100} ${circ}`} transform="rotate(-90 28 28)" />
        </svg>
        <strong>{Math.round(value)}</strong>
      </div>
      <span className="dial-grade">{GRADE_LABEL[grade]}</span>
    </div>
  )
}

function ScoreView({ candidate }: { candidate: Candidate }) {
  const s = candidate.score
  return (
    <div className="score-view">
      <p className="summary">{s.summary}</p>
      <ul className="bars">
        {s.categories.map((cat) => (
          <li key={cat.key}>
            <div className="bar-head">
              <span>{cat.label}</span>
              <span className="mono">{Math.round(cat.score)}</span>
            </div>
            <div className="bar" role="meter" aria-valuenow={Math.round(cat.score)} aria-valuemin={0} aria-valuemax={100} aria-label={cat.label}>
              <span style={{ width: `${cat.score}%` }} className={cat.score >= 85 ? 'hi' : cat.score >= 65 ? 'mid' : 'lo'} />
            </div>
            <p className="bar-detail">{cat.detail}</p>
          </li>
        ))}
      </ul>
      <p className="fine">Weighted average of the categories above. Plans with blocking errors are capped at 55.</p>
    </div>
  )
}

function RoomsTable(p: Props & { total: number }) {
  const c = p.candidate
  const [sort, setSort] = useState<'plan' | 'area' | 'name'>('plan')
  const rooms = [...c.rooms].sort((a, b) =>
    sort === 'area' ? b.area_sqm - a.area_sqm : sort === 'name' ? a.name.localeCompare(b.name) : a.floor - b.floor,
  )
  const header = (key: typeof sort, label: string, cls = '') => (
    <th scope="col" className={cls} aria-sort={sort === key ? (key === 'area' ? 'descending' : 'ascending') : 'none'}>
      <button type="button" onClick={() => setSort(sort === key ? 'plan' : key)}>
        {label}
      </button>
    </th>
  )
  return (
    <div className="rooms-table-wrap">
      <table className="rooms-table">
        <thead>
          <tr>
            {header('name', 'Room')}
            {header('area', 'Area', 'num')}
            <th scope="col" className="num">
              Size
            </th>
          </tr>
        </thead>
        <tbody>
          {rooms.map((r) => {
            const delta = r.target_area_sqm > 0 && r.type !== 'corridor' && r.type !== 'stair' ? r.area_sqm / r.target_area_sqm - 1 : null
            return (
              <tr
                key={r.id}
                className={`${p.selectedRoom === r.id ? 'is-selected' : ''} ${p.hoverRoom === r.id ? 'is-hover' : ''}`}
                onMouseEnter={() => p.onHoverRoom(r.id)}
                onMouseLeave={() => p.onHoverRoom(null)}
              >
                <td>
                  <button type="button" className="room-link" onClick={() => p.onSelectRoom(p.selectedRoom === r.id ? null : r.id)}>
                    <span className={`zone-dot zone-${r.zone}`} aria-hidden="true" />
                    <span className="room-name">
                      {r.name}
                      {c.floors > 1 && <small className="muted">Level {r.floor}</small>}
                    </span>
                  </button>
                </td>
                <td className="num mono">
                  {formatArea(r.area_sqm, p.units, 1)}
                  {delta !== null && (
                    <small className={`cell-delta ${Math.abs(delta) > 0.25 ? 'warn' : ''}`} title="Compared with the room's target area">
                      {signedPercent(delta)}
                    </small>
                  )}
                </td>
                <td className="num mono muted">{formatDims(r.width_m, r.depth_m, p.units).replace(' m', '')}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td className="num mono">
              {formatArea(p.total, p.units, 1)}
              <small className="cell-delta">{signedPercent(p.total / p.targetArea - 1)}</small>
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

const CHECKED = ['Every room reachable from the front door', 'Minimum room widths', 'A window in every habitable room', 'Essential fixtures fit', 'Rooms tile the footprint']

function ChecksList({ candidate, onSelectRoom, onHoverRoom }: { candidate: Candidate; onSelectRoom: (id: string | null) => void; onHoverRoom: (id: string | null) => void }) {
  const issues = candidate.validation.issues
  if (issues.length === 0) {
    return (
      <div className="checks-empty">
        <Icon name="check" size={20} />
        <p>All checks pass.</p>
        <ul>
          {CHECKED.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <ul className="checks">
      {issues.map((i, n) => (
        <li key={n} className={`check check-${i.severity}`}>
          <button
            type="button"
            disabled={i.room_ids.length === 0}
            onClick={() => onSelectRoom(i.room_ids[0] ?? null)}
            onMouseEnter={() => onHoverRoom(i.room_ids[0] ?? null)}
            onMouseLeave={() => onHoverRoom(null)}
          >
            <Icon name={i.severity === 'error' ? 'error' : 'alert'} size={15} />
            <span>{i.message}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
