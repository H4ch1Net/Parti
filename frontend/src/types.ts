// Mirrors backend/app/models/schemas.py

export type RoomType =
  | 'entry' | 'living' | 'studio' | 'dining' | 'kitchen' | 'bedroom' | 'bathroom' | 'ensuite'
  | 'powder' | 'corridor' | 'stair' | 'laundry' | 'storage' | 'garage' | 'study' | 'reception'
  | 'open_office' | 'private_office' | 'meeting_room' | 'break_room' | 'server_room'

export type Zone = 'public' | 'private' | 'service' | 'circulation'
export type Point = [number, number]
export type Units = 'metric' | 'imperial'

export type RoomRequest = { type: RoomType; count: number }

export type Preferences = { daylight: boolean; privacy: boolean; compact: boolean }

export type Brief = {
  raw_prompt: string
  building_type: 'residential' | 'commercial'
  target_area_sqm: number
  target_area_sqft?: number
  area_source: 'stated' | 'estimated'
  stories: number
  style: 'open_plan' | 'traditional'
  rooms: RoomRequest[]
  preferences: Preferences
  notes: string[]
}

export type ProgramRoom = {
  id: string
  type: RoomType
  name: string
  zone: Zone
  floor: number
  target_area_sqm: number
  min_area_sqm: number
  primary: boolean
}

export type Program = {
  target_area_sqm: number
  stories: number
  rooms: ProgramRoom[]
  adjacency: { a: string; b: string; weight: number }[]
}

export type Room = {
  id: string
  type: RoomType
  name: string
  zone: Zone
  floor: number
  polygon: Point[]
  width_m: number
  depth_m: number
  area_sqm: number
  target_area_sqm: number
  primary: boolean
}

export type Door = {
  id: string
  kind: 'entry' | 'door' | 'opening' | 'garage'
  floor: number
  room_a: string
  room_b: string
  segment: Point[]
  width: number
  hinge: Point | null
  swing: Point | null
}

export type Window = { id: string; room_id: string; floor: number; segment: Point[]; width: number }

export type Fixture = {
  id: string
  room_id: string
  floor: number
  type: string
  footprint: Point[]
  facing: 'n' | 's' | 'e' | 'w'
}

export type Connection = { from_room: string; to_room: string; kind: 'door' | 'opening' | 'stair'; length_m: number }

export type ScoreCategory = { key: string; label: string; score: number; weight: number; detail: string }

export type Score = {
  total: number
  grade: 'excellent' | 'good' | 'fair' | 'weak'
  categories: ScoreCategory[]
  summary: string
}

export type Issue = { severity: 'error' | 'warning'; code: string; message: string; room_ids: string[] }

export type ValidationReport = { valid: boolean; issues: Issue[] }

export type Candidate = {
  id: string
  label: string
  strategy: string
  floors: number
  footprint: { width_m: number; depth_m: number; area_sqm: number }
  rooms: Room[]
  walls: unknown[]
  doors: Door[]
  windows: Window[]
  fixtures: Fixture[]
  connections: Connection[]
  zones: Record<string, string[]>
  score: Score
  validation: ValidationReport
}

export type GenerateResponse = {
  brief: Brief
  program: Program
  candidates: Candidate[]
  best_candidate_id: string
  drawings: Record<string, string[]>
  elapsed_ms: number
}

export type Example = { title: string; prompt: string }

export type RoomTypeInfo = { type: RoomType; label: string; zone: Zone; residential: boolean; commercial: boolean }

export type ExportFormat = 'svg' | 'pdf' | 'png' | 'dxf'
