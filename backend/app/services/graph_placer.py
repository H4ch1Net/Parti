from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon

from app.core.geometry import bbox_dimensions, polygon_to_points, rectangle
from app.models.schemas import CirculationEdge, ProgramOutput, RoomGeometry, RoomScheduleRow, Wall
from app.services.parti_selector import Parti, PartiDecision, ProgramBrief


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
    "corridor": (1.0, 1.0),
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
    if room_type == "bedroom" and master_id and room_id == master_id:
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
    if parti == Parti.OPEN_BAR:
        length = min(depth * 0.35, max_area / max(corridor_w, 0.01))
        return Rect(_snap(width * 0.45, module_m), 0.0, _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))
    if parti == Parti.SPLIT_ZONE:
        length = min(width * 0.55, max_area / max(corridor_w, 0.01))
        return Rect(_snap(width * 0.2, module_m), _snap(depth * 0.45, module_m), _snap(max(module_m, length), module_m), _snap(corridor_w, module_m))
    if parti == Parti.CENTRAL_CORE:
        length = min(depth * 0.8, max_area / max(corridor_w, 0.01))
        return Rect(_snap(width * 0.5 - corridor_w / 2, module_m), _snap(depth * 0.1, module_m), _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))
    # Linear and double-loaded default to central spine.
    length = min(depth * 0.85, max_area / max(corridor_w, 0.01))
    return Rect(_snap(width * 0.5 - corridor_w / 2, module_m), 0.0, _snap(corridor_w, module_m), _snap(max(module_m, length), module_m))


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

    clock = _clockwise_order(brief.entry_wall)
    best_edge, second_edge, third_edge, worst_edge = clock[0], clock[1], clock[2], clock[3]

    for fl in floors:
        floor_rooms = [r for r in program.rooms if r.floor == fl]
        floor_area = max(18.0, sum(r.target_area_sqm for r in floor_rooms))
        ratio = 1.25 + ((variant + fl) % 4) * 0.15
        width = _snap(max(module_m * 8, math.sqrt(floor_area * ratio)), module_m)
        depth = _snap(max(module_m * 8, floor_area / max(0.01, width)), module_m)

        by_type: dict[str, list] = defaultdict(list)
        for r in floor_rooms:
            by_type[r.type].append(r)
            zone_map.setdefault(r.zone, []).append(r.id)

        master_id = None
        if by_type.get("bedroom"):
            master_id = max(by_type["bedroom"], key=lambda x: x.target_area_sqm).id

        tiers: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for r in floor_rooms:
            t = _tier_for(r.type, r.id, master_id, brief.commercial)
            tier_map[r.id] = t
            tiers[t].append(r)

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

        south_h = max(module_m * 3, depth * 0.22)
        north_h = max(module_m * 3, depth * 0.22)
        west_w = max(module_m * 3, width * 0.20)
        east_w = max(module_m * 3, width * 0.20)

        for r in floor_rooms:
            is_master = bool(master_id and r.id == master_id)
            conserv_floor_area = max(floor_area * 1.10, 80.0)
            min_w, min_h = room_min_dims(r.type, r.target_area_sqm, conserv_floor_area, is_master=is_master)
            edge = edge_map.get(r.id)
            if edge == "south":
                south_h = max(south_h, _snap_up(min_h, module_m))
            elif edge == "north":
                north_h = max(north_h, _snap_up(min_h, module_m))
            elif edge == "west":
                west_w = max(west_w, _snap_up(min_w, module_m))
            elif edge == "east":
                east_w = max(east_w, _snap_up(min_w, module_m))

        # Keep bands feasible within envelope.
        if south_h + north_h > depth - module_m * 2:
            scale = (depth - module_m * 2) / max(0.01, (south_h + north_h))
            south_h = _snap(max(module_m, south_h * scale), module_m)
            north_h = _snap(max(module_m, north_h * scale), module_m)
        if west_w + east_w > width - module_m * 2:
            scale = (width - module_m * 2) / max(0.01, (west_w + east_w))
            west_w = _snap(max(module_m, west_w * scale), module_m)
            east_w = _snap(max(module_m, east_w * scale), module_m)

        room_rects: dict[str, Rect] = {}

        for edge in ["south", "north", "west", "east"]:
            edge_rooms = [r for r in floor_rooms if edge_map.get(r.id) == edge and r.type != "corridor"]
            strip = _strip(edge, width, depth, south_h, north_h, west_w, east_w)
            room_rects.update(_split_in_strip(strip, edge_rooms, module_m, horizontal=edge in {"south", "north"}))

        # Enforce type minimum dimensions after strip splitting.
        for r in floor_rooms:
            if r.id not in room_rects or r.type == "corridor":
                continue
            rr = room_rects[r.id]
            is_master = bool(master_id and r.id == master_id)
            conserv_floor_area = max(floor_area * 1.10, 80.0)
            min_w, min_h = room_min_dims(r.type, r.target_area_sqm, conserv_floor_area, is_master=is_master)
            new_w = max(rr.w, _snap_up(min_w, module_m))
            new_h = max(rr.h, _snap_up(min_h, module_m))

            x, y = rr.x, rr.y
            edge = edge_map.get(r.id, "south")
            if edge == "north":
                y = max(0.0, depth - new_h)
            elif edge == "east":
                x = max(0.0, width - new_w)
            elif edge == "south":
                y = 0.0
            elif edge == "west":
                x = 0.0

            room_rects[r.id] = Rect(_snap(x, module_m), _snap(y, module_m), _snap(new_w, module_m), _snap(new_h, module_m))

        # Corridor along parti spine with strict area cap.
        corridor_rooms = [r for r in floor_rooms if r.type == "corridor"]
        if corridor_rooms:
            c_room = corridor_rooms[0]
            c_width = 1.5 if brief.commercial else 1.0
            c_max_area = floor_area * 0.075
            c_rect = _corridor_rect(parti_decision.parti, width, depth, c_width, c_max_area, module_m)
            room_rects[c_room.id] = c_rect
            edge_map[c_room.id] = "center"
            tier_map[c_room.id] = 3

        _ensure_exterior(room_rects, {r.id: r for r in floor_rooms}, edge_map, width, depth, module_m)

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
    zone_map["__tier1"] = [rid for rid, t in tier_map.items() if t == 1]
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
