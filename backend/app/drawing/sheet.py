"""Plan -> display list.

A :class:`Sheet` is a list of layers holding simple primitives in plan
coordinates (metres, y pointing to the back of the plan). The SVG, PDF, PNG
and DXF writers all consume the same sheet, so every export looks alike.

Class names on primitives are a contract with the web client, which styles
and toggles layers with CSS (see ``frontend/src/styles/plan.css``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.geometry import Box, Segment, subtract_intervals
from app.drawing import units as fmt
from app.engine.validation import room_box
from app.engine.walls import EXTERIOR_WALL
from app.models.schemas import Candidate, Door, Fixture

Pt = tuple[float, float]


@dataclass
class Poly:
    points: list[Pt]
    cls: str
    attrs: dict[str, str] = field(default_factory=dict)
    rx: float = 0.0  # corner radius for rectangles (SVG only)


@dataclass
class Line:
    a: Pt
    b: Pt
    cls: str


@dataclass
class Arc:
    center: Pt
    radius: float
    start: float  # degrees, counter-clockwise from +x
    end: float
    cls: str


@dataclass
class Circle:
    center: Pt
    r: float
    cls: str


@dataclass
class Ellipse:
    center: Pt
    rx: float
    ry: float
    cls: str


@dataclass
class Text:
    pos: Pt
    text: str
    size: float
    cls: str
    alt: str | None = None  # imperial variant, when it differs
    anchor: str = "middle"
    rotate: float = 0.0  # degrees, counter-clockwise


Prim = Poly | Line | Arc | Circle | Ellipse | Text


@dataclass
class Layer:
    name: str
    items: list[Prim] = field(default_factory=list)


@dataclass
class Sheet:
    title: str
    layers: list[Layer]
    bounds: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    plan_box: Box

    def layer(self, name: str) -> Layer:
        return next(lay for lay in self.layers if lay.name == name)


def _rect_pts(x: float, y: float, w: float, h: float) -> list[Pt]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _txt(units: str, metric: str, imperial: str) -> tuple[str, str | None]:
    if units == "metric":
        return metric, None
    if units == "imperial":
        return imperial, None
    return metric, imperial


# ------------------------------------------------------------- furniture ----


class _Frame:
    """Local frame for a fixture: u across the front, v from back to front."""

    def __init__(self, f: Fixture) -> None:
        xs = [p[0] for p in f.footprint]
        ys = [p[1] for p in f.footprint]
        self.x0, self.y0, self.x1, self.y1 = min(xs), min(ys), max(xs), max(ys)
        self.facing = f.facing
        if f.facing in ("n", "s"):
            self.W, self.D = self.x1 - self.x0, self.y1 - self.y0
        else:
            self.W, self.D = self.y1 - self.y0, self.x1 - self.x0

    def pt(self, u: float, v: float) -> Pt:
        if self.facing == "n":
            return (self.x0 + u, self.y0 + v)
        if self.facing == "s":
            return (self.x1 - u, self.y1 - v)
        if self.facing == "e":
            return (self.x0 + v, self.y1 - u)
        return (self.x1 - v, self.y0 + u)

    def rect(self, u: float, v: float, w: float, d: float, cls: str, rx: float = 0.0) -> Poly:
        pts = [self.pt(u, v), self.pt(u + w, v), self.pt(u + w, v + d), self.pt(u, v + d)]
        return Poly(pts, cls, rx=rx)

    def line(self, u0: float, v0: float, u1: float, v1: float, cls: str = "fx-line") -> Line:
        return Line(self.pt(u0, v0), self.pt(u1, v1), cls)

    def circle(self, u: float, v: float, r: float, cls: str = "fx-line") -> Circle:
        return Circle(self.pt(u, v), r, cls)

    def ellipse(self, u: float, v: float, ru: float, rv: float, cls: str = "fx-line") -> Ellipse:
        cx, cy = self.pt(u, v)
        if self.facing in ("n", "s"):
            return Ellipse((cx, cy), ru, rv, cls)
        return Ellipse((cx, cy), rv, ru, cls)


def _chairs_around(box: Box, seats: int, out: list[Prim]) -> None:
    long_x = box.w >= box.h
    length = box.w if long_x else box.h
    per_side = max(1, (seats - (2 if seats >= 6 else 0)) // 2)
    cs = 0.42
    for i in range(per_side):
        t = length * (i + 0.5) / per_side - cs / 2
        if long_x:
            out.append(Poly(_rect_pts(box.x + t, box.y - cs + 0.08, cs, cs), "fx", rx=0.06))
            out.append(Poly(_rect_pts(box.x + t, box.y + box.h - 0.08, cs, cs), "fx", rx=0.06))
        else:
            out.append(Poly(_rect_pts(box.x - cs + 0.08, box.y + t, cs, cs), "fx", rx=0.06))
            out.append(Poly(_rect_pts(box.x + box.w - 0.08, box.y + t, cs, cs), "fx", rx=0.06))
    if seats >= 6:
        if long_x:
            cy = box.y + box.h / 2 - cs / 2
            out.append(Poly(_rect_pts(box.x - cs + 0.08, cy, cs, cs), "fx", rx=0.06))
            out.append(Poly(_rect_pts(box.x + box.w - 0.08, cy, cs, cs), "fx", rx=0.06))
        else:
            cx = box.x + box.w / 2 - cs / 2
            out.append(Poly(_rect_pts(cx, box.y - cs + 0.08, cs, cs), "fx", rx=0.06))
            out.append(Poly(_rect_pts(cx, box.y + box.h - 0.08, cs, cs), "fx", rx=0.06))


def fixture_symbol(f: Fixture) -> list[Prim]:
    fr = _Frame(f)
    W, D = fr.W, fr.D
    box = Box(fr.x0, fr.y0, fr.x1 - fr.x0, fr.y1 - fr.y0)
    t = f.type
    out: list[Prim] = []
    if t.startswith("dining_table") or t == "meeting_table":
        seats = int(t.rsplit("_", 1)[1]) if t.startswith("dining_table") else max(4, int(max(box.w, box.h) / 0.7) * 2 + 2)
        _chairs_around(box, seats, out)
        out.append(Poly(_rect_pts(box.x, box.y, box.w, box.h), "fx", rx=0.05))
        return out
    if t == "car":
        out.append(Poly(_rect_pts(box.x, box.y, box.w, box.h), "fx", rx=0.35))
        long_x = box.w >= box.h
        for k in (0.3, 0.62):
            if long_x:
                x = box.x + box.w * k
                out.append(Line((x, box.y + 0.15), (x, box.y + box.h - 0.15), "fx-line"))
            else:
                y = box.y + box.h * k
                out.append(Line((box.x + 0.15, y), (box.x + box.w - 0.15, y), "fx-line"))
        return out

    out.append(
        fr.rect(
            0, 0, W, D, "fx-fill" if t in {"counter", "island", "vanity"} else "fx", rx=0.03 if t in {"coffee_table", "island"} else 0.0
        )
    )
    if t == "bed":
        if W >= 1.2:
            out.append(fr.rect(0.08, 0.08, W / 2 - 0.12, 0.36, "fx", rx=0.06))
            out.append(fr.rect(W / 2 + 0.04, 0.08, W / 2 - 0.12, 0.36, "fx", rx=0.06))
        else:
            out.append(fr.rect(0.1, 0.08, W - 0.2, 0.36, "fx", rx=0.06))
        out.append(fr.line(0, 0.62, W, 0.62))
        out.append(fr.line(W - 0.45, 0.62, W, 1.0))
    elif t in {"wardrobe", "closet"}:
        out.append(fr.line(0.05, D / 2, W - 0.05, D / 2, "fx-dash"))
        n = max(2, int(W / 0.3))
        for i in range(1, n):
            u = W * i / n
            out.append(fr.line(u - 0.06, D / 2 - 0.12, u + 0.06, D / 2 + 0.12))
    elif t == "nightstand":
        out.append(fr.circle(W / 2, D / 2, min(W, D) * 0.25))
    elif t in {"sofa", "armchair"}:
        arm = 0.18
        out.append(fr.rect(0, 0, W, 0.22, "fx"))
        out.append(fr.rect(0, 0.22, arm, D - 0.22, "fx"))
        out.append(fr.rect(W - arm, 0.22, arm, D - 0.22, "fx"))
        seats = 1 if t == "armchair" else (3 if W >= 2.0 else 2)
        seat_w = (W - 2 * arm) / seats
        for i in range(1, seats):
            out.append(fr.line(arm + seat_w * i, 0.22, arm + seat_w * i, D - 0.05))
    elif t == "tv_unit":
        out.append(fr.rect(W * 0.15, 0.06, W * 0.7, 0.05, "fx-fill"))
    elif t == "sink":
        out.append(fr.rect(0.08, 0.1, W - 0.16, D - 0.2, "fx", rx=0.05))
        out.append(fr.circle(W / 2, D / 2 + 0.02, 0.03))
        out.append(fr.circle(W / 2, 0.06, 0.025))
    elif t == "stove":
        for u in (0.18, W - 0.18):
            for v in (0.17, D - 0.17):
                out.append(fr.circle(u, v, 0.09))
    elif t == "fridge":
        out.append(fr.line(0, D - 0.06, W, D - 0.06))
        out.append(fr.line(0, 0, W, D - 0.06))
    elif t == "bathtub":
        out.append(fr.rect(0.07, 0.07, W - 0.14, D - 0.14, "fx", rx=0.2))
        out.append(fr.circle(0.25, D / 2, 0.03))
    elif t == "shower":
        out.append(fr.line(0, 0, W, D, "fx-thin"))
        out.append(fr.line(W, 0, 0, D, "fx-thin"))
        out.append(fr.circle(W / 2, D / 2, 0.035))
    elif t == "toilet":
        out.append(fr.rect(0.02, 0.0, W - 0.04, 0.19, "fx"))
        out.append(fr.ellipse(W / 2, 0.19 + (D - 0.21) / 2, W / 2 - 0.03, (D - 0.21) / 2))
    elif t == "vanity":
        out.append(fr.ellipse(W / 2, D * 0.52, min(0.22, W * 0.32), D * 0.28))
    elif t in {"washer", "dryer"}:
        out.append(fr.circle(W / 2, D / 2 + 0.03, min(W, D) * 0.32))
    elif t == "utility_sink":
        out.append(fr.rect(0.06, 0.08, W - 0.12, D - 0.14, "fx", rx=0.04))
    elif t == "desk":
        out.append(fr.rect(W / 2 - 0.23, D + 0.1, 0.46, 0.44, "fx", rx=0.1))
    elif t in {"bookshelf", "shelving"}:
        n = max(1, int(W / 0.45))
        for i in range(1, n):
            out.append(fr.line(W * i / n, 0, W * i / n, D, "fx-thin"))
    elif t == "reception_desk":
        out.append(fr.rect(0.1, 0.0, W - 0.2, 0.25, "fx-fill"))
        out.append(fr.rect(W / 2 - 0.23, -0.55, 0.46, 0.44, "fx", rx=0.1))
    elif t == "rack":
        for i in range(1, 6):
            out.append(fr.line(0.05, D * i / 6, W - 0.05, D * i / 6, "fx-thin"))
    return out


# ------------------------------------------------------------- the plan ----


def _seg(points: list[list[float]]) -> Segment:
    (x0, y0), (x1, y1) = points
    return Segment(x0, y0, x1, y1)


def _door_prims(d: Door) -> list[Prim]:
    seg = _seg(d.segment)
    out: list[Prim] = []
    if d.kind == "opening":
        a, b = seg.point(seg.lo), seg.point(seg.hi)
        out.append(Line(a, b, "boundary"))
        return out
    if d.kind == "garage":
        a, b = seg.point(seg.lo), seg.point(seg.hi)
        out.append(Line(a, b, "door-garage"))
        return out
    hx, hy = d.hinge or d.segment[0]
    sx, sy = d.swing or d.segment[1]
    lx, ly = d.segment[1] if d.segment[0] == d.hinge else d.segment[0]
    out.append(Line((hx, hy), (sx, sy), "door-leaf"))
    a_open = math.degrees(math.atan2(sy - hy, sx - hx))
    a_closed = math.degrees(math.atan2(ly - hy, lx - hx))
    start, end = sorted((a_open, a_closed))
    if end - start > 180:
        start, end = end, start + 360
    out.append(Arc((hx, hy), d.width, start, end, "door-swing"))
    return out


def _window_prims(seg: Segment, t: float) -> list[Prim]:
    half = t / 2
    if seg.horizontal:
        y = seg.offset
        return [
            Poly(_rect_pts(seg.lo, y - half, seg.hi - seg.lo, t), "window"),
            Line((seg.lo, y), (seg.hi, y), "window-glass"),
        ]
    x = seg.offset
    return [
        Poly(_rect_pts(x - half, seg.lo, t, seg.hi - seg.lo), "window"),
        Line((x, seg.lo), (x, seg.hi), "window-glass"),
    ]


def _stair_prims(box: Box, label: str) -> list[Prim]:
    out: list[Prim] = []
    along_y = box.h >= box.w
    length = box.h if along_y else box.w
    landing = min(1.0, length * 0.25)
    run = length - landing
    n = max(3, int(run / 0.27))
    for i in range(n + 1):
        t = landing + run * i / n
        if along_y:
            out.append(Line((box.x, box.y + t), (box.x + box.w, box.y + t), "stair"))
        else:
            out.append(Line((box.x + t, box.y), (box.x + t, box.y + box.h), "stair"))
    if along_y:
        cx = box.x + box.w / 2
        a, b = (cx, box.y + landing * 0.6), (cx, box.y + box.h - 0.25)
        tip = [(cx, b[1] + 0.12), (cx - 0.12, b[1] - 0.1), (cx + 0.12, b[1] - 0.1)]
    else:
        cy = box.y + box.h / 2
        a, b = (box.x + landing * 0.6, cy), (box.x + box.w - 0.25, cy)
        tip = [(b[0] + 0.12, cy), (b[0] - 0.1, cy - 0.12), (b[0] - 0.1, cy + 0.12)]
    out.append(Line(a, b, "stair-arrow"))
    out.append(Poly(tip, "stair-head"))
    out.append(Text((a[0], a[1] - 0.25) if along_y else (a[0] - 0.05, a[1] + 0.3), label, 0.18, "label-note"))
    return out


def _label_anchor(room: Box, bw: float, bh: float, vertical: bool, obstacles: list[Box]) -> Pt:
    """Centre for a label block that overlaps the least furniture."""
    if vertical:
        bw, bh = bh, bw
    best = (math.inf, room.cx, room.cy)
    for fx in (0.5, 0.38, 0.62, 0.26, 0.74):
        for fy in (0.5, 0.38, 0.62, 0.26, 0.74, 0.16, 0.84):
            cx = room.x + room.w * fx
            cy = room.y + room.h * fy
            block = Box(cx - bw / 2, cy - bh / 2, bw, bh)
            if not room.inset(0.12, 0.12, 0.12, 0.12).contains(block, tol=0.05):
                continue
            overlap = 0.0
            for o in obstacles:
                ox = max(0.0, min(block.x + block.w, o.x + o.w) - max(block.x, o.x))
                oy = max(0.0, min(block.y + block.h, o.y + o.h) - max(block.y, o.y))
                overlap += ox * oy
            cost = overlap * 10 + abs(fx - 0.5) + abs(fy - 0.5)
            if cost < best[0]:
                best = (cost, cx, cy)
    return best[1], best[2]


def _label_size(text: str, avail: float, base: float, char_w: float = 0.56) -> float:
    return max(0.11, min(base, avail * 0.88 / max(1, len(text) * char_w)))


def build_sheet(c: Candidate, level: int, units: str = "both", annotate: bool = True, title: str | None = None) -> Sheet:
    rooms = [r for r in c.rooms if r.floor == level]
    W, D = c.footprint.width_m, c.footprint.depth_m
    zones = Layer("zones")
    furniture = Layer("furniture")
    walls = Layer("walls")
    openings = Layer("openings")
    labels = Layer("labels")
    dims = Layer("dims")
    annot = Layer("annot")

    for r in rooms:
        b = room_box(r)
        zones.items.append(
            Poly(_rect_pts(b.x, b.y, b.w, b.h), f"room zone-{r.zone}", {"data-room": r.id, "data-zone": r.zone, "data-type": r.type})
        )

    for f in c.fixtures:
        if f.floor == level:
            furniture.items.extend(fixture_symbol(f))

    top = max(r.floor for r in c.rooms)
    for r in rooms:
        if r.type == "stair":
            furniture.items.extend(_stair_prims(room_box(r), "DN" if level == top and top > 1 else "UP"))

    # Walls, with door and window openings cut out.
    cuts: dict[tuple, list[tuple[float, float]]] = {}
    level_doors = [d for d in c.doors if d.floor == level]
    level_windows = [w for w in c.windows if w.floor == level]
    for item in [*level_doors, *level_windows]:
        s = _seg(item.segment)
        cuts.setdefault((s.horizontal, round(s.offset, 3)), []).append((s.lo, s.hi))
    for wall in (w for w in c.walls if w.floor == level):
        s = _seg(wall.segment)
        t = wall.thickness
        holes = [h for h in cuts.get((s.horizontal, round(s.offset, 3)), []) if h[0] < s.hi and h[1] > s.lo]
        for lo, hi in subtract_intervals((s.lo, s.hi), holes, min_len=0.01):
            ext_lo = EXTERIOR_WALL / 2 if abs(lo - s.lo) < 1e-6 else 0.0
            ext_hi = EXTERIOR_WALL / 2 if abs(hi - s.hi) < 1e-6 else 0.0
            if s.horizontal:
                pts = _rect_pts(lo - ext_lo, s.offset - t / 2, hi - lo + ext_lo + ext_hi, t)
            else:
                pts = _rect_pts(s.offset - t / 2, lo - ext_lo, t, hi - lo + ext_lo + ext_hi)
            walls.items.append(Poly(pts, "wall wall-ext" if wall.exterior else "wall"))

    wall_t = {(round(_seg(w.segment).offset, 3), _seg(w.segment).horizontal): w.thickness for w in c.walls if w.floor == level}
    for d in level_doors:
        openings.items.extend(_door_prims(d))
    for w in level_windows:
        s = _seg(w.segment)
        openings.items.extend(_window_prims(s, wall_t.get((round(s.offset, 3), s.horizontal), EXTERIOR_WALL)))

    # Room labels, nudged off the furniture where the room allows it.
    furniture_boxes: dict[str, list[Box]] = {}
    for f in c.fixtures:
        if f.floor == level:
            xs = [p[0] for p in f.footprint]
            ys = [p[1] for p in f.footprint]
            furniture_boxes.setdefault(f.room_id, []).append(Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    for r in rooms:
        b = room_box(r)
        vertical = b.w < 1.6 and b.h > b.w * 1.8
        avail = b.h if vertical else b.w
        name = r.name.upper()
        size = _label_size(name, avail, 0.24, char_w=0.72)  # bold capitals with tracking
        small = min(size * 0.82, 0.2)
        area_m, area_i = fmt.area(r.area_sqm, "metric"), fmt.area(r.area_sqm, "imperial")
        dim_m, dim_i = fmt.dims(r.width_m, r.depth_m, "metric"), fmt.dims(r.width_m, r.depth_m, "imperial")
        rot = 90.0 if vertical else 0.0
        show_dims = b.short >= 2.1 and b.area >= 6 and r.type not in {"corridor", "stair"}
        lines = [(name, None, size, "label-name")]
        if r.type not in {"stair"} and b.area >= 2.5:
            m, i = _txt(units, area_m, area_i)
            lines.append((m, i, small, "label-area"))
        if show_dims:
            m, i = _txt(units, dim_m, dim_i)
            lines.append((m, i, small * 0.9, "label-dim"))
        block_w = max(len(t) * sz * (0.72 if cls == "label-name" else 0.6) for t, _, sz, cls in lines)
        block_h = sum(sz * 1.25 for _, _, sz, _ in lines)
        cx, cy = _label_anchor(b, block_w, block_h, vertical, furniture_boxes.get(r.id, []))
        acc = 0.0
        half = block_h / 2
        for text, alt, sz, cls in lines:
            offset = half - acc - sz * 0.95
            acc += sz * 1.25
            pos = (cx - offset, cy) if vertical else (cx, cy + offset)
            labels.items.append(Text(pos, text, sz, cls, alt=alt, rotate=rot))

    if annotate:
        _dimensions(dims, rooms, W, D, units)
        _annotations(annot, W, D, level, c.floors, units, title)

    pad_l, pad_b, pad_r, pad_t = 2.0, 2.3, 0.9, 1.2
    return Sheet(
        title=title or (f"Level {level}" if c.floors > 1 else "Plan"),
        layers=[zones, furniture, walls, openings, labels, dims, annot],
        bounds=(-pad_l, -pad_b, W + pad_r, D + pad_t),
        plan_box=Box(0, 0, W, D),
    )


def _dim_chain(layer: Layer, stops: list[float], horizontal: bool, offset: float, units: str, cls: str = "dim") -> None:
    tick = 0.12
    for a, b in zip(stops, stops[1:]):
        if b - a < 0.05:
            continue
        m, i = _txt(units, fmt.length(b - a, "metric"), fmt.length(b - a, "imperial"))
        if horizontal:
            layer.items.append(Line((a, offset), (b, offset), cls))
            layer.items.append(Text(((a + b) / 2, offset + 0.12), m, 0.2, "dim-text", alt=i))
        else:
            layer.items.append(Line((offset, a), (offset, b), cls))
            layer.items.append(Text((offset - 0.12, (a + b) / 2), m, 0.2, "dim-text", alt=i, rotate=90))
    for s in stops:
        if horizontal:
            layer.items.append(Line((s - tick, offset - tick), (s + tick, offset + tick), "dim-tick"))
            layer.items.append(Line((s, offset - 0.2), (s, offset + 0.2), "dim-ext"))
        else:
            layer.items.append(Line((offset - tick, s - tick), (offset + tick, s + tick), "dim-tick"))
            layer.items.append(Line((offset - 0.2, s), (offset + 0.2, s), "dim-ext"))


def _dimensions(layer: Layer, rooms, W: float, D: float, units: str) -> None:
    xs = sorted({0.0, W} | {room_box(r).x for r in rooms if room_box(r).y < 1e-4} | {room_box(r).x1 for r in rooms if room_box(r).y < 1e-4})
    ys = sorted({0.0, D} | {room_box(r).y for r in rooms if room_box(r).x < 1e-4} | {room_box(r).y1 for r in rooms if room_box(r).x < 1e-4})
    _dim_chain(layer, xs, True, -0.75, units)
    _dim_chain(layer, [0.0, W], True, -1.45, units, "dim dim-total")
    _dim_chain(layer, ys, False, -0.75, units)
    _dim_chain(layer, [0.0, D], False, -1.45, units, "dim dim-total")


def _annotations(layer: Layer, W: float, D: float, level: int, floors: int, units: str, title: str | None) -> None:
    # North arrow (plans are drawn with the entry facade to the south).
    cx, cy, r = W + 0.45, D + 0.55, 0.32
    layer.items.append(Circle((cx, cy), r, "annot-line"))
    layer.items.append(
        Poly([(cx, cy + r * 0.85), (cx - r * 0.45, cy - r * 0.6), (cx, cy - r * 0.3), (cx + r * 0.45, cy - r * 0.6)], "annot-fill")
    )
    layer.items.append(Text((cx, cy - r - 0.25), "N", 0.2, "annot-text"))
    # Level title.
    heading = title or (f"LEVEL {level}" if floors > 1 else "FLOOR PLAN")
    layer.items.append(Text((0.0, D + 0.45), heading.upper(), 0.3, "annot-title", anchor="start"))
    # Scale bar; the web view carries both and shows one via CSS.
    bars = [("metric", " u-m"), ("imperial", " u-i")] if units == "both" else [(units, "")]
    y = -2.05
    for system, extra in bars:
        if system == "imperial":
            step, n, label = 1.524, 4, ["0", "5", "10", "15", "20 ft"]
        else:
            step, n, label = 1.0, 5, ["0", "1", "2", "3", "4", "5 m"]
        for i in range(n):
            layer.items.append(Poly(_rect_pts(i * step, y, step, 0.1), ("annot-fill" if i % 2 == 0 else "annot-line") + extra))
        for i, text in enumerate(label):
            layer.items.append(Text((i * step, y + 0.2), text, 0.15, "annot-text" + extra))
