import type { Candidate } from '../types/planner'

type Props = {
  items: Candidate[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function CandidateList({ items, selectedId, onSelect }: Props) {
  return (
    <div className="candidate-grid">
      {items.map((c) => (
        <button
          key={c.id}
          className={`candidate-card ${selectedId === c.id ? 'selected' : ''}`}
          onClick={() => onSelect(c.id)}
        >
          <h3>{c.id}</h3>
          <p>Total Score: {(c.score.total * 100).toFixed(1)}</p>
          <p>Valid: {c.validation.valid ? 'Yes' : 'No'}</p>
          <p>Rooms: {c.rooms.length}</p>
          <p>Doors: {c.openings.doors.length} | Windows: {c.openings.windows.length}</p>
        </button>
      ))}
    </div>
  )
}
