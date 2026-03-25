from __future__ import annotations

from collections import defaultdict

from shapely.geometry import Polygon

from app.models.schemas import LayoutCandidate, ProgramOutput, ScoreBreakdown
from app.services.graph_placer import room_min_dims


def _grid_alignment_percent(candidate: LayoutCandidate) -> float:
    grid_mm = int((candidate.zones.get("__grid_module_mm") or ["1200"])[0])
    module = grid_mm / 1000.0
    pts = [pt for w in candidate.walls for pt in w.segment]
    if not pts or module <= 0:
        return 0.0
    on = 0
    for x, y in pts:
        sx = round(x / module) * module
        sy = round(y / module) * module
        if abs(x - sx) < 0.05 and abs(y - sy) < 0.05:
            on += 1
    return 100.0 * on / len(pts)


def _room_touches(room, edge: str, minx: float, miny: float, maxx: float, maxy: float) -> bool:
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


def _hierarchy_points(candidate: LayoutCandidate) -> tuple[float, float]:
    best_edge = (candidate.zones.get("__best_edge") or ["south"])[0]
    second_edge = (candidate.zones.get("__second_edge") or ["west"])[0]

    minx = min(p[0] for r in candidate.rooms for p in r.polygon)
    miny = min(p[1] for r in candidate.rooms for p in r.polygon)
    maxx = max(p[0] for r in candidate.rooms for p in r.polygon)
    maxy = max(p[1] for r in candidate.rooms for p in r.polygon)

    tier1 = [r for r in candidate.rooms if r.type in {"living", "reception"}]
    tier4 = [r for r in candidate.rooms if r.type in {"bathroom", "ensuite", "storage", "laundry", "server_room"}]

    points = 0.0
    if tier1 and any(_room_touches(r, best_edge, minx, miny, maxx, maxy) for r in tier1):
        points += 10.0

    bad_tier4 = [
        r
        for r in tier4
        if _room_touches(r, best_edge, minx, miny, maxx, maxy) or _room_touches(r, second_edge, minx, miny, maxx, maxy)
    ]
    if not bad_tier4:
        points += 10.0

    return points, points * 5.0


def _circulation_points(candidate: LayoutCandidate) -> tuple[float, float]:
    total_area = sum(r.area_sqm for r in candidate.rooms)
    corridor_area = sum(r.area_sqm for r in candidate.rooms if r.type == "corridor")

    points = 0.0
    ratio = (corridor_area / total_area) if total_area > 0 else 0.0
    if ratio <= 0.10:
        points += 10.0
    else:
        points += max(0.0, 10.0 * (1.0 - (ratio - 0.10) / 0.10))

    if not candidate.circulation:
        points += 5.0
    elif all(e.length_m <= 6.0 for e in candidate.circulation):
        points += 5.0
    elif all(e.length_m <= 8.0 for e in candidate.circulation):
        points += 2.5

    degree: dict[str, int] = defaultdict(int)
    for e in candidate.circulation:
        degree[e.from_room] += 1
        degree[e.to_room] += 1
    dead_end_nodes = [rid for rid, d in degree.items() if d == 1 and not rid.startswith("entry") and not rid.startswith("reception")]
    if not dead_end_nodes:
        points += 5.0
    elif len(dead_end_nodes) <= 2:
        points += 2.5

    return min(20.0, points), min(100.0, points * 5.0)


def _proportion_points(candidate: LayoutCandidate, total_area: float) -> tuple[float, float]:
    points = 0.0

    aspect_pass = 0
    for r in candidate.rooms:
        mn = min(r.width_m, r.depth_m)
        mx = max(r.width_m, r.depth_m)
        if mn > 0 and mx / mn <= 2.0:
            aspect_pass += 1
    if candidate.rooms:
        points += 10.0 * (aspect_pass / len(candidate.rooms))

    below_min = 0
    master_id = None
    bedrooms = [r for r in candidate.rooms if r.type == "bedroom"]
    if bedrooms:
        master_id = max(bedrooms, key=lambda x: x.area_sqm).id

    for r in candidate.rooms:
        min_w, min_h = room_min_dims(r.type, r.area_sqm, total_area, is_master=(r.id == master_id))
        if r.width_m + 0.15 < min_w or r.depth_m + 0.15 < min_h:
            below_min += 1

    if candidate.rooms:
        points += 10.0 * ((len(candidate.rooms) - below_min) / len(candidate.rooms))

    return min(20.0, points), min(100.0, points * 5.0)


def _share_wall(a, b) -> bool:
    pa = Polygon(a.polygon)
    pb = Polygon(b.polygon)
    shared = pa.boundary.intersection(pb.boundary)
    return not shared.is_empty and shared.length > 0.4


def _adjacency_points(candidate: LayoutCandidate) -> tuple[float, float]:
    points = 0.0

    by_type: dict[str, list] = defaultdict(list)
    for r in candidate.rooms:
        by_type[r.type].append(r)

    doors = candidate.openings.get("doors", [])

    kitchens = by_type.get("kitchen", [])
    livings = by_type.get("living", []) + by_type.get("dining", [])
    kitchen_connected = False
    if kitchens and livings:
        if any(_share_wall(k, l) for k in kitchens for l in livings):
            kitchen_connected = True
        else:
            kitchen_ids = {r.id for r in kitchens}
            living_ids = {r.id for r in livings}
            kitchen_connected = any(
                (d["room_a"] in kitchen_ids and d["room_b"] in living_ids) or (d["room_b"] in kitchen_ids and d["room_a"] in living_ids)
                for d in doors
            )
    if kitchen_connected:
        points += 10.0

    corridor_ids = {r.id for r in by_type.get("corridor", [])}
    bedrooms = by_type.get("bedroom", [])
    if bedrooms:
        linked = 0
        for b in bedrooms:
            ok = any((e.from_room == b.id and e.to_room in corridor_ids) or (e.to_room == b.id and e.from_room in corridor_ids) for e in candidate.circulation)
            if ok:
                linked += 1
        points += 5.0 * (linked / len(bedrooms))

    baths = by_type.get("bathroom", []) + by_type.get("ensuite", [])
    if len(baths) <= 1:
        points += 5.0
    else:
        grouped_pairs = sum(1 for i, a in enumerate(baths) for b in baths[i + 1 :] if _share_wall(a, b))
        total_pairs = max(1, len(baths) * (len(baths) - 1) // 2)
        points += 5.0 * (grouped_pairs / total_pairs)

    return min(20.0, points), min(100.0, points * 5.0)


def lowest_scoring_category(score: ScoreBreakdown) -> str:
    categories = {
        "grid_alignment": score.grid_alignment_score / 5.0,
        "hierarchy": score.hierarchy_score / 5.0,
        "circulation": score.circulation_composition_score / 5.0,
        "proportion": score.spatial_sequence_score / 5.0,
        "adjacency": score.adjacency_quality,
    }
    return min(categories, key=categories.get)


def score_candidate(candidate: LayoutCandidate, program: ProgramOutput, furniture_score: float) -> ScoreBreakdown:
    total_area = sum(r.area_sqm for r in candidate.rooms)

    grid_percent = _grid_alignment_percent(candidate)
    grid_points = min(20.0, grid_percent * 0.2)
    hierarchy_points, hierarchy_percent = _hierarchy_points(candidate)
    circulation_points, circulation_percent = _circulation_points(candidate)
    proportion_points, proportion_percent = _proportion_points(candidate, total_area)
    adjacency_points, adjacency_percent = _adjacency_points(candidate)

    total_score = grid_points + hierarchy_points + circulation_points + proportion_points + adjacency_points

    area_accuracy = max(0.0, 1.0 - abs(total_area - program.target_area_sqm) / max(program.target_area_sqm, 1.0))
    circulation_eff = circulation_points / 20.0
    daylight = min(1.0, sum(1 for w in candidate.openings.get("windows", []) if w.get("room_id")) / max(1, len(candidate.rooms)))

    explanation = (
        "Weighted score (20 each): grid alignment, hierarchy, circulation, proportion, adjacency. "
        f"Lowest category: {min({'grid_alignment': grid_points, 'hierarchy': hierarchy_points, 'circulation': circulation_points, 'proportion': proportion_points, 'adjacency': adjacency_points}, key=lambda k: {'grid_alignment': grid_points, 'hierarchy': hierarchy_points, 'circulation': circulation_points, 'proportion': proportion_points, 'adjacency': adjacency_points}[k])}."
    )

    return ScoreBreakdown(
        area_accuracy=round(area_accuracy, 3),
        adjacency_quality=round(adjacency_points, 2),
        zoning_quality=round(hierarchy_points / 20.0, 3),
        privacy=round(hierarchy_points / 20.0, 3),
        circulation_efficiency=round(circulation_eff, 3),
        daylight_potential=round(daylight, 3),
        furniture_usability=round(furniture_score, 3),
        compactness=round(proportion_points / 20.0, 3),
        wall_efficiency=round(grid_points / 20.0, 3),
        total=round(total_score, 2),
        explanation=explanation,
        grid_alignment_score=round(grid_percent, 2),
        hierarchy_score=round(hierarchy_percent, 2),
        circulation_composition_score=round(circulation_percent, 2),
        spatial_sequence_score=round(proportion_percent, 2),
    )
