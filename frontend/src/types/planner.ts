export type ScoreBreakdown = {
  area_accuracy: number
  adjacency_quality: number
  zoning_quality: number
  privacy: number
  circulation_efficiency: number
  daylight_potential: number
  furniture_usability: number
  compactness: number
  wall_efficiency: number
  total: number
  explanation: string
}

export type ValidationReport = {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export type Candidate = {
  id: string
  rooms: Array<{
    id: string
    name: string
    type: string
    area_sqm: number
    width_m: number
    depth_m: number
    polygon: number[][]
  }>
  openings: {
    doors: any[]
    windows: any[]
  }
  schedule: Array<{
    room_name: string
    room_type: string
    area_sqm: number
    dimensions_m: string
  }>
  score: ScoreBreakdown
  validation: ValidationReport
}

export type GenerateResponse = {
  best_candidate_id: string
  candidates: Candidate[]
  brief: any
  program: any
}
