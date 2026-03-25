import type { Candidate } from '../types/planner'

export function ScheduleTable({ candidate }: { candidate: Candidate | null }) {
  if (!candidate) return null
  return (
    <div className="panel">
      <h3>Room Schedule</h3>
      <table>
        <thead>
          <tr>
            <th>Room</th>
            <th>Type</th>
            <th>Area (sqm)</th>
            <th>Dimensions</th>
          </tr>
        </thead>
        <tbody>
          {candidate.schedule.map((r, idx) => (
            <tr key={`${r.room_name}-${idx}`}>
              <td>{r.room_name}</td>
              <td>{r.room_type}</td>
              <td>{r.area_sqm.toFixed(2)}</td>
              <td>{r.dimensions_m}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
