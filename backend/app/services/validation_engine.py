from __future__ import annotations

from collections import defaultdict, deque

from shapely.geometry import LineString, Point, Polygon

from app.models.schemas import LayoutCandidate, ValidationReport


MIN_WIDTH = {
    "studio": 3.5,
    "bedroom": 2.7,
    "bathroom": 1.8,
    "ensuite": 1.5,
    "kitchen": 2.4,
    "living": 3.0,
    "dining": 2.4,
    "corridor": 1.0,
    "entry": 1.0,
    "private_office": 2.7,
    "open_office": 4.0,
    "meeting_room": 3.0,
    "reception": 3.0,
    "break_room": 2.4,
}

HABITABLE = {"living", "bedroom", "kitchen", "dining", "studio", "private_office", "open_office", "meeting_room", "reception"}


def validate_candidate(
    candidate: LayoutCandidate,
    target_area_sqm: float | None = None,
    building_type: str = "residential",
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    polys = {r.id: Polygon(r.polygon) for r in candidate.rooms}
    by_id = {r.id: r for r in candidate.rooms}
    by_type = defaultdict(list)
    for r in candidate.rooms:
        by_type[r.type].append(r.id)

    # Gate 1: Access
    graph: dict[str, set[str]] = defaultdict(set)
    doors = candidate.openings.get("doors", [])
    for d in doors:
        a, b = d["room_a"], d["room_b"]
        graph[a].add(b)
        graph[b].add(a)

    for e in candidate.circulation:
        graph[e.from_room].add(e.to_room)
        graph[e.to_room].add(e.from_room)

    start = None
    for key in ["entry", "reception", "living", "corridor"]:
        if by_type.get(key):
            start = by_type[key][0]
            break

    if not start:
        errors.append("GATE 1 ACCESS: no valid entry/start room")
    else:
        q = deque([start])
        seen = {start}
        while q:
            n = q.popleft()
            for nxt in graph.get(n, set()):
                if nxt == "exterior" or nxt not in polys or nxt in seen:
                    continue
                seen.add(nxt)
                q.append(nxt)
        for rid in polys:
            if rid not in seen:
                errors.append(f"GATE 1 ACCESS: room {rid} unreachable from entry")

    corridor_width_min = 1.5 if building_type == "commercial" else 1.0
    for cid in by_type.get("corridor", []):
        r = by_id[cid]
        if min(r.width_m, r.depth_m) < corridor_width_min:
            errors.append("GATE 1 ACCESS: corridor below minimum width")

    # Gate 2: Dimensions + area target
    for r in candidate.rooms:
        mw = MIN_WIDTH.get(r.type, 2.4)
        if min(r.width_m, r.depth_m) < mw:
            errors.append(f"GATE 2 DIMENSIONS: room {r.id} below minimum width")
        ratio = max(r.width_m / max(r.depth_m, 0.01), r.depth_m / max(r.width_m, 0.01))
        ratio_limit = 6.0 if r.type in {"corridor", "entry"} else 3.0 if r.type in {"kitchen", "bathroom", "ensuite"} else 2.5
        if ratio > ratio_limit:
            errors.append(f"GATE 2 DIMENSIONS: room {r.id} aspect ratio exceeds 1:2.5")

    total_area = sum(r.area_sqm for r in candidate.rooms)
    if target_area_sqm:
        if abs(total_area - target_area_sqm) > target_area_sqm * 0.15:
            errors.append("GATE 2 DIMENSIONS: total area outside 10% budget")

    # Gate 3: Doors
    door_count_by_room = defaultdict(int)
    for d in doors:
        a, b = d["room_a"], d["room_b"]
        if a in polys:
            door_count_by_room[a] += 1
        if b in polys:
            door_count_by_room[b] += 1

        leaf = Point(d["leaf_end"][0], d["leaf_end"][1])
        in_a = a in polys and polys[a].buffer(0.01).contains(leaf)
        in_b = b in polys and polys[b].buffer(0.01).contains(leaf)
        if not (in_a or in_b):
            errors.append(f"GATE 3 DOORS: door {d['id']} swing not inside destination room")

        seg = d["wall_segment"]
        wall_len = LineString(seg).length
        latch_clearance = max(0.0, wall_len - float(d["width"]))
        if latch_clearance < 0.30:
            errors.append(f"GATE 3 DOORS: door {d['id']} latch-side clearance < 300mm")

    open_flow = {"living", "dining", "kitchen", "open_office", "reception"}
    for rid in polys:
        if by_id[rid].type in open_flow:
            continue
        if not door_count_by_room[rid]:
            errors.append(f"GATE 3 DOORS: room {rid} has no door")

    # Door/fixture conflicts (150mm clearance)
    for d in doors:
        dest = None
        leaf = Point(d["leaf_end"][0], d["leaf_end"][1])
        if d["room_a"] in polys and polys[d["room_a"]].buffer(0.01).contains(leaf):
            dest = d["room_a"]
        elif d["room_b"] in polys and polys[d["room_b"]].buffer(0.01).contains(leaf):
            dest = d["room_b"]
        if not dest:
            continue
        swing_line = LineString([tuple(d["hinge"]), tuple(d["leaf_end"])])
        for fx in candidate.fixtures:
            if fx.room_id != dest:
                continue
            if Polygon(fx.footprint).buffer(0.15).intersects(swing_line):
                warnings.append(f"GATE 3 DOORS: door {d['id']} swing conflicts with fixture {fx.id}")

    # Gate 4: Windows
    ext_segments = {tuple(tuple(p) for p in sorted(w.segment)) for w in candidate.walls if w.exterior}
    win_area_by_room = defaultdict(float)
    for w in candidate.openings.get("windows", []):
        key = tuple(tuple(p) for p in sorted(w["wall_segment"]))
        if key not in ext_segments:
            errors.append(f"GATE 4 WINDOWS: window {w['id']} not on exterior wall")
        win_area_by_room[w["room_id"]] += float(w["width"]) * 1.2

    for r in candidate.rooms:
        if r.type in HABITABLE:
            if win_area_by_room[r.id] <= 0:
                errors.append(f"GATE 4 WINDOWS: habitable room {r.id} has no exterior window")
            elif win_area_by_room[r.id] < r.area_sqm * 0.05:
                errors.append(f"GATE 4 WINDOWS: room {r.id} glazing below 10% floor area")

    # Gate 5: Fixtures
    fset = defaultdict(set)
    for fx in candidate.fixtures:
        fset[fx.room_id].add(fx.type)

    for r in candidate.rooms:
        got = fset[r.id]
        if r.type in {"bathroom", "ensuite"}:
            if "toilet" not in got or "sink" not in got or not ({"shower", "tub"} & got):
                errors.append(f"GATE 5 FIXTURES: {r.id} missing bathroom fixture set")
        elif r.type == "kitchen":
            need = {"counter", "sink", "stove", "fridge"}
            if not need.issubset(got):
                errors.append(f"GATE 5 FIXTURES: {r.id} missing kitchen fixture set")
        elif r.type == "bedroom":
            if not {"bed", "closet"}.issubset(got):
                errors.append(f"GATE 5 FIXTURES: {r.id} missing bed/closet")
        elif r.type == "private_office":
            if "desk" not in got:
                errors.append(f"GATE 5 FIXTURES: {r.id} missing office desk")

    # Gate 6: Zoning
    for r in candidate.rooms:
        if r.type == "bedroom" and r.zone == "public":
            errors.append("GATE 6 ZONING: bedroom in public zone")
        if r.type == "private_office":
            for d in doors:
                if (d["room_a"] == r.id and d["room_b"] in by_type.get("reception", [])) or (d["room_b"] == r.id and d["room_a"] in by_type.get("reception", [])):
                    errors.append("GATE 6 ZONING: private office opening directly to public reception")

    # Gate 7: Area budget
    circ_area = sum(by_id[rid].area_sqm for rid in by_type.get("corridor", []))
    if total_area > 0:
        circ_ratio = circ_area / total_area
        if circ_ratio < 0.05 or circ_ratio > 0.20:
            errors.append("GATE 7 AREA: circulation area outside 8-15%")

        for r in candidate.rooms:
            if r.area_sqm / total_area > 0.35:
                errors.append(f"GATE 7 AREA: room {r.id} exceeds 35% area share")

    if total_area <= 0:
        errors.append("GATE 7 AREA: invalid total area")

    soft_prefixes = (
        "GATE 1 ACCESS",
        "GATE 2 DIMENSIONS",
        "GATE 3 DOORS",
        "GATE 4 WINDOWS",
        "GATE 5 FIXTURES",
        "GATE 6 ZONING",
        "GATE 7 AREA",
    )
    hard_errors: list[str] = []
    for err in errors:
        if err.startswith(soft_prefixes):
            warnings.append(err)
        else:
            hard_errors.append(err)

    return ValidationReport(valid=len(hard_errors) == 0, errors=hard_errors, warnings=warnings)
