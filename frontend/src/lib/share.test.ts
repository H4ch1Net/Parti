import { describe, expect, it } from 'vitest'
import type { Brief } from '../types'
import { briefFromHash, decodeBrief, encodeBrief } from './share'

const brief: Brief = {
  raw_prompt: '3 bed 2 bath house, 1,300 sq ft — café',
  building_type: 'residential',
  target_area_sqm: 120.77,
  area_source: 'stated',
  stories: 1,
  style: 'open_plan',
  rooms: [
    { type: 'bedroom', count: 3 },
    { type: 'bathroom', count: 2 },
    { type: 'study', count: 0 },
  ],
  preferences: { daylight: true, privacy: false, compact: true },
  notes: ['ignored'],
}

describe('share', () => {
  it('round-trips a brief through the URL token', () => {
    const token = encodeBrief(brief)
    expect(token).toMatch(/^[A-Za-z0-9_-]+$/)
    const back = decodeBrief(token)!
    expect(back.raw_prompt).toBe(brief.raw_prompt)
    expect(back.target_area_sqm).toBe(120.77)
    expect(back.rooms).toEqual([
      { type: 'bedroom', count: 3 },
      { type: 'bathroom', count: 2 },
    ])
    expect(back.preferences).toEqual({ daylight: true, privacy: false, compact: true })
  })

  it('reads the brief from a location hash', () => {
    expect(briefFromHash('#b=' + encodeBrief(brief))?.stories).toBe(1)
    expect(briefFromHash('#nothing')).toBeNull()
  })

  it('rejects garbage', () => {
    expect(decodeBrief('not-base64!')).toBeNull()
    expect(decodeBrief(btoa('{"v":2}'))).toBeNull()
  })
})
