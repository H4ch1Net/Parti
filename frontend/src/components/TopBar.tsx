import type { Units } from '../types'
import { Segmented } from './controls'
import { Icon, Logo } from './Icon'

export type ThemePref = 'system' | 'light' | 'dark'

type Props = {
  units: Units
  theme: ThemePref
  onUnits: (u: Units) => void
  onTheme: (t: ThemePref) => void
  onHelp: () => void
}

const NEXT_THEME: Record<ThemePref, ThemePref> = { system: 'light', light: 'dark', dark: 'system' }
const THEME_ICON: Record<ThemePref, string> = { system: 'monitor', light: 'sun', dark: 'moon' }

export function TopBar({ units, theme, onUnits, onTheme, onHelp }: Props) {
  return (
    <header className="topbar">
      <a className="brand" href="./" aria-label="Parti home">
        <Logo />
        <span className="brand-name">Parti</span>
        <span className="brand-tag">Floor plans from a brief</span>
      </a>
      <nav className="topbar-actions" aria-label="Preferences">
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
        <button type="button" className="icon-btn" onClick={() => onTheme(NEXT_THEME[theme])} aria-label={`Theme: ${theme}. Switch theme`} title={`Theme: ${theme}`}>
          <Icon name={THEME_ICON[theme]} />
        </button>
        <button type="button" className="icon-btn" onClick={onHelp} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
          <Icon name="keyboard" />
        </button>
        <a className="icon-btn" href="https://github.com/H4ch1Net/Parti" target="_blank" rel="noreferrer" aria-label="Source on GitHub" title="Source on GitHub">
          <Icon name="github" />
        </a>
      </nav>
    </header>
  )
}
