"""Access planning: decide which rooms connect and where doors go.

Starting from the front door (or the stair landing on upper levels) the
planner grows a spanning tree over rooms that share a wall, always taking the
cheapest allowed connection next. Costs encode architectural preferences: a
bedroom should open off the hall, not the kitchen; an ensuite only opens off
its bedroom. Rooms that cannot be reached are reported so the candidate can
be rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.geometry import Box, Segment, r3, shared_edge, side_of, side_segment
from app.engine.layout import Layout, PlacedRoom
from app.engine.rooms import SPECS
from app.models.schemas import Connection, Door

OPEN_CLUSTER = {"living", "dining", "kitchen", "studio"}
CIRCULATION = {"corridor", "stair", "entry"}
LATCH_CLEARANCE = 0.3
CORNER_OFFSET = 0.1

# cost[server][target]; a missing entry means the connection is not allowed.
_ANY = {
    "bedroom": 1.0,
    "bathroom": 1.0,
    "ensuite": None,
    "powder": 1.0,
    "study": 1.0,
    "laundry": 1.0,
    "storage": 1.0,
    "living": 1.0,
    "dining": 1.2,
    "kitchen": 1.3,
    "stair": 1.0,
    "entry": 1.0,
    "private_office": 1.0,
    "meeting_room": 1.0,
    "open_office": 1.0,
    "break_room": 1.0,
    "server_room": 1.0,
    "reception": 1.0,
    "garage": 1.5,
    "studio": 1.0,
    "corridor": 1.0,
}
COSTS: dict[str, dict[str, float | None]] = {
    "corridor": _ANY,
    "entry": {
        "living": 1.0,
        "studio": 1.0,
        "reception": 1.0,
        "corridor": 1.0,
        "stair": 1.0,
        "dining": 1.6,
        "kitchen": 1.8,
        "powder": 1.5,
        "bathroom": 2.5,
        "storage": 1.5,
        "study": 2.0,
        "garage": 1.5,
        "bedroom": 4.0,
        "open_office": 1.5,
        "laundry": 2.5,
    },
    "living": {
        "dining": 1.0,
        "kitchen": 1.2,
        "corridor": 1.0,
        "stair": 1.2,
        "entry": 1.0,
        "study": 2.5,
        "powder": 3.0,
        "bedroom": 6.0,
        "bathroom": 8.0,
        "storage": 4.0,
    },
    "studio": {"kitchen": 1.0, "entry": 1.0, "bathroom": 2.5, "storage": 2.0, "corridor": 1.0, "powder": 2.5},
    "dining": {
        "kitchen": 1.0,
        "living": 1.0,
        "corridor": 1.5,
        "stair": 2.0,
        "study": 3.0,
        "powder": 4.0,
        "laundry": 4.0,
        "storage": 3.0,
        "bedroom": 9.0,
    },
    "kitchen": {"dining": 1.0, "living": 1.2, "laundry": 1.5, "storage": 1.5, "garage": 2.0, "corridor": 1.5, "entry": 1.8, "studio": 1.0},
    "stair": {
        "corridor": 1.0,
        "entry": 1.0,
        "living": 1.5,
        "dining": 2.0,
        "kitchen": 3.0,
        "bedroom": 5.0,
        "bathroom": 6.0,
        "study": 3.0,
        "reception": 1.5,
        "open_office": 2.0,
    },
    "reception": {
        "corridor": 1.0,
        "open_office": 1.5,
        "meeting_room": 1.5,
        "private_office": 4.0,
        "bathroom": 3.0,
        "break_room": 3.0,
        "storage": 3.0,
        "stair": 1.5,
    },
    "open_office": {
        "corridor": 1.0,
        "meeting_room": 1.5,
        "private_office": 2.5,
        "break_room": 1.5,
        "server_room": 2.5,
        "storage": 2.0,
        "bathroom": 3.0,
        "reception": 1.5,
    },
    "garage": {"laundry": 1.5, "storage": 1.5, "kitchen": 2.0, "entry": 1.5, "corridor": 1.5},
    "bedroom": {"ensuite": 0.5},
}


def link_cost(server: PlacedRoom, target: PlacedRoom) -> float | None:
    cost = COSTS.get(server.room.type, {}).get(target.room.type)
    if cost is None:
        return None
    if target.room.type == "ensuite":
        return 0.5 if server.room.primary else 2.0
    return cost


def connection_kind(a: PlacedRoom, b: PlacedRoom, style: str) -> str:
    types = {a.room.type, b.room.type}
    if types & {"stair"}:
        return "opening"
    if types <= OPEN_CLUSTER | {"entry"}:
        if style == "traditional" and "kitchen" in types and len(types) > 1:
            return "door"
        return "opening"
    if types <= {"corridor", "entry", "living", "dining", "reception", "open_office", "studio"}:
        return "opening"
    return "door"


def _door_width(target: PlacedRoom, commercial: bool) -> float:
    w = SPECS[target.room.type].door_width
    return max(w, 0.9) if commercial else w


def _opening_width(a: PlacedRoom, b: PlacedRoom, shared: float, style: str) -> float:
    types = {a.room.type, b.room.type}
    if types <= OPEN_CLUSTER and style == "open_plan":
        return r3(max(1.0, min(shared - 0.3, max(1.2, shared * 0.8))))
    if "stair" in types:
        return r3(min(shared - 0.2, 1.1))
    return r3(min(shared - 0.3, 1.2 if types & {"living", "dining", "reception", "open_office"} else 1.0))


def _need(a: PlacedRoom, b: PlacedRoom, style: str, commercial: bool) -> float:
    if connection_kind(a, b, style) == "opening":
        return 1.0
    return _door_width(b, commercial) + LATCH_CLEARANCE


@dataclass
class AccessPlan:
    doors: list[Door] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)
    entry_missing: bool = False
    depth: dict[str, int] = field(default_factory=dict)  # tree depth from the entry
    parents: dict[str, str] = field(default_factory=dict)


class _Spans:
    """Door spans already used on each wall line, to keep doors apart."""

    def __init__(self) -> None:
        self.lines: dict[tuple, list[tuple[float, float]]] = {}

    def key(self, seg: Segment) -> tuple:
        return (seg.horizontal, round(seg.offset, 3))

    def free(self, seg: Segment, lo: float, hi: float) -> bool:
        return all(hi <= a - 0.1 or lo >= b + 0.1 for a, b in self.lines.get(self.key(seg), []))

    def add(self, seg: Segment, lo: float, hi: float) -> None:
        self.lines.setdefault(self.key(seg), []).append((lo, hi))


def _exterior_sides(box: Box, width: float, depth: float) -> list[str]:
    sides = []
    if abs(box.y) < 1e-4:
        sides.append("s")
    if abs(box.x1 - width) < 1e-4:
        sides.append("e")
    if abs(box.y1 - depth) < 1e-4:
        sides.append("n")
    if abs(box.x) < 1e-4:
        sides.append("w")
    return sides


def exterior_sides(p: PlacedRoom, layout: Layout) -> list[str]:
    return _exterior_sides(p.box, layout.width, layout.depth)


def _swing_door(
    did: str,
    kind: str,
    level: int,
    server: str,
    target: PlacedRoom,
    seg: Segment,
    width: float,
    spans: _Spans,
    toward: tuple[float, float] | None,
) -> Door | None:
    lo, hi = seg.lo, seg.hi
    if hi - lo < width + 0.05:
        return None
    tb = target.box
    corner_lo = abs(lo - (tb.x if seg.horizontal else tb.y)) < 1e-4
    corner_hi = abs(hi - (tb.x1 if seg.horizontal else tb.y1)) < 1e-4
    off = min(CORNER_OFFSET, (hi - lo - width) / 2)
    options = []
    for end in ("lo", "hi"):
        if end == "lo":
            a, b = lo + off, lo + off + width
        else:
            a, b = hi - off - width, hi - off
        pref = 0.0
        if (end == "lo" and corner_lo) or (end == "hi" and corner_hi):
            pref -= 1.0
        if toward is not None:
            px, py = seg.point((a + b) / 2)
            pref += 0.05 * (abs(px - toward[0]) + abs(py - toward[1]))
        options.append((pref, end, a, b))
    mid = (lo + hi) / 2
    options.append((5.0, "mid", mid - width / 2, mid + width / 2))
    options.sort(key=lambda t: t[0])
    for _, end, a, b in options:
        if not spans.free(seg, a, b):
            continue
        spans.add(seg, a, b)
        hinge_t = a if end != "hi" else b
        latch_t = b if end != "hi" else a
        hx, hy = seg.point(hinge_t)
        side = side_of(tb, seg)
        nx, ny = {"s": (0, 1), "n": (0, -1), "w": (1, 0), "e": (-1, 0)}[side]
        lx, ly = seg.point(latch_t)
        return Door(
            id=did,
            kind=kind,  # type: ignore[arg-type]
            floor=level,
            room_a=server,
            room_b=target.room.id,
            segment=[[r3(hx), r3(hy)], [r3(lx), r3(ly)]],
            width=r3(width),
            hinge=[r3(hx), r3(hy)],
            swing=[r3(hx + nx * width), r3(hy + ny * width)],
        )
    return None


def _opening(did: str, level: int, a: PlacedRoom, b: PlacedRoom, seg: Segment, width: float, spans: _Spans) -> Door | None:
    lo, hi = seg.lo, seg.hi
    width = min(width, hi - lo - 0.1)
    if width < 0.8:
        return None
    mid = (lo + hi) / 2
    for center in (mid, lo + 0.15 + width / 2, hi - 0.15 - width / 2):
        s, e = center - width / 2, center + width / 2
        if s < lo - 1e-6 or e > hi + 1e-6 or not spans.free(seg, s, e):
            continue
        spans.add(seg, s, e)
        p0, p1 = seg.point(s), seg.point(e)
        return Door(
            id=did,
            kind="opening",
            floor=level,
            room_a=a.room.id,
            room_b=b.room.id,
            segment=[[r3(p0[0]), r3(p0[1])], [r3(p1[0]), r3(p1[1])]],
            width=r3(width),
        )
    return None


def _root(rooms: list[PlacedRoom], level: int, base_level: int) -> PlacedRoom | None:
    order = ["entry", "reception", "studio", "living", "open_office"] if level == base_level else ["stair"]
    for t in order:
        for p in rooms:
            if p.room.type == t:
                return p
    return rooms[0] if rooms else None


def plan_access(layout: Layout, style: str, commercial: bool) -> AccessPlan:
    plan = AccessPlan()
    levels = sorted({p.room.floor for p in layout.rooms})
    counter = 0

    def next_id(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}_{counter}"

    stairs: list[PlacedRoom] = []
    for level in levels:
        rooms = layout.floor(level)
        spans = _Spans()
        root = _root(rooms, level, levels[0])
        if root is None:
            continue
        toward = (root.box.cx, root.box.cy)

        if level == levels[0]:
            ext = exterior_sides(root, layout)
            ext.sort(key=lambda s: {"s": 0, "w": 1, "e": 1, "n": 2}[s])
            door = None
            for s in ext:
                seg = side_segment(root.box, s)
                width = 1.0 if commercial else 0.9
                if seg.length < width + 0.4:
                    continue
                mid = (seg.lo + seg.hi) / 2
                sub = seg.sub(mid - width / 2 - CORNER_OFFSET, mid + width / 2 + CORNER_OFFSET)
                door = _swing_door("door_entry", "entry", level, "exterior", root, sub, width, spans, None)
                if door:
                    toward = (door.segment[0][0], door.segment[0][1])
                    break
            if door is None:
                plan.entry_missing = True
            else:
                plan.doors.append(door)
            for g in (p for p in rooms if p.room.type == "garage"):
                gext = [s for s in exterior_sides(g, layout) if s == "s"] or exterior_sides(g, layout)
                if gext:
                    seg = side_segment(g.box, gext[0])
                    cars = 2 if "2" in g.room.name else 3 if "3" in g.room.name else 1
                    gw = min(seg.length - 0.6, 2.5 * cars + 0.4 * (cars - 1))
                    mid = (seg.lo + seg.hi) / 2
                    a, b = seg.point(mid - gw / 2), seg.point(mid + gw / 2)
                    spans.add(seg, mid - gw / 2, mid + gw / 2)
                    plan.doors.append(
                        Door(
                            id=f"door_garage_{g.room.id}",
                            kind="garage",
                            floor=level,
                            room_a="exterior",
                            room_b=g.room.id,
                            segment=[[r3(a[0]), r3(a[1])], [r3(b[0]), r3(b[1])]],
                            width=r3(gw),
                        )
                    )

        # Shared walls between rooms on this level.
        edges: dict[tuple[str, str], Segment] = {}
        for i, a in enumerate(rooms):
            for b in rooms[i + 1 :]:
                seg = shared_edge(a.box, b.box)
                if seg is not None and seg.length >= 0.8:
                    edges[(a.room.id, b.room.id)] = seg
                    edges[(b.room.id, a.room.id)] = seg

        by_id = {p.room.id: p for p in rooms}
        visited = {root.room.id}
        plan.depth[root.room.id] = 0
        tree: list[tuple[PlacedRoom, PlacedRoom, Segment]] = []
        while len(visited) < len(rooms):
            best = None
            for sid in visited:
                s = by_id[sid]
                for t in rooms:
                    if t.room.id in visited:
                        continue
                    seg = edges.get((sid, t.room.id))
                    if seg is None:
                        continue
                    cost = link_cost(s, t)
                    if cost is None or seg.length < _need(s, t, style, commercial):
                        continue
                    cost += 0.1 * plan.depth[sid]
                    if best is None or cost < best[0]:
                        best = (cost, s, t, seg)
            if best is None:
                break
            _, s, t, seg = best
            visited.add(t.room.id)
            plan.depth[t.room.id] = plan.depth[s.room.id] + 1
            plan.parents[t.room.id] = s.room.id
            tree.append((s, t, seg))

        for p in rooms:
            if p.room.id not in visited:
                plan.unreachable.append(p.room.id)

        # Openings first (they are wide and centred), then swing doors.
        # Open-plan rooms that touch are joined even when the tree does not need it.
        links = list(tree)
        linked = {frozenset((s.room.id, t.room.id)) for s, t, _ in tree}
        for i, a in enumerate(rooms):
            for b in rooms[i + 1 :]:
                pair = frozenset((a.room.id, b.room.id))
                if pair in linked or (a.room.id, b.room.id) not in edges:
                    continue
                types = {a.room.type, b.room.type}
                allowed = types <= OPEN_CLUSTER if style == "open_plan" else types == {"living", "dining"}
                if allowed and edges[(a.room.id, b.room.id)].length >= 1.4:
                    links.append((a, b, edges[(a.room.id, b.room.id)]))

        links.sort(key=lambda link: 0 if connection_kind(link[0], link[1], style) == "opening" else 1)
        for s, t, seg in links:
            kind = connection_kind(s, t, style)
            if kind == "opening":
                door = _opening(next_id("opening"), level, s, t, seg, _opening_width(s, t, seg.length, style), spans)
            else:
                door = _swing_door(next_id("door"), "door", level, s.room.id, t, seg, _door_width(t, commercial), spans, toward)
            if door is None:
                if t.room.id in visited and (s, t, seg) in tree:
                    plan.unreachable.append(t.room.id)
                continue
            plan.doors.append(door)
            plan.connections.append(
                Connection(
                    from_room=s.room.id,
                    to_room=t.room.id,
                    kind=kind,  # type: ignore[arg-type]
                    length_m=r3(abs(s.box.cx - t.box.cx) + abs(s.box.cy - t.box.cy)),
                )
            )
        stairs.extend(p for p in rooms if p.room.type == "stair")

    stairs.sort(key=lambda p: p.room.floor)
    for a, b in zip(stairs, stairs[1:]):
        plan.connections.append(Connection(from_room=a.room.id, to_room=b.room.id, kind="stair", length_m=3.0))
    return plan
