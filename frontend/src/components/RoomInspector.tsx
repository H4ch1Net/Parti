import { formatArea, formatDims, signedPercent } from '../lib/units'
import type { Candidate, Units } from '../types'
import { Icon } from './Icon'

const FIXTURE_NAMES: Record<string, string> = {
  bed: 'Bed',
  nightstand: 'Nightstand',
  wardrobe: 'Wardrobe',
  closet: 'Closet',
  sofa: 'Sofa',
  armchair: 'Armchair',
  coffee_table: 'Coffee table',
  tv_unit: 'TV unit',
  counter: 'Counter',
  sink: 'Sink',
  stove: 'Cooktop',
  fridge: 'Fridge',
  island: 'Island',
  bathtub: 'Bathtub',
  shower: 'Shower',
  toilet: 'Toilet',
  vanity: 'Vanity',
  washer: 'Washer',
  dryer: 'Dryer',
  utility_sink: 'Utility sink',
  desk: 'Desk',
  bookshelf: 'Bookshelf',
  shelving: 'Shelving',
  meeting_table: 'Meeting table',
  reception_desk: 'Reception desk',
  car: 'Car space',
  rack: 'Server rack',
  bench: 'Bench',
}

type Props = { candidate: Candidate; roomId: string; units: Units; side?: 'left' | 'right'; onClose: () => void; onSelectRoom: (id: string) => void }

export function RoomInspector({ candidate, roomId, units, side = 'right', onClose, onSelectRoom }: Props) {
  const room = candidate.rooms.find((r) => r.id === roomId)
  if (!room) return null
  const byId = Object.fromEntries(candidate.rooms.map((r) => [r.id, r]))
  const windows = candidate.windows.filter((w) => w.room_id === room.id)
  const glazing = (windows.reduce((s, w) => s + w.width, 0) * 1.2) / room.area_sqm
  const links = candidate.connections
    .filter((c) => c.from_room === room.id || c.to_room === room.id)
    .map((c) => ({ id: c.from_room === room.id ? c.to_room : c.from_room, kind: c.kind }))
  const entry = candidate.doors.some((d) => d.kind === 'entry' && d.room_b === room.id)
  const fixtures = Object.entries(
    candidate.fixtures
      .filter((f) => f.room_id === room.id)
      .reduce<Record<string, number>>((acc, f) => {
        const name = f.type.startsWith('dining_table') ? `Table for ${f.type.split('_').pop()}` : (FIXTURE_NAMES[f.type] ?? f.type)
        acc[name] = (acc[name] ?? 0) + 1
        return acc
      }, {}),
  )
  const issues = candidate.validation.issues.filter((i) => i.room_ids.includes(room.id))
  const delta = room.target_area_sqm > 0 && room.type !== 'corridor' && room.type !== 'stair' ? room.area_sqm / room.target_area_sqm - 1 : null

  return (
    <aside className={`inspector inspector-${side}`} aria-label={`${room.name} details`}>
      <header>
        <span className={`swatch zone-${room.zone}`} aria-hidden="true" />
        <div>
          <h3>{room.name}</h3>
          <p className="muted small">
            {room.zone.charAt(0).toUpperCase() + room.zone.slice(1)} zone{candidate.floors > 1 && ` · Level ${room.floor}`}
          </p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close room details" title="Close (Esc)">
          <Icon name="close" />
        </button>
      </header>
      <dl className="inspector-stats">
        <div>
          <dt>Area</dt>
          <dd className="mono">
            {formatArea(room.area_sqm, units)}
            {delta !== null && <small className={Math.abs(delta) > 0.25 ? 'delta warn' : 'delta'}>{signedPercent(delta)} vs target</small>}
          </dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd className="mono">{formatDims(room.width_m, room.depth_m, units)}</dd>
        </div>
        <div>
          <dt>Daylight</dt>
          <dd className="mono">
            {windows.length ? (
              <>
                {windows.length} window{windows.length > 1 ? 's' : ''}
                <small className="delta">{Math.round(glazing * 100)}% glazing</small>
              </>
            ) : (
              'None'
            )}
          </dd>
        </div>
      </dl>
      {(links.length > 0 || entry) && (
        <div className="inspector-block">
          <h4>Connects to</h4>
          <ul className="link-list">
            {entry && <li className="chip">Outside (front door)</li>}
            {links.map((l) => (
              <li key={l.id}>
                <button type="button" className="chip chip-btn" onClick={() => onSelectRoom(l.id)}>
                  {byId[l.id]?.name ?? l.id}
                  <span className="muted">{l.kind === 'door' ? ' · door' : l.kind === 'stair' ? ' · stair' : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {fixtures.length > 0 && (
        <div className="inspector-block">
          <h4>Furniture</h4>
          <p className="small">{fixtures.map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(', ')}</p>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="checks compact">
          {issues.map((i, n) => (
            <li key={n} className={`check check-${i.severity}`}>
              <span>
                <Icon name={i.severity === 'error' ? 'error' : 'alert'} size={14} />
                {i.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
