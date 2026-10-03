/*
  Axonometric cut-away of a small plan, drawn in code so it follows the
  theme tokens. Used for the empty, loading and error states. In the
  loading state the walls rise one after another, like a model being built.
*/

type Rect = { x: number; y: number; w: number; h: number; zone: 'public' | 'private' | 'service' | 'circulation'; mark?: boolean }

const ROOMS: Rect[] = [
  { x: 0, y: 0, w: 6, h: 4, zone: 'public' },
  { x: 6, y: 0, w: 4, h: 4, zone: 'public' },
  { x: 0, y: 4, w: 10, h: 1.2, zone: 'circulation' },
  { x: 0, y: 5.2, w: 3.8, h: 3.4, zone: 'private' },
  { x: 3.8, y: 5.2, w: 2.2, h: 3.4, zone: 'service' },
  { x: 6, y: 5.2, w: 4, h: 3.4, zone: 'private', mark: true },
]

const W = 10
const D = 8.6
const H = 1.5 // cut height of the walls
const T = 0.2 // wall thickness
const COS = Math.cos(Math.PI / 6)
const SIN = Math.sin(Math.PI / 6)

function P(x: number, y: number, z: number): string {
  const px = (x - y) * COS
  const py = (x + y) * SIN - z
  return `${px.toFixed(3)},${py.toFixed(3)}`
}

type Wall = { x0: number; y0: number; x1: number; y1: number }

function walls(): Wall[] {
  const out: Wall[] = []
  const seen = new Set<string>()
  const add = (x0: number, y0: number, x1: number, y1: number) => {
    const key = [x0, y0, x1, y1].map((v) => v.toFixed(2)).join()
    if (!seen.has(key)) {
      seen.add(key)
      out.push({ x0, y0, x1, y1 })
    }
  }
  add(0, 0, W, 0)
  add(0, D, W, D)
  add(0, 0, 0, D)
  add(W, 0, W, D)
  add(6, 0, 6, 4)
  add(0, 4, 2.4, 4)
  add(3.4, 4, W, 4)
  add(0, 5.2, 1.2, 5.2)
  add(2.2, 5.2, 4.6, 5.2)
  add(5.4, 5.2, 7, 5.2)
  add(8, 5.2, W, 5.2)
  add(3.8, 5.2, 3.8, D)
  add(6, 5.2, 6, D)
  // Draw back to front so nearer walls overlap farther ones.
  return out.sort((a, b) => a.x0 + a.y0 + a.x1 + a.y1 - (b.x0 + b.y0 + b.x1 + b.y1))
}

/** Visible faces of a wall prism: the cut top and the +x and +y faces. */
function prism(w: Wall): { top: string; fx: string; fy: string } {
  const t = T / 2
  const horizontal = Math.abs(w.y1 - w.y0) < 1e-6
  const [xa, xb] = horizontal ? [Math.min(w.x0, w.x1) - t, Math.max(w.x0, w.x1) + t] : [w.x0 - t, w.x0 + t]
  const [ya, yb] = horizontal ? [w.y0 - t, w.y0 + t] : [Math.min(w.y0, w.y1) - t, Math.max(w.y0, w.y1) + t]
  return {
    top: [P(xa, ya, H), P(xb, ya, H), P(xb, yb, H), P(xa, yb, H)].join(' '),
    fx: [P(xb, ya, 0), P(xb, yb, 0), P(xb, yb, H), P(xb, ya, H)].join(' '),
    fy: [P(xa, yb, 0), P(xb, yb, 0), P(xb, yb, H), P(xa, yb, H)].join(' '),
  }
}

export function Axo({ state = 'idle', size = 260 }: { state?: 'idle' | 'loading' | 'error'; size?: number }) {
  const ws = walls()
  const minX = -D * COS - 0.6
  const maxX = W * COS + 0.6
  const minY = -H - 0.6
  const maxY = (W + D) * SIN + 0.6
  return (
    <svg
      className={`axo axo-${state}`}
      width={size}
      height={(size * (maxY - minY)) / (maxX - minX)}
      viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
      aria-hidden="true"
    >
      <g className="axo-floor">
        {ROOMS.map((r, i) => (
          <polygon
            key={i}
            className={`axo-room zone-${r.zone} ${r.mark ? 'is-mark' : ''}`}
            points={[P(r.x, r.y, 0), P(r.x + r.w, r.y, 0), P(r.x + r.w, r.y + r.h, 0), P(r.x, r.y + r.h, 0)].join(' ')}
          />
        ))}
        <polygon className="axo-outline" points={[P(0, 0, 0), P(W, 0, 0), P(W, D, 0), P(0, D, 0)].join(' ')} />
      </g>
      <g className="axo-walls">
        {ws.map((w, i) => {
          const f = prism(w)
          return (
            <g key={i} className="axo-wall" style={{ animationDelay: `${i * 90}ms` }}>
              <polygon className="axo-fy" points={f.fy} />
              <polygon className="axo-fx" points={f.fx} />
              <polygon className="axo-top" points={f.top} />
            </g>
          )
        })}
      </g>
      {state === 'error' && (
        <g className="axo-flag">
          <circle cx={(8 - 6.9) * COS} cy={(8 + 6.9) * SIN - 2.6} r="0.75" />
          <path d={`M${(8 - 6.9) * COS} ${(8 + 6.9) * SIN - 3} v0.5 M${(8 - 6.9) * COS} ${(8 + 6.9) * SIN - 2.2} v0.05`} />
        </g>
      )}
    </svg>
  )
}
