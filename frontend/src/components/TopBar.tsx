import type { Units } from '../types'
import { Segmented } from './controls'
import { Icon, Mark } from './Icon'

export type ThemePref = 'system' | 'light' | 'dark'

type Props = {
  units: Units
  theme: ThemePref
  onUnits: (u: Units) => void
  onTheme: (t: ThemePref) => void
  onHelp: () => void
}

const NEXT_THEME: Record<ThemePref, ThemePref> = { system: 'light', light: 'dark', dark: 'system' }
const THEME_ICON: Record<ThemePref, string> = { system: 'contrast', light: 'sun', dark: 'moon' }
const THEME_LABEL: Record<ThemePref, string> = { system: 'Auto', light: 'Vellum', dark: 'Cyanotype' }

export function TopBar({ units, theme, onUnits, onTheme, onHelp }: Props) {
  return (
    <header className="masthead">
      <a className="brand" href="./" aria-label="Parti home">
        <Mark />
        <span className="wordmark">Parti</span>
      </a>
      <p className="masthead-note">
        <span className="brand-tag">Schematic floor plans from a written brief</span>
        <span className="nfc">Not for construction</span>
      </p>
      <nav className="masthead-tools" aria-label="Preferences">
        <Segmented
          label="Units"
          size="sm"
          value={units}
          options={[
            { value: 'metric', label: 'm²' },
            { value: 'imperial', label: 'ft²' },
          ]}
          onChange={onUnits}
        />
        <button
          type="button"
          className="tool-btn"
          onClick={() => onTheme(NEXT_THEME[theme])}
          aria-label={`Theme: ${THEME_LABEL[theme]}. Switch theme`}
          title={`Theme: ${THEME_LABEL[theme]}`}
        >
          <Icon name={THEME_ICON[theme]} />
          <span className="tool-label">{THEME_LABEL[theme]}</span>
        </button>
        <button type="button" className="tool-btn" onClick={onHelp} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
          <Icon name="keyboard" />
        </button>
        <a
          className="tool-btn"
          href="https://github.com/H4ch1Net/Parti"
          target="_blank"
          rel="noreferrer"
          aria-label="Source on GitHub"
          title="Source on GitHub"
        >
          <Icon name="github" />
        </a>
      </nav>
    </header>
  )
}
