import { areaFromDisplay, areaToDisplay } from '../lib/units'
import type { Brief, RoomType, RoomTypeInfo, Units } from '../types'
import { Segmented, Stepper } from './controls'

const RESIDENTIAL_ORDER: RoomType[] = ['bedroom', 'bathroom', 'ensuite', 'powder', 'living', 'dining', 'kitchen', 'study', 'laundry', 'storage', 'garage', 'studio']
const COMMERCIAL_ORDER: RoomType[] = ['reception', 'open_office', 'private_office', 'meeting_room', 'break_room', 'bathroom', 'storage', 'server_room']

const DEFAULT_ROOMS: Record<Brief['building_type'], Brief['rooms']> = {
  residential: [
    { type: 'entry', count: 1 },
    { type: 'living', count: 1 },
    { type: 'kitchen', count: 1 },
    { type: 'bedroom', count: 2 },
    { type: 'bathroom', count: 1 },
  ],
  commercial: [
    { type: 'reception', count: 1 },
    { type: 'open_office', count: 1 },
    { type: 'meeting_room', count: 1 },
    { type: 'bathroom', count: 1 },
  ],
}

type Props = {
  brief: Brief
  roomTypes: RoomTypeInfo[]
  units: Units
  onChange: (brief: Brief) => void
}

export function ProgramEditor({ brief, roomTypes, units, onChange }: Props) {
  const labels = Object.fromEntries(roomTypes.map((t) => [t.type, t.label])) as Record<RoomType, string>
  const order = brief.building_type === 'commercial' ? COMMERCIAL_ORDER : RESIDENTIAL_ORDER
  const count = (t: RoomType) => brief.rooms.find((r) => r.type === t)?.count ?? 0

  const setCount = (t: RoomType, n: number) => {
    const rooms = brief.rooms.some((r) => r.type === t)
      ? brief.rooms.map((r) => (r.type === t ? { ...r, count: n } : r))
      : [...brief.rooms, { type: t, count: n }]
    onChange({ ...brief, rooms: rooms.filter((r) => r.count > 0) })
  }

  const area = areaToDisplay(brief.target_area_sqm, units)
  const unitLabel = units === 'imperial' ? 'ft²' : 'm²'

  return (
    <div className="program">
      <div className="field-row">
        <Segmented
          label="Building type"
          value={brief.building_type}
          options={[
            { value: 'residential', label: 'Home' },
            { value: 'commercial', label: 'Office' },
          ]}
          onChange={(t) => onChange({ ...brief, building_type: t, rooms: DEFAULT_ROOMS[t] })}
        />
        <Segmented
          label="Layout style"
          value={brief.style}
          options={[
            { value: 'open_plan', label: 'Open', title: 'Living, dining and kitchen flow together' },
            { value: 'traditional', label: 'Closed', title: 'Kitchen behind a door' },
          ]}
          onChange={(style) => onChange({ ...brief, style })}
        />
      </div>

      <div className="field-row">
        <label className="field">
          <span>Total area</span>
          <span className="input-unit">
            <input
              type="number"
              inputMode="decimal"
              min={units === 'imperial' ? 200 : 18}
              max={units === 'imperial' ? 16000 : 1500}
              step={units === 'imperial' ? 50 : 5}
              value={area}
              onChange={(e) => {
                const v = Number(e.target.value)
                if (Number.isFinite(v) && v > 0) {
                  const sqm = Math.min(1500, Math.max(15, areaFromDisplay(v, units)))
                  onChange({ ...brief, target_area_sqm: Math.round(sqm * 100) / 100, area_source: 'stated' })
                }
              }}
            />
            <em>{unitLabel}</em>
          </span>
        </label>
        <div className="field">
          <span>Levels</span>
          <Segmented
            label="Levels"
            size="sm"
            value={brief.stories}
            options={[1, 2, 3].map((n) => ({ value: n, label: String(n) }))}
            onChange={(stories) => onChange({ ...brief, stories })}
          />
        </div>
      </div>

      <div className="steppers">
        {order.map((t) => (
          <Stepper
            key={t}
            label={t === 'garage' ? 'Garage' : labels[t] ?? t}
            hint={t === 'garage' ? 'cars' : undefined}
            value={count(t)}
            max={t === 'garage' ? 3 : 12}
            onChange={(n) => setCount(t, n)}
          />
        ))}
      </div>

      <fieldset className="prefs">
        <legend>Priorities</legend>
        {(
          [
            ['daylight', 'Daylight'],
            ['privacy', 'Privacy'],
            ['compact', 'Compact circulation'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="check-chip">
            <input
              type="checkbox"
              checked={brief.preferences[key]}
              onChange={(e) => onChange({ ...brief, preferences: { ...brief.preferences, [key]: e.target.checked } })}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
    </div>
  )
}
