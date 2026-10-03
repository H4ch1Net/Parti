import type { Units } from '../types'

export const SQFT_PER_SQM = 10.7639

export function feetInches(m: number): string {
  const inches = Math.round(m / 0.0254)
  return `${Math.floor(inches / 12)}'-${inches % 12}"`
}

export function formatArea(sqm: number, units: Units, digits = 1): string {
  if (units === 'imperial') return `${Math.round(sqm * SQFT_PER_SQM).toLocaleString('en-US')} ft²`
  return `${sqm.toFixed(digits)} m²`
}

export function formatLength(m: number, units: Units): string {
  return units === 'imperial' ? feetInches(m) : `${m.toFixed(2)} m`
}

export function formatDims(w: number, d: number, units: Units): string {
  return units === 'imperial' ? `${feetInches(w)} × ${feetInches(d)}` : `${w.toFixed(1)} × ${d.toFixed(1)} m`
}

export function areaToDisplay(sqm: number, units: Units): number {
  return units === 'imperial' ? Math.round(sqm * SQFT_PER_SQM) : Math.round(sqm * 10) / 10
}

export function areaFromDisplay(value: number, units: Units): number {
  return units === 'imperial' ? value / SQFT_PER_SQM : value
}

export function signedPercent(value: number): string {
  const pct = Math.round(value * 100)
  return `${pct > 0 ? '+' : ''}${pct}%`
}
