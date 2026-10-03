import { type CSSProperties, useState } from 'react'
import { formatArea, formatDims, formatLength, signedPercent } from '../lib/units'
import type { Candidate, Units } from '../types'
import { ExportPanel } from './ExportPanel'
import { SectionHead } from './controls'
import { Bubble, Icon } from './Icon'

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
      <SectionHead index="4" title="Sheet" note={c.floors > 1 ? `${c.floors} levels` : undefined} />

      <div className="titleblock">
        <div className="tb-cell tb-title">
          <span className="tb-label">Drawing</span>
          <h2 id="details-title">{c.label}</h2>
          <span className="tb-sub">{c.strategy}</span>
          <Bubble size="lg" active>
            {c.label.replace('Variant ', '')}
          </Bubble>
        </div>
        <div className={`tb-cell tb-score grade-${c.score.grade}`} title={`Overall score ${c.score.total.toFixed(1)} / 100`}>
          <span className="tb-label">Score</span>
          <div className="tb-score-row">
            <strong className="numeral">{Math.round(c.score.total)}</strong>
            <span className="tb-of">/100</span>
            <span className="tb-grade">{GRADE_LABEL[c.score.grade]}</span>
          </div>
          <ScaleMeter value={c.score.total} label="Overall score" />
        </div>
        <dl className="tb-grid">
          <div className="tb-cell">
            <dt className="tb-label">Area</dt>
            <dd>
              {formatArea(total, p.units, 1)}
              <small className={Math.abs(total / p.targetArea - 1) > 0.05 ? 'delta warn' : 'delta'}>{signedPercent(total / p.targetArea - 1)}</small>
            </dd>
          </div>
          <div className="tb-cell">
            <dt className="tb-label">Footprint</dt>
            <dd className="nowrap-metric">
              {p.units === 'metric'
                ? `${c.footprint.width_m.toFixed(1)} × ${c.footprint.depth_m.toFixed(1)} m`
                : `${formatLength(c.footprint.width_m, p.units)} × ${formatLength(c.footprint.depth_m, p.units)}`}
            </dd>
          </div>
          <div className="tb-cell">
            <dt className="tb-label">Checks</dt>
            <dd className={errors.length ? 'status-bad' : warnings.length ? 'status-note' : 'status-ok'}>
              <Icon name={errors.length ? 'error' : warnings.length ? 'alert' : 'check'} size={14} />
              {errors.length ? `${errors.length} error${errors.length > 1 ? 's' : ''}` : warnings.length ? `${warnings.length} note${warnings.length > 1 ? 's' : ''}` : 'All pass'}
            </dd>
          </div>
        </dl>
      </div>

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

/** Score meter drawn as an architectural scale bar: alternating ten-point blocks. */
function ScaleMeter({ value, label, flagged = false }: { value: number; label: string; flagged?: boolean }) {
  return (
    <div
      className={`scale-meter ${flagged ? 'is-flagged' : ''}`}
      role="meter"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span className="scale-fill" style={{ '--v': `${Math.max(0, Math.min(100, value))}%` } as CSSProperties} />
    </div>
  )
}

function ScoreView({ candidate }: { candidate: Candidate }) {
  const s = candidate.score
  const weakest = s.categories.reduce((a, b) => (b.score < a.score ? b : a), s.categories[0])
  return (
    <div className="score-view">
      <p className="summary">{s.summary}</p>
      <ul className="bars">
        {s.categories.map((cat) => {
          const flagged = cat.key === weakest?.key && cat.score < 95
          return (
            <li key={cat.key} className={flagged ? 'is-weakest' : ''}>
              <div className="bar-head">
                <span className="bar-label">{cat.label}</span>
                {flagged && <span className="redline-tag">Weakest</span>}
                <span className="bar-value">{Math.round(cat.score)}</span>
              </div>
              <ScaleMeter value={cat.score} label={cat.label} flagged={flagged} />
              <p className="bar-detail">{cat.detail}</p>
            </li>
          )
        })}
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
                    <span className={`swatch zone-${r.zone}`} aria-hidden="true" />
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
