/*
  Zone fills for every plan on the page. Each zone is a tint plus a hatch on
  the engine's 300 mm planning grid, so zones stay distinguishable without
  relying on colour alone. Patterns live in one hidden SVG and are referenced
  by id from plan.css; inline SVGs share the document's id space.
  Units are plan metres (the plans' user space).
*/
export function PlanPatterns() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        <pattern id="zp-public" width="0.3" height="0.3" patternUnits="userSpaceOnUse">
          <rect width="0.3" height="0.3" style={{ fill: 'var(--zone-public)' }} />
          <circle cx="0.15" cy="0.15" r="0.018" style={{ fill: 'var(--hatch)' }} />
        </pattern>
        <pattern id="zp-private" width="0.3" height="0.3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="0.3" height="0.3" style={{ fill: 'var(--zone-private)' }} />
          <path d="M0 0.15H0.3" style={{ stroke: 'var(--hatch)', strokeWidth: 0.016 }} />
        </pattern>
        <pattern id="zp-service" width="0.3" height="0.3" patternUnits="userSpaceOnUse">
          <rect width="0.3" height="0.3" style={{ fill: 'var(--zone-service)' }} />
          <path d="M0 0.15H0.3M0.15 0V0.3" style={{ stroke: 'var(--hatch)', strokeWidth: 0.012 }} />
        </pattern>
      </defs>
    </svg>
  )
}
