import { useState } from 'react'
import { exportPlan, saveBlob } from '../api'
import type { Candidate, ExportFormat, Units } from '../types'
import { Spinner } from './controls'
import { Icon } from './Icon'

const FORMATS: { id: ExportFormat | 'json'; label: string; desc: string }[] = [
  { id: 'pdf', label: 'PDF', desc: 'A3 sheet at a standard scale, with title block' },
  { id: 'svg', label: 'SVG', desc: 'Vector drawing, 1:100 at printed size' },
  { id: 'png', label: 'PNG', desc: 'High-resolution image for sharing' },
  { id: 'dxf', label: 'DXF', desc: 'CAD file in metres with named layers' },
  { id: 'json', label: 'JSON', desc: 'Full plan data: rooms, doors, windows, fixtures' },
]

type Props = { candidate: Candidate; units: Units; shareUrl: string; briefPrompt: string }

export function ExportPanel({ candidate, units, shareUrl, briefPrompt }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const run = async (id: ExportFormat | 'json') => {
    setBusy(id)
    setError(null)
    setDone(null)
    try {
      if (id === 'json') {
        const data = JSON.stringify({ brief: briefPrompt, candidate }, null, 2)
        saveBlob(new Blob([data], { type: 'application/json' }), `parti-${candidate.id}.json`)
      } else {
        saveBlob(await exportPlan(candidate, id, units), `parti-${candidate.id}.${id}`)
      }
      setDone(id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      setError('Copy failed. Select the link and copy it manually.')
    }
  }

  return (
    <div className="export">
      <ul className="formats">
        {FORMATS.map((f) => (
          <li key={f.id}>
            <button type="button" className="format" onClick={() => run(f.id)} disabled={busy !== null}>
              <span className="format-tag">{f.label}</span>
              <span className="format-desc">{f.desc}</span>
              <span className="format-state">{busy === f.id ? <Spinner /> : done === f.id ? <Icon name="check" /> : <Icon name="download" />}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="fine">Labels and dimensions use {units === 'imperial' ? 'feet and inches' : 'metres'}; switch units in the top bar.</p>
      {error && <p className="inline-error">{error}</p>}
      <div className="share">
        <h3>Share</h3>
        <p className="fine">The link encodes the brief. Plans are regenerated identically when it is opened.</p>
        <div className="share-row">
          <input readOnly value={shareUrl} aria-label="Share link" onFocus={(e) => e.currentTarget.select()} />
          <button type="button" className="btn" onClick={copy}>
            <Icon name={copied ? 'check' : 'link'} />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
    </div>
  )
}
