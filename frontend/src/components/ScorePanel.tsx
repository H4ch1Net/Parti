import type { Candidate } from '../types/planner'

export function ScorePanel({ candidate }: { candidate: Candidate | null }) {
  if (!candidate) return null
  const s = candidate.score
  return (
    <div className="panel">
      <h3>Score Breakdown</h3>
      <ul>
        <li>Area Accuracy: {s.area_accuracy.toFixed(2)}</li>
        <li>Adjacency: {s.adjacency_quality.toFixed(2)}</li>
        <li>Zoning: {s.zoning_quality.toFixed(2)}</li>
        <li>Privacy: {s.privacy.toFixed(2)}</li>
        <li>Circulation: {s.circulation_efficiency.toFixed(2)}</li>
        <li>Daylight: {s.daylight_potential.toFixed(2)}</li>
        <li>Furniture: {s.furniture_usability.toFixed(2)}</li>
        <li>Compactness: {s.compactness.toFixed(2)}</li>
        <li>Wall Efficiency: {s.wall_efficiency.toFixed(2)}</li>
      </ul>
      <strong>Total: {(s.total * 100).toFixed(1)}</strong>
      <p>{s.explanation}</p>
    </div>
  )
}
