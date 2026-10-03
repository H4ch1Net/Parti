import { useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, type Ref } from 'react'

type Box = { x: number; y: number; w: number; h: number }

export type CanvasController = {
  zoomBy: (factor: number) => void
  fit: () => void
}

type Props = {
  svg: string
  selectedRoom: string | null
  hoverRoom: string | null
  flaggedRooms: string[]
  label: string
  onHoverRoom: (id: string | null) => void
  onSelectRoom: (id: string | null) => void
  controllerRef?: Ref<CanvasController>
}

function parseBox(value: string | null): Box | null {
  if (!value) return null
  const [x, y, w, h] = value.split(/[\s,]+/).map(Number)
  return [x, y, w, h].every(Number.isFinite) ? { x, y, w, h } : null
}

/** Grow a box to the container's aspect ratio around its centre. */
function toAspect(b: Box, cw: number, ch: number): Box {
  if (cw <= 0 || ch <= 0) return b
  const ratio = ch / cw
  if (b.h / b.w < ratio) {
    const h = b.w * ratio
    return { x: b.x, y: b.y - (h - b.h) / 2, w: b.w, h }
  }
  const w = b.h / ratio
  return { x: b.x - (w - b.w) / 2, y: b.y, w, h: b.h }
}

export function PlanCanvas({ svg, selectedRoom, hoverRoom, flaggedRooms, label, onHoverRoom, onSelectRoom, controllerRef }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const base = useRef<Box | null>(null)
  const view = useRef<Box | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const drag = useRef<{ x: number; y: number; moved: boolean; pinch: number | null; room: string | null } | null>(null)

  const svgEl = () => stageRef.current?.querySelector('svg') ?? null

  const apply = useCallback(() => {
    const el = svgEl()
    const v = view.current
    if (el && v) el.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`)
  }, [])

  const fit = useCallback(() => {
    const host = hostRef.current
    if (!host || !base.current) return
    const pad = 0.03
    const b = base.current
    const padded = { x: b.x - b.w * pad, y: b.y - b.h * pad, w: b.w * (1 + 2 * pad), h: b.h * (1 + 2 * pad) }
    view.current = toAspect(padded, host.clientWidth, host.clientHeight)
    apply()
  }, [apply])

  const zoomAt = useCallback(
    (factor: number, px?: number, py?: number) => {
      const host = hostRef.current
      const v = view.current
      const b = base.current
      if (!host || !v || !b) return
      const cw = host.clientWidth
      const ch = host.clientHeight
      const fx = px === undefined ? 0.5 : px / cw
      const fy = py === undefined ? 0.5 : py / ch
      const w = Math.min(b.w * 2, Math.max(b.w / 14, v.w / factor))
      const h = (w * ch) / cw
      const sx = v.x + fx * v.w
      const sy = v.y + fy * v.h
      view.current = { x: sx - fx * w, y: sy - fy * h, w, h }
      apply()
    },
    [apply],
  )

  useImperativeHandle(controllerRef, () => ({ zoomBy: (f: number) => zoomAt(f), fit }), [zoomAt, fit])

  // New drawing: read its natural box; refit only if the footprint changed.
  useLayoutEffect(() => {
    const el = svgEl()
    if (!el) return
    const nb = parseBox(el.getAttribute('viewBox'))
    const prev = base.current
    base.current = nb
    if (!prev || !nb || Math.abs(prev.w - nb.w) > 1e-3 || Math.abs(prev.h - nb.h) > 1e-3 || !view.current) fit()
    else apply()
  }, [svg, fit, apply])

  // Keep the scale when the container resizes.
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let last = { w: host.clientWidth, h: host.clientHeight }
    const ro = new ResizeObserver(() => {
      const v = view.current
      const cw = host.clientWidth
      const ch = host.clientHeight
      if (!v || cw === 0 || ch === 0) return
      if (last.w === 0 || last.h === 0) {
        fit()
      } else {
        const w = (v.w * cw) / last.w
        const h = (w * ch) / cw
        view.current = { x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w, h }
        apply()
      }
      last = { w: cw, h: ch }
    })
    ro.observe(host)
    return () => ro.disconnect()
  }, [fit, apply])

  // Wheel zoom needs a non-passive listener to stop page scroll.
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = host.getBoundingClientRect()
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
      zoomAt(Math.exp(-delta * 0.0018), e.clientX - r.left, e.clientY - r.top)
    }
    host.addEventListener('wheel', onWheel, { passive: false })
    return () => host.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  // Room highlight classes.
  useEffect(() => {
    const el = svgEl()
    if (!el) return
    el.querySelectorAll<SVGElement>('.room').forEach((node) => {
      const id = node.dataset.room ?? ''
      node.classList.toggle('is-selected', id === selectedRoom)
      node.classList.toggle('is-hover', id === hoverRoom && id !== selectedRoom)
      node.classList.toggle('is-flagged', flaggedRooms.includes(id) && id !== selectedRoom && id !== hoverRoom)
    })
  }, [svg, selectedRoom, hoverRoom, flaggedRooms])

  const roomAt = (target: EventTarget | null): string | null => {
    const node = (target as Element | null)?.closest?.('[data-room]') as SVGElement | null
    return node?.dataset.room ?? null
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    hostRef.current?.setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    // Pointer capture retargets later events to the host, so remember the room now.
    drag.current = { x: e.clientX, y: e.clientY, moved: false, pinch: null, room: roomAt(e.target) }
  }

  const onPointerMove = (e: React.PointerEvent) => {
    const host = hostRef.current
    const d = drag.current
    if (!d || !host) {
      onHoverRoom(roomAt(e.target))
      return
    }
    const prev = pointers.current.get(e.pointerId)
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (d.pinch) {
        const r = host.getBoundingClientRect()
        zoomAt(dist / d.pinch, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top)
      }
      d.pinch = dist
      d.moved = true
      return
    }
    if (!prev || !view.current) return
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 4) return
    d.moved = true
    const v = view.current
    const k = v.w / host.clientWidth
    view.current = { ...v, x: v.x - (e.clientX - prev.x) * k, y: v.y - (e.clientY - prev.y) * k }
    apply()
  }

  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current
    pointers.current.delete(e.pointerId)
    if (pointers.current.size > 0) return
    drag.current = null
    if (d && !d.moved) onSelectRoom(d.room)
  }

  return (
    <div
      ref={hostRef}
      className="canvas-host"
      role="img"
      aria-label={label}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={() => !drag.current && onHoverRoom(null)}
      onDoubleClick={fit}
    >
      <div ref={stageRef} className="canvas-stage" dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  )
}
