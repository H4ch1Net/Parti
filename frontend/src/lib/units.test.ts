import { describe, expect, it } from 'vitest'
import { areaFromDisplay, areaToDisplay, feetInches, formatArea, formatDims, signedPercent } from './units'

describe('units', () => {
  it('formats feet and inches with carry', () => {
    expect(feetInches(3.6)).toBe(`11'-10"`)
    expect(feetInches(0.3048)).toBe(`1'-0"`)
    expect(feetInches(3.6576)).toBe(`12'-0"`)
  })

  it('formats areas in both systems', () => {
    expect(formatArea(74.32, 'metric')).toBe('74.3 m²')
    expect(formatArea(74.32, 'imperial')).toBe('800 ft²')
    expect(formatArea(185.8, 'imperial')).toBe('2,000 ft²')
  })

  it('round-trips display areas', () => {
    expect(areaToDisplay(74.32, 'imperial')).toBe(800)
    expect(areaFromDisplay(800, 'imperial')).toBeCloseTo(74.32, 1)
    expect(areaToDisplay(74.32, 'metric')).toBe(74.3)
  })

  it('formats dims and percentages', () => {
    expect(formatDims(3.6, 4.2, 'metric')).toBe('3.6 × 4.2 m')
    expect(signedPercent(0.123)).toBe('+12%')
    expect(signedPercent(-0.05)).toBe('-5%')
    expect(signedPercent(0)).toBe('0%')
  })
})
