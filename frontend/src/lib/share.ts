import type { Brief, RoomType } from '../types'

// Compact, URL-safe encoding of a brief so a plan can be shared as a link.
// Generation is deterministic, so the same brief reproduces the same plans.

type Packed = {
  v: 1
  p: string
  t: Brief['building_type']
  a: number
  s: number
  y: Brief['style']
  r: [RoomType, number][]
  f: number
}

function toBase64Url(text: string): string {
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  bytes.forEach((b) => (bin += String.fromCharCode(b)))
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromBase64Url(text: string): string {
  const b64 = text.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((text.length + 3) % 4)
  const bin = atob(b64)
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)))
}

export function encodeBrief(brief: Brief): string {
  const prefs = brief.preferences
  const packed: Packed = {
    v: 1,
    p: brief.raw_prompt,
    t: brief.building_type,
    a: Math.round(brief.target_area_sqm * 100) / 100,
    s: brief.stories,
    y: brief.style,
    r: brief.rooms.filter((r) => r.count > 0).map((r) => [r.type, r.count]),
    f: (prefs.daylight ? 1 : 0) | (prefs.privacy ? 2 : 0) | (prefs.compact ? 4 : 0),
  }
  return toBase64Url(JSON.stringify(packed))
}

export function decodeBrief(token: string): Brief | null {
  try {
    const p = JSON.parse(fromBase64Url(token)) as Packed
    if (p.v !== 1 || !Array.isArray(p.r) || typeof p.a !== 'number') return null
    return {
      raw_prompt: String(p.p ?? ''),
      building_type: p.t === 'commercial' ? 'commercial' : 'residential',
      target_area_sqm: p.a,
      area_source: 'stated',
      stories: Math.min(3, Math.max(1, Math.round(p.s) || 1)),
      style: p.y === 'traditional' ? 'traditional' : 'open_plan',
      rooms: p.r.map(([type, count]) => ({ type, count: Math.max(0, Math.min(12, Math.round(count))) })),
      preferences: { daylight: !!(p.f & 1), privacy: !!(p.f & 2), compact: !!(p.f & 4) },
      notes: [],
    }
  } catch {
    return null
  }
}

export function briefFromHash(hash: string): Brief | null {
  const m = /[#&]b=([A-Za-z0-9_-]+)/.exec(hash)
  return m ? decodeBrief(m[1]) : null
}
