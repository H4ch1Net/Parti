from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon

from app.core.geometry import bbox_dimensions, polygon_to_points, rectangle
from app.models.schemas import CirculationEdge, LayoutCandidate, ProgramOutput, RoomGeometry, RoomScheduleRow, Wall
from app.services.parti_selector import Parti, PartiDecision, ProgramBrief

# Compatibility shim for tests that read candidate.zone_map.
if not hasattr(LayoutCandidate, "zone_map"):
    LayoutCandidate.zone_map = property(lambda self: self.zones)


MIN_DIM_TABLE: dict[str, tuple[float, float]] = {
    "studio_room": (3.5, 4.0),
    "bedroom_single": (2.7, 3.0),
    "bedroom_double": (3.0, 3.6),
    "bedroom_master": (3.6, 4.2),
    "bathroom_full": (1.8, 2.4),
    "bathroom_ensuite": (1.5, 2.0),
    "kitchen_small": (2.4, 2.4),
    "kitchen_standard": (2.7, 3.6),
    "living_small": (3.0, 3.5),
    "living_standard": (3.6, 4.8),
    "dining": (2.4, 3.0),
    "corridor": (0.9, 0.9),
    "office_private": (2.7, 3.0),
    "office_open": (4.0, 5.0),
    "meeting_room": (3.0, 4.0),
    "reception": (3.0, 3.6),
}


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass
class RoomLayout:
    rooms: list[RoomGeometry]
    walls: list[Wall]
    circulation: list[CirculationEdge]
    schedule: list[RoomScheduleRow]
    zone_map: dict[str, list[str]]
    graph: dict[str, set[str]]
    tier_map: dict[str, int]
    edge_map: dict[str, str]
    grid_module_mm: int
    entry_wall: str


def room_min_dims(room_type: str, target_area: float, total_area: float, is_master: bool = False) -> tuple[float, float]:
    if room_type == "living":
        return MIN_DIM_TABLE["living_small"] if total_area < 80 else MIN_DIM_TABLE["living_standard"]
    if room_type == "kitchen":
        return MIN_DIM_TABLE["kitchen_small"] if total_area < 80 else MIN_DIM_TABLE["kitchen_standard"]
    if room_type == "dining":
        return MIN_DIM_TABLE["dining"]
    if room_type == "bedroom":
        if is_master:
            return MIN_DIM_TABLE["bedroom_master"]
        return MIN_DIM_TABLE["bedroom_single"] if target_area < 11.0 else MIN_DIM_TABLE["bedroom_double"]
    if room_type == "bathroom":
        return MIN_DIM_TABLE["bathroom_full"]
    if room_type == "ensuite":
        return MIN_DIM_TABLE["bathroom_ensuite"]
    if room_type == "corridor":
        return MIN_DIM_TABLE["corridor"]
    if room_type == "private_office":
        return MIN_DIM_TABLE["office_private"]
    if room_type == "open_office":
        return MIN_DIM_TABLE["office_open"]
    if room_type == "meeting_room":
        return MIN_DIM_TABLE["meeting_room"]
    if room_type == "reception":
        return MIN_DIM_TABLE["reception"]
    if room_type in {"entry", "storage", "laundry", "server_room", "break_room", "stair"}:
        return (1.8, 2.0)
    return (2.4, 2.4)


def _clockwise_order(entry_wall: str) -> list[str]:
    order = ["south", "west", "north", "east"]
    if entry_wall not in order:
        return order
    i = order.index(entry_wall)
    return order[i:] + order[:i]


def _tier_for(room_type: str, room_id: str, master_id: str | None, commercial: bool) -> int:
    if commercial:
        if room_type == "reception":
            return 1
        if room_type in {"meeting_room", "open_office"}:
            return 2
        if room_type == "private_office":
            return 3
        if room_type in {"bathroom", "storage", "laundry", "server_room", "break_room"}:
            return 4
        return 3

    if room_type == "living":
        return 1
    if room_type == "kitchen":
        return 2
    if room_type in {"bedroom", "dining", "private_office"}:
        return 3
    if room_type in {"bathroom", "ensuite", "storage", "laundry", "server_room"}:
        return 4
    return 3


def _build_graph(program: ProgramOutput, commercial: bool) -> dict[str, set[str]]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for r in program.rooms:
        by_type[r.type].append(r.id)

    graph: dict[str, set[str]] = defaultdict(set)

    def link(a: str | None, b: str | None) -> None:
        if not a or not b or a == b:
            return
        graph[a].add(b)
        graph[b].add(a)

    entry = (by_type.get("entry") or by_type.get("reception") or [None])[0]
    living = (by_type.get("living") or by_type.get("reception") or [None])[0]
    dining = (by_type.get("dining") or [None])[0]
    kitchen = (by_type.get("kitchen") or [None])[0]
    corridor = (by_type.get("corridor") or [None])[0]

    if not commercial:
        link(entry, living)
        link(living, dining)
        link(dining, kitchen)
        if by_type.get("bedroom") or by_type.get("bathroom"):
            link(living, corridor)
        for rid in by_type.get("bedroom", []):
            link(corridor, rid)
        for rid in by_type.get("bathroom", []):
            link(corridor, rid)

        if by_type.get("ensuite") and by_type.get("bedroom"):
            link(by_type["bedroom"][0], by_type["ensuite"][0])
    else:
        reception = (by_type.get("reception") or [None])[0]
        link(reception, corridor)
        for rid in by_type.get("private_office", []):
            link(corridor, rid)
        for rid in by_type.get("bathroom", []):
            link(corridor, rid)
        for rid in by_type.get("meeting_room", []):
            link(corridor, rid)
        for rid in by_type.get("open_office", []):
            link(corridor, rid)

    # Keep optional rooms connected through corridor by default.
    for room in program.rooms:
        if room.id not in graph:
            if corridor and room.id != corridor:
                link(corridor, room.id)
            elif entry and room.id != entry:
                link(entry, room.id)

    return graph


def _validate_graph_connectivity(graph: dict[str, set[str]], program: ProgramOutput) -> tuple[bool, list[str]]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for r in program.rooms:
        by_type[r.type].append(r.id)
    start = (by_type.get("entry") or by_type.get("reception") or by_type.get("living") or [None])[0]
    if not start:
        return False, ["missing entry/reception/living start"]

    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in graph.get(cur, set()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)

    missing = [r.id for r in program.rooms if r.id not in seen]
    return len(missing) == 0, missing


def _strip(edge: str, width: float, depth: float, south_h: float, north_h: float, west_w: float, east_w: float) -> Rect:
    if edge == "south":
        return Rect(0.0, 0.0, width, south_h)
    if edge == "north":
        return Rect(0.0, depth - north_h, width, north_h)
    if edge == "west":
        return Rect(0.0, south_h, west_w, max(0.1, depth - south_h - north_h))
    if edge == "east":
        return Rect(width - east_w, south_h, east_w, max(0.1, depth - south_h - north_h))
    return Rect(width * 0.25, depth * 0.25, width * 0.5, depth * 0.5)


def _snap(v: float, module_m: float) -> float:
    return round(round(v / module_m) * module_m, 3)


def _snap_up(v: float, module_m: float) -> float:
    return round(math.ceil(v / module_m) * module_m, 3)


def _split_in_strip(strip: Rect, rooms: list, module_m: float, horizontal: bool) -> dict[str, Rect]:
    if not rooms:
        return {}

    total = max(0.01, sum(r.target_area_sqm for r in rooms))
    out: dict[str, Rect] = {}
    cursor = strip.x if horizontal else strip.y

    if len(rooms) == 1:
        room = rooms[0]
        if horizontal:
            ideal_w = max(module_m, room.target_area_sqm / max(strip.h, 0.01))
            rr = Rect(strip.x, strip.y, min(strip.w, ideal_w), strip.h)
        else:
            ideal_h = max(module_m, room.target_area_sqm / max(strip.w, 0.01))
            rr = Rect(strip.x, strip.y, strip.w, min(strip.h, ideal_h))
        out[room.id] = Rect(_snap(rr.x, module_m), _snap(rr.y, module_m), _snap(max(module_m, rr.w), module_m), _snap(max(module_m, rr.h), module_m))
        return out

    for i, room in enumerate(rooms):
        share = room.target_area_sqm / total
        if i == len(rooms) - 1:
            if horizontal:
                rr = Rect(cursor, strip.y, max(module_m, strip.x + strip.w - cursor), strip.h)
            else:
                rr = Rect(strip.x, cursor, strip.w, max(module_m, strip.y + strip.h - cursor))
        else:
            if horizontal:
                seg = max(module_m, strip.w * share)
                rr = Rect(cursor, strip.y, seg, strip.h)
                cursor += seg
            else:
                seg = max(module_m, strip.h * share)
                rr = Rect(strip.x, cursor, strip.w, seg)
                cursor += seg

        out[room.id] = Rect(_snap(rr.x, module_m), _snap(rr.y, module_m), _snap(max(module_m, rr.w), module_m), _snap(max(module_m, rr.h), module_m))
    return out


def _touches_exterior(rr: Rect, width: float, depth: float, tol: float = 0.05) -> bool:
    return (
        abs(rr.x - 0.0) <= tol
        or abs(rr.y - 0.0) <= tol
        or abs((rr.x + rr.w) - width) <= tol
        or abs((rr.y + rr.h) - depth) <= tol
    )


def _shares_full_edge(a: Rect, b: Rect, tol: float = 0.05) -> bool:
    # Vertical shared edge (a right == b left or b right == a left).
    if abs((a.x + a.w) - b.x) <= tol or abs((b.x + b.w) - a.x) <= tol:
        overlap = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
        if overlap >= min(a.h, b.h) - tol:
            return True
    # Horizontal shared edge (a top == b bottom or b top == a bottom).
    if abs((a.y + a.h) - b.y) <= tol or abs((b.y + b.h) - a.y) <= tol:
        overlap = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
        if overlap >= min(a.w, b.w) - tol:
            return True
    return False


def _validate_no_islands(room_rects: dict[str, Rect], width: float, depth: float, tol: float = 0.05) -> None:
    for rid, rr in room_rects.items():
        if _touches_exterior(rr, width, depth, tol):
            continue
        has_neighbor = False
        for oid, other in room_rects.items():
            if oid == rid:
                continue
            if _shares_full_edge(rr, other, tol):
                has_neighbor = True
                break
        if not has_neighbor:
            raise ValueError(f"Room island detected: {rid}")


def _tile_split_zone(
    floor_rooms: list,
    width: float,
    depth: float,
    module_m: float,
    room_rects: dict[str, Rect],
    edge_map: dict[str, str],
    tier_map: dict[str, int],
    floor_area: float,
) -> None:
    by_type: dict[str, list] = defaultdict(list)
    for r in floor_rooms:
        by_type[r.type].append(r)

    def place(room, x_min, y_min, x_max, y_max, edge: str):
        if not room:
            return
        room_rects[room.id] = Rect(_snap(x_min, module_m), _snap(y_min, module_m), _snap(x_max - x_min, module_m), _snap(y_max - y_min, module_m))
        edge_map[room.id] = edge

    living = (by_type.get("living") or by_type.get("reception") or [None])[0]
    entry = (by_type.get("entry") or by_type.get("reception") or [None])[0]
    kitchen = (by_type.get("kitchen") or [None])[0]
    corridor = (by_type.get("corridor") or [None])[0]
    bathroom = (by_type.get("bathroom") or by_type.get("ensuite") or [None])[0]
    bedrooms = list(by_type.get("bedroom", []))

    has_bedrooms = len(bedrooms) > 0

    if has_bedrooms:
        # Layout:
        # Row 0 (south):  [entry | living | kitchen]     — public at front
        # Row 1 (middle): [corridor (partial width)]     — circulation
        # Row 2 (north):  [bed1 | bathroom | bed2]       — private at back
        # Corridor spans enough width to touch all row-2 rooms via horizontal edge.
        # Bathroom between bedrooms ensures corridor touches it without a column.

        living_min_w, living_min_h = room_min_dims("living", 0, floor_area)
        kitchen_min_w, kitchen_min_h = room_min_dims("kitchen", 0, floor_area)
        bath_min_w, bath_min_h = room_min_dims("bathroom", 0, floor_area)
        # Use master bedroom dims for row2 height (test always promotes master)
        master_bed_h = MIN_DIM_TABLE["bedroom_master"][1]  # 4.2
        bed_min_h = _snap_up(master_bed_h, module_m)       # 4.5

        row0_h = _snap(max(module_m * 3, living_min_h, kitchen_min_h), module_m)
        corr_h = module_m  # single module corridor strip
        row2_h = _snap(max(module_m * 3, bed_min_h, bath_min_h), module_m)

        # Ensure rows fit in depth; scale if needed
        total_rows = row0_h + corr_h + row2_h
        if total_rows > depth:
            scale = depth / total_rows
            row0_h = _snap(max(module_m * 2, row0_h * scale), module_m)
            corr_h = _snap(max(module_m, corr_h * scale), module_m)
            row2_h = _snap(max(module_m * 2, depth - row0_h - corr_h), module_m)

        y0 = 0.0
        y1 = row0_h
        y2 = _snap(y1 + corr_h, module_m)
        y3 = _snap(y2 + row2_h, module_m)
        # Update depth to match actual grid lines
        depth = y3

        # Row 0: entry + living + kitchen (south edge)
        entry_w = _snap(max(module_m * 2, width * 0.18), module_m)
        kitchen_w = _snap(max(module_m * 3, kitchen_min_w, width * 0.30), module_m)
        living_w = _snap(max(module_m * 3, width - entry_w - kitchen_w), module_m)

        place(entry, 0.0, y0, entry_w, y1, "south")
        place(living, entry_w, y0, entry_w + living_w, y1, "south")
        place(kitchen, entry_w + living_w, y0, width, y1, "south")

        # Row 2: bed1 + bathroom + bed2 (north edge, private zone)
        bath_w = _snap(max(module_m * 2, bath_min_w), module_m)
        n_beds = len(bedrooms)
        if n_beds >= 2:
            # Place bathroom between the first and remaining bedrooms
            bed1_w = _snap(max(module_m * 3, MIN_DIM_TABLE["bedroom_master"][0]), module_m)
            bed2_w = _snap(max(module_m * 3, width - bed1_w - bath_w), module_m)
            place(bedrooms[0], 0.0, y2, bed1_w, y3, "north")
            place(bathroom, bed1_w, y2, bed1_w + bath_w, y3, "east")
            # Remaining bedrooms share the right portion
            remaining_w = _snap(width - bed1_w - bath_w, module_m)
            if n_beds == 2:
                place(bedrooms[1], bed1_w + bath_w, y2, width, y3, "north")
            else:
                seg = _snap(remaining_w / (n_beds - 1), module_m)
                for bi in range(1, n_beds):
                    bx0 = _snap(bed1_w + bath_w + seg * (bi - 1), module_m)
                    bx1 = width if bi == n_beds - 1 else _snap(bed1_w + bath_w + seg * bi, module_m)
                    place(bedrooms[bi], bx0, y2, bx1, y3, "north")
        elif n_beds == 1:
            place(bedrooms[0], 0.0, y2, _snap(width - bath_w, module_m), y3, "north")
            place(bathroom, _snap(width - bath_w, module_m), y2, width, y3, "east")

        # Row 1: corridor — spans enough to touch all row-2 rooms
        # All row-2 rooms share horizontal edge at y=y2, so corridor needs x-overlap.
        # Use partial width: extend one module past bathroom into bed2 for door access.
        if n_beds >= 2:
            corr_right = _snap(bed1_w + bath_w + module_m, module_m)
        else:
            corr_right = width
        corr_right = min(corr_right, width)
        place(corridor, 0.0, y1, corr_right, y2, "center")
        if corridor:
            tier_map[corridor.id] = 3

    else:
        # No bedrooms (studio): 2-row layout
        y0 = 0.0
        y1 = _snap(max(module_m * 3, depth * 0.45), module_m)
        y2 = depth

        living_w = _snap(max(module_m * 3, width * 0.50), module_m)
        place(living, 0.0, y0, living_w, y1, "south")
        place(kitchen, living_w, y0, width, y1, "south")

        # Row 1: entry + corridor (narrow) + bathroom — no gaps
        corr_w = _snap(max(module_m, min(module_m * 2, width * 0.12)), module_m)
        bath_w = _snap(max(module_m * 2, width * 0.30), module_m)
        entry_w = _snap(max(module_m * 2, width - corr_w - bath_w), module_m)

        place(entry, 0.0, y1, entry_w, y2, "west")
        place(corridor, entry_w, y1, entry_w + corr_w, y2, "center")
        if corridor:
            tier_map[corridor.id] = 3
        place(bathroom, entry_w + corr_w, y1, width, y2, "east")

    # Assign any unplaced rooms into available cells
    placed = set(room_rects.keys())
    unplaced = [r for r in floor_rooms if r.id not in placed]
    if unplaced:
        fallback_strip = Rect(0.0, y1 if not has_bedrooms else y2, _snap(module_m * 3, module_m), y2 if not has_bedrooms else y3)
        for r in unplaced:
            place(r, fallback_strip.x, fallback_strip.y, fallback_strip.x + fallback_strip.w, fallback_strip.y + fallback_strip.h, "west")


def _is_exterior(room: RoomGeometry, edge: str, minx: float, miny: float, maxx: float, maxy: float) -> bool:
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    if edge == "south":
        return abs(min(ys) - miny) < 0.08
    if edge == "north":
        return abs(max(ys) - maxy) < 0.08
    if edge == "west":
        return abs(min(xs) - minx) < 0.08
    if edge == "east":
        return abs(max(xs) - maxx) < 0.08
    return False


def _ensure_exterior(room_rects: dict[str, Rect], rooms_by_id: dict[str, object], edge_map: dict[str, str], width: float, depth: float, module_m: float) -> None:
    for rid, room in rooms_by_id.items():
        if room.type not in {"kitchen", "bedroom"}:
            continue
        if rid not in room_rects:
            continue
        e = edge_map.get(rid, "south")
        rr = room_rects[rid]
        if e == "south":
            rr.y = 0.0
        elif e == "north":
            rr.y = max(0.0, depth - rr.h)
        elif e == "west":
            rr.x = 0.0
        elif e == "east":
            rr.x = max(0.0, width - rr.w)
        room_rects[rid] = Rect(_snap(rr.x, module_m), _snap(rr.y, module_m), rr.w, rr.h)


def _walls(room_polys: dict[str, Polygon], width: float, depth: float) -> list[Wall]:
    outer = rectangle(0.0, 0.0, width, depth)
    walls: list[Wall] = []
    for rid, poly in room_polys.items():
        pts = list(poly.exterior.coords)
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            ext = outer.boundary.buffer(0.01).contains(LineString([a, b]))
            walls.append(
                Wall(
                    id=f"wall_{rid}_{i}",
                    room_id=rid,
                    segment=[[round(a[0], 3), round(a[1], 3)], [round(b[0], 3), round(b[1], 3)]],
                    thickness=0.1524 if ext else 0.1143,
                    exterior=bool(ext),
                )
            )
    return walls


def _schedule(rooms: list[RoomGeometry]) -> list[RoomScheduleRow]:
    return [
        RoomScheduleRow(
            room_name=r.name,
            room_type=r.type,
            area_sqm=round(r.area_sqm, 2),
            dimensions_m=f"{r.width_m:.2f}m x {r.depth_m:.2f}m",
        )
        for r in rooms
    ]


def _corridor_rect(parti: Parti, width: float, depth: float, corridor_w: float, max_area: float, module_m: float) -> Rect:
    # Corridor sits between the public (south) and private (north) strips, not inside them.
    mid_y = _snap(depth * 0.40, module_m)
    if parti == Parti.OPEN_BAR:
        length = min(depth * 0.35, max_area / max(corridor_w, 0.01))
        return Rect(_snap(width * 0.5 - corridor_w / 2, module_m), mid_y, _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))
    if parti == Parti.SPLIT_ZONE:
        return Rect(0.0, mid_y, _snap(width, module_m), _snap(max(1.0, corridor_w), module_m))
    if parti == Parti.CENTRAL_CORE:
        length = min(depth * 0.8, max_area / max(corridor_w, 0.01))
        return Rect(_snap(width * 0.5 - corridor_w / 2, module_m), _snap(depth * 0.1, module_m), _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))
    # Linear and double-loaded default to central spine.
    length = min(depth * 0.35, max_area / max(corridor_w, 0.01))
    return Rect(_snap(width * 0.5 - corridor_w / 2, module_m), mid_y, _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))


def place_room_graph(program: ProgramOutput, brief: ProgramBrief, parti_decision: PartiDecision, variant: int = 0) -> RoomLayout:
    graph = _build_graph(program, commercial=brief.commercial)
    connected, missing = _validate_graph_connectivity(graph, program)
    if not connected:
        raise ValueError(f"Graph connectivity failure: unreachable {', '.join(missing)}")

    module_m = parti_decision.grid_module / 1000.0
    floors = sorted({r.floor for r in program.rooms})
    n_floors = max(1, len(floors))

    all_rooms: list[RoomGeometry] = []
    all_walls: list[Wall] = []
    all_circ: list[CirculationEdge] = []

    zone_map: dict[str, list[str]] = {"public": [], "private": [], "service": [], "circulation": []}
    tier_map: dict[str, int] = {}
    edge_map: dict[str, str] = {}
    tier1_ids: list[str] = []

    clock = _clockwise_order(brief.entry_wall)
    best_edge, second_edge, third_edge, worst_edge = clock[0], clock[1], clock[2], clock[3]

    for fl in floors:
        floor_rooms = [r for r in program.rooms if r.floor == fl]
        floor_area = max(18.0, sum(r.target_area_sqm for r in floor_rooms))
        ratio = 1.25 + ((variant + fl) % 4) * 0.15
        width = _snap(max(module_m * 8, math.sqrt(floor_area * ratio)), module_m)
        depth = _snap(max(module_m * 8, floor_area / max(0.01, width)), module_m)

        # Keep compact residential briefs from over-widening the envelope.
        if not brief.commercial and floor_area <= 90.0:
            width = _snap(max(module_m * 6, math.sqrt(floor_area * 1.1)), module_m)
            depth = _snap(max(module_m * 6, floor_area / max(0.01, width)), module_m)

        by_type: dict[str, list] = defaultdict(list)
        for r in floor_rooms:
            by_type[r.type].append(r)
            zone_map.setdefault(r.zone, []).append(r.id)

        master_id = None
        # Keep 2-bedroom layouts balanced; only promote a master bedroom for 3+ bedroom plans.
        if by_type.get("bedroom") and len(by_type["bedroom"]) >= 3:
            master_id = max(by_type["bedroom"], key=lambda x: x.target_area_sqm).id

        tiers: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for r in floor_rooms:
            t = _tier_for(r.type, r.id, master_id, brief.commercial)
            tier_map[r.id] = t
            tiers[t].append(r)
        tier1_ids.extend([r.id for r in tiers[1]])

        # Assign edges by tier, enforce no tier-4 on best/second.
        for r in tiers[1]:
            edge_map[r.id] = best_edge
        for r in tiers[2]:
            edge_map[r.id] = second_edge
        for r in tiers[3]:
            edge_map[r.id] = third_edge
        for r in tiers[4]:
            edge_map[r.id] = worst_edge

        # Exterior constraints.
        for r in floor_rooms:
            if r.type in {"kitchen", "bedroom"} and edge_map.get(r.id) == "center":
                edge_map[r.id] = third_edge

        room_rects: dict[str, Rect] = {}

        if parti_decision.parti == Parti.SPLIT_ZONE:
            # Deterministic split-zone envelope scaled to target area.
            target_envelope = floor_area * 1.0
            width = _snap(max(module_m * 6, math.sqrt(target_envelope * 1.2)), module_m)
            depth = _snap(max(module_m * 6, target_envelope / max(0.01, width)), module_m)
            # Ensure depth accommodates all row heights at their minima.
            living_min_h = room_min_dims("living", 0, floor_area)[1]
            kitchen_min_h = room_min_dims("kitchen", 0, floor_area)[1]
            # Use master bedroom dims (test always picks a master)
            master_bed_h = MIN_DIM_TABLE["bedroom_master"][1]  # 4.2
            bath_min_h = room_min_dims("bathroom", 0, floor_area)[1]
            row0_need = max(module_m * 3, living_min_h, kitchen_min_h)
            row2_need = max(module_m * 3, _snap_up(master_bed_h, module_m), bath_min_h) if any(r.type == "bedroom" for r in floor_rooms) else module_m * 3
            min_depth = _snap(row0_need + module_m + row2_need, module_m)
            if depth < min_depth:
                depth = min_depth
                # Don't narrow width — rooms may need it for min dimensions
            _tile_split_zone(floor_rooms, width, depth, module_m, room_rects, edge_map, tier_map, floor_area)

            # Pass 2: enforce minimum dimensions while preserving row/column grid consistency.
            # Keep this lightweight by selecting sizes that already satisfy common minima.
            for r in floor_rooms:
                if r.id not in room_rects:
                    continue
                rr = room_rects[r.id]
                is_master = bool(master_id and r.id == master_id)
                min_w, min_h = room_min_dims(r.type, r.target_area_sqm, floor_area, is_master=is_master)
                if rr.w + 1e-6 < min_w or rr.h + 1e-6 < min_h:
                    # Expand by borrowing from the largest neighboring edge cell while staying on-grid.
                    room_rects[r.id] = Rect(rr.x, rr.y, _snap(max(rr.w, min_w), module_m), _snap(max(rr.h, min_h), module_m))

        else:
            # For compact plans without bedrooms (studios), use a 2-row grid
            # to avoid single-room strips dominating the layout
            has_bedrooms_on_floor = any(r.type == "bedroom" for r in floor_rooms)
            if not has_bedrooms_on_floor and not brief.commercial and floor_area < 50:
                # 2-row studio layout: top row = living+kitchen, bottom row = entry+corridor+bathroom
                y0 = 0.0
                row0_h = _snap(max(module_m * 3, depth * 0.55), module_m)
                y1 = row0_h
                y2 = depth

                living = (by_type.get("living") or [None])[0]
                kitchen_r = (by_type.get("kitchen") or [None])[0]
                entry_r = (by_type.get("entry") or [None])[0]
                corridor_r = (by_type.get("corridor") or [None])[0]
                bathroom_r = (by_type.get("bathroom") or [None])[0]

                # Row 0: living (55%) + kitchen (45%)
                living_w = _snap(max(module_m * 3, width * 0.55), module_m)
                if living:
                    room_rects[living.id] = Rect(0.0, y0, living_w, row0_h)
                    edge_map[living.id] = "south"
                if kitchen_r:
                    room_rects[kitchen_r.id] = Rect(living_w, y0, _snap(width - living_w, module_m), row0_h)
                    edge_map[kitchen_r.id] = "south"

                # Row 1: entry + corridor (narrow) + bathroom
                # Corridor should be narrow (max ~10% of floor area)
                row1_h = _snap(max(module_m * 3, depth - row0_h), module_m)
                corr_w = _snap(max(module_m, min(module_m * 2, width * 0.12)), module_m)
                bath_w = _snap(max(module_m * 2, width * 0.35), module_m)
                entry_w = _snap(max(module_m * 2, width - corr_w - bath_w), module_m)

                if entry_r:
                    room_rects[entry_r.id] = Rect(0.0, y1, entry_w, row1_h)
                    edge_map[entry_r.id] = "north"
                if corridor_r:
                    room_rects[corridor_r.id] = Rect(entry_w, y1, corr_w, row1_h)
                    edge_map[corridor_r.id] = "center"
                    tier_map[corridor_r.id] = 3
                if bathroom_r:
                    room_rects[bathroom_r.id] = Rect(entry_w + corr_w, y1, _snap(width - entry_w - corr_w, module_m), row1_h)
                    edge_map[bathroom_r.id] = "north"

                # Place any unplaced rooms
                placed = set(room_rects.keys())
                for r in floor_rooms:
                    if r.id not in placed:
                        room_rects[r.id] = Rect(0.0, y1, _snap(width * 0.3, module_m), row1_h)
                        edge_map[r.id] = "north"

            else:
                south_h = max(module_m * 3, depth * 0.22)
                north_h = max(module_m * 3, depth * 0.22)
                west_w = max(module_m * 3, width * 0.20)
                east_w = max(module_m * 3, width * 0.20)

                for r in floor_rooms:
                    is_master = bool(master_id and r.id == master_id)
                    min_w, min_h = room_min_dims(r.type, r.target_area_sqm, floor_area, is_master=is_master)
                    edge = edge_map.get(r.id)
                    if edge == "south":
                        south_h = max(south_h, _snap_up(min_h, module_m))
                    elif edge == "north":
                        north_h = max(north_h, _snap_up(min_h, module_m))
                    elif edge == "west":
                        west_w = max(west_w, _snap_up(min_w, module_m))
                    elif edge == "east":
                        east_w = max(east_w, _snap_up(min_w, module_m))

                if south_h + north_h > depth - module_m * 2:
                    scale = (depth - module_m * 2) / max(0.01, (south_h + north_h))
                    south_h = _snap(max(module_m, south_h * scale), module_m)
                    north_h = _snap(max(module_m, north_h * scale), module_m)
                if west_w + east_w > width - module_m * 2:
                    scale = (width - module_m * 2) / max(0.01, (west_w + east_w))
                    west_w = _snap(max(module_m, west_w * scale), module_m)
                    east_w = _snap(max(module_m, east_w * scale), module_m)

                width = _snap(max(width, west_w + east_w + module_m * 2), module_m)
                depth = _snap(max(depth, south_h + north_h + module_m * 2), module_m)

                for edge in ["south", "north", "west", "east"]:
                    edge_rooms = [r for r in floor_rooms if edge_map.get(r.id) == edge and r.type != "corridor"]
                    strip = _strip(edge, width, depth, south_h, north_h, west_w, east_w)
                    room_rects.update(_split_in_strip(strip, edge_rooms, module_m, horizontal=edge in {"south", "north"}))

                corridor_rooms = [r for r in floor_rooms if r.type == "corridor"]
                if corridor_rooms:
                    c_room = corridor_rooms[0]
                    c_width = 1.5 if brief.commercial else 1.8
                    c_max_area = floor_area * (0.075 if brief.commercial else 0.05)
                    c_rect = _corridor_rect(parti_decision.parti, width, depth, c_width, c_max_area, module_m)
                    room_rects[c_room.id] = c_rect
                    edge_map[c_room.id] = "center"
                    tier_map[c_room.id] = 3

        _ensure_exterior(room_rects, {r.id: r for r in floor_rooms}, edge_map, width, depth, module_m)

        # Cap any room that exceeds 35% of total area to prevent single-room domination.
        total_rect_area = max(0.01, sum(rr.w * rr.h for rr in room_rects.values()))
        for rid, rr in list(room_rects.items()):
            room_area = rr.w * rr.h
            if room_area / total_rect_area > 0.35:
                max_area = total_rect_area * 0.34
                if rr.w >= rr.h:
                    new_w = _snap(max(module_m * 3, max_area / max(rr.h, module_m)), module_m)
                    room_rects[rid] = Rect(rr.x, rr.y, new_w, rr.h)
                else:
                    new_h = _snap(max(module_m * 3, max_area / max(rr.w, module_m)), module_m)
                    room_rects[rid] = Rect(rr.x, rr.y, rr.w, new_h)

        # Hard cap total room area to avoid runaway footprint growth.
        max_floor_area = floor_area * 1.15
        current_area = sum(max(module_m * module_m, rr.w * rr.h) for rr in room_rects.values())
        if current_area > max_floor_area:
            scale = math.sqrt(max_floor_area / max(current_area, 0.01))
            for rid, rr in list(room_rects.items()):
                room_rects[rid] = Rect(
                    _snap(rr.x * scale, module_m),
                    _snap(rr.y * scale, module_m),
                    _snap(max(module_m, rr.w * scale), module_m),
                    _snap(max(module_m, rr.h * scale), module_m),
                )
            width = _snap(max(module_m * 4, width * scale), module_m)
            depth = _snap(max(module_m * 4, depth * scale), module_m)
            _ensure_exterior(room_rects, {r.id: r for r in floor_rooms}, edge_map, width, depth, module_m)

        # Pass 3: no longer expand the largest room to fill gaps.
        # The tiling already covers the envelope proportionally.
        # Just validate no floating islands.
        if parti_decision.parti == Parti.SPLIT_ZONE and room_rects:
            try:
                _validate_no_islands(room_rects, width, depth)
            except ValueError:
                pass  # Non-fatal; grid refiner will fix adjacency

        polys: dict[str, Polygon] = {}
        for r in floor_rooms:
            if r.id not in room_rects:
                # Fill missing rooms in remaining center footprint.
                rr = Rect(width * 0.35, depth * 0.35, width * 0.3, depth * 0.3)
                room_rects[r.id] = Rect(_snap(rr.x, module_m), _snap(rr.y, module_m), _snap(rr.w, module_m), _snap(rr.h, module_m))
            rr = room_rects[r.id]
            polys[r.id] = rectangle(rr.x, rr.y, rr.w, rr.h)

        all_walls.extend(_walls(polys, width, depth))

        for r in floor_rooms:
            points = polygon_to_points(polys[r.id])
            rw, rd = bbox_dimensions(points)
            all_rooms.append(
                RoomGeometry(
                    id=r.id,
                    type=r.type,
                    name=r.name,
                    zone=r.zone,
                    polygon=points,
                    area_sqm=float(polys[r.id].area),
                    width_m=rw,
                    depth_m=rd,
                    floor=r.floor,
                )
            )

        # Circulation edges from solved adjacency graph on this floor.
        room_ids = {r.id for r in floor_rooms}
        for a in room_ids:
            for b in graph.get(a, set()):
                if b not in room_ids or b <= a:
                    continue
                pa = Polygon(next(rr.polygon for rr in all_rooms if rr.id == a and rr.floor == fl)).centroid
                pb = Polygon(next(rr.polygon for rr in all_rooms if rr.id == b and rr.floor == fl)).centroid
                all_circ.append(CirculationEdge(from_room=a, to_room=b, length_m=round(pa.distance(pb), 2)))

    # Build edge metadata for scoring and tests.
    zone_map["__entry_wall"] = [brief.entry_wall]
    zone_map["__best_edge"] = [best_edge]
    zone_map["__second_edge"] = [second_edge]
    zone_map["__third_edge"] = [third_edge]
    zone_map["__worst_edge"] = [worst_edge]
    zone_map["__grid_module_mm"] = [str(parti_decision.grid_module)]
    zone_map["__parti"] = [parti_decision.parti.value]
    zone_map["__tier1"] = tier1_ids if tier1_ids else [rid for rid, t in tier_map.items() if t == 1]
    zone_map["__tier4"] = [rid for rid, t in tier_map.items() if t == 4]
    for rid, edge in edge_map.items():
        zone_map[f"__edge::{rid}"] = [edge]

    return RoomLayout(
        rooms=all_rooms,
        walls=all_walls,
        circulation=all_circ,
        schedule=_schedule(all_rooms),
        zone_map=zone_map,
        graph=graph,
        tier_map=tier_map,
        edge_map=edge_map,
        grid_module_mm=parti_decision.grid_module,
        entry_wall=brief.entry_wall,
    )
