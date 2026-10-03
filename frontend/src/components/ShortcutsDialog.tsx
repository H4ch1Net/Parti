import { useEffect, useRef } from 'react'
import { Kbd, MOD } from './controls'
import { Icon } from './Icon'

const SHORTCUTS: [string[], string][] = [
  [[MOD, '↵'], 'Generate plans'],
  [['←', '→'], 'Previous / next variant'],
  [['1', '2', '3'], 'Switch level'],
  [['+', '−'], 'Zoom in / out'],
  [['0'], 'Fit plan to view'],
  [['F'], 'Toggle furniture'],
  [['L'], 'Toggle labels'],
  [['D'], 'Toggle dimensions'],
  [['U'], 'Switch m² / ft²'],
  [['Esc'], 'Clear room selection'],
  [['?'], 'Show this help'],
]

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} className="dialog" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()} aria-labelledby="shortcuts-title">
      <header>
        <h2 id="shortcuts-title">Keyboard shortcuts</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
      </header>
      <dl className="shortcuts">
        {SHORTCUTS.map(([keys, label]) => (
          <div key={label}>
            <dt>
              {keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </dt>
            <dd>{label}</dd>
          </div>
        ))}
      </dl>
      <p className="fine">On the plan: scroll to zoom, drag to pan, double-click to fit, click a room for details.</p>
    </dialog>
  )
}
