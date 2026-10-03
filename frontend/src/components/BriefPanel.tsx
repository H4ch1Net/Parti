import { formatArea } from '../lib/units'
import type { Brief, Example, RoomTypeInfo, Units } from '../types'
import { Kbd, MOD, Spinner } from './controls'
import { Icon } from './Icon'
import { ProgramEditor } from './ProgramEditor'

export type RecentBrief = { prompt: string; brief: Brief; at: number }

type Props = {
  prompt: string
  brief: Brief | null
  briefEdited: boolean
  interpreting: boolean
  interpretError: string | null
  generating: boolean
  examples: Example[]
  recent: RecentBrief[]
  roomTypes: RoomTypeInfo[]
  units: Units
  onPromptChange: (v: string) => void
  onBriefChange: (b: Brief) => void
  onResetBrief: () => void
  onGenerate: () => void
  onPickRecent: (r: RecentBrief) => void
  onClearRecent: () => void
}

function roomChips(brief: Brief, roomTypes: RoomTypeInfo[]): string[] {
  const label = (t: string) => roomTypes.find((r) => r.type === t)?.label ?? t
  return brief.rooms
    .filter((r) => r.count > 0 && !['entry', 'corridor', 'stair'].includes(r.type))
    .map((r) => {
      if (r.type === 'garage') return `${r.count}-car garage`
      const name = label(r.type).toLowerCase()
      return r.count === 1 ? name.charAt(0).toUpperCase() + name.slice(1) : `${r.count} ${name}s`
    })
}

export function BriefPanel(p: Props) {
  const b = p.brief
  return (
    <section className="panel brief" aria-labelledby="brief-title">
      <header className="panel-head">
        <h2 id="brief-title">Brief</h2>
        <span className="muted small">Describe the building in plain language</span>
      </header>

      <div className="prompt-box">
        <textarea
          aria-label="Describe the floor plan"
          value={p.prompt}
          rows={4}
          maxLength={2000}
          placeholder="e.g. 3 bed 2 bath house, 1,400 sq ft, open plan with a home office"
          onChange={(e) => p.onPromptChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              p.onGenerate()
            }
          }}
        />
        <button type="button" className="btn btn-primary btn-block" onClick={p.onGenerate} disabled={p.generating || (!b && !p.prompt.trim())}>
          {p.generating ? <Spinner /> : <Icon name="sparkle" />}
          <span>{p.generating ? 'Generating plans…' : 'Generate plans'}</span>
          {!p.generating && (
            <span className="btn-hint" aria-hidden="true">
              <Kbd>{MOD}</Kbd>
              <Kbd>↵</Kbd>
            </span>
          )}
        </button>
      </div>

      <div className="understood" aria-live="polite">
        <div className="understood-head">
          <h3>Understood</h3>
          {p.interpreting && <Spinner size={12} />}
          {p.briefEdited && (
            <button type="button" className="link-btn" onClick={p.onResetBrief} title="Discard program edits and re-read the text">
              <Icon name="reset" size={13} /> Reset to text
            </button>
          )}
        </div>
        {p.interpretError && <p className="inline-error">{p.interpretError}</p>}
        {b && (
          <>
            <ul className="chips">
              <li className="chip chip-strong">{b.building_type === 'commercial' ? 'Office' : 'Home'}</li>
              <li className="chip chip-strong" title={b.area_source === 'estimated' ? 'Estimated from the rooms' : 'From your brief'}>
                {formatArea(b.target_area_sqm, p.units, 0)}
                {b.area_source === 'estimated' && <span className="chip-flag">est.</span>}
              </li>
              {b.stories > 1 && <li className="chip">{b.stories} levels</li>}
              <li className="chip">{b.style === 'open_plan' ? 'Open plan' : 'Closed kitchen'}</li>
              {roomChips(b, p.roomTypes).map((c) => (
                <li key={c} className="chip">
                  {c}
                </li>
              ))}
            </ul>
            {b.notes.length > 0 && (
              <ul className="notes">
                {b.notes.map((n) => (
                  <li key={n}>
                    <Icon name="info" size={13} />
                    {n}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {b && (
        <details className="disclosure">
          <summary>
            <Icon name="chevron" size={14} className="disclosure-icon" />
            Adjust program
            {p.briefEdited && <span className="badge">edited</span>}
          </summary>
          <ProgramEditor brief={b} roomTypes={p.roomTypes} units={p.units} onChange={p.onBriefChange} />
        </details>
      )}

      {p.examples.length > 0 && (
        <div className="examples">
          <h3>Examples</h3>
          <ul>
            {p.examples.map((ex) => (
              <li key={ex.title}>
                <button type="button" className="example" onClick={() => p.onPromptChange(ex.prompt)} title={ex.prompt}>
                  <strong>{ex.title}</strong>
                  <span>{ex.prompt}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.recent.length > 0 && (
        <div className="examples recent">
          <div className="understood-head">
            <h3>Recent</h3>
            <button type="button" className="link-btn" onClick={p.onClearRecent}>
              Clear
            </button>
          </div>
          <ul>
            {p.recent.map((r) => (
              <li key={r.at}>
                <button type="button" className="example" onClick={() => p.onPickRecent(r)}>
                  <Icon name="clock" size={13} />
                  <span>{r.prompt || 'Custom program'}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
