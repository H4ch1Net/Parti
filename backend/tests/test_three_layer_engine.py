from collections import defaultdict, deque

from app.services.brief_interpreter import interpret_brief
from app.services.graph_placer import room_min_dims
from app.services.parti_selector import Parti, ProgramBrief, select_parti
from app.services.planner_pipeline import generate_from_prompt


PARTI_CASES = [
    ("studio apartment 400 sqft", Parti.OPEN_BAR),
    ("800 sqft, 2 bedrooms, kitchen, bathroom", Parti.SPLIT_ZONE),
    ("3 bedroom 2 bathroom house 1200 sqft", Parti.LINEAR_BAR),
    ("4 bedroom 3 bathroom house 2000 sqft", Parti.DOUBLE_LOADED),
    ("small office 600 sqft, reception, 3 private offices, bathroom", Parti.CENTRAL_CORE),
]


def _best(prompt: str):
    result = generate_from_prompt(prompt)
    return next(c for c in result.candidates if c.id == result.best_candidate_id)


def _touches(room, edge: str, minx: float, miny: float, maxx: float, maxy: float) -> bool:
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


def test_parti_selection():
    for prompt, expected in PARTI_CASES:
        brief = interpret_brief(prompt)
        parti = select_parti(ProgramBrief.from_structured(brief))
        assert parti.parti == expected, (prompt, parti.parti, expected)


def test_graph_connectivity():
    for prompt, _ in PARTI_CASES:
        best = _best(prompt)
        graph: dict[str, set[str]] = defaultdict(set)
        for edge in best.circulation:
            graph[edge.from_room].add(edge.to_room)
            graph[edge.to_room].add(edge.from_room)
        for d in best.openings.get("doors", []):
            a, b = d["room_a"], d["room_b"]
            if a != "exterior" and b != "exterior":
                graph[a].add(b)
                graph[b].add(a)

        start = next((r.id for r in best.rooms if r.type in {"entry", "reception", "living"}), best.rooms[0].id)
        seen = {start}
        q = deque([start])
        while q:
            cur = q.popleft()
            for nxt in graph.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)

        assert all(r.id in seen for r in best.rooms), prompt


def test_tier_placement():
    best = _best("800 sqft, 2 bedrooms, kitchen, bathroom")
    best_edge = (best.zones.get("__best_edge") or ["south"])[0]
    second_edge = (best.zones.get("__second_edge") or ["west"])[0]

    minx = min(p[0] for r in best.rooms for p in r.polygon)
    miny = min(p[1] for r in best.rooms for p in r.polygon)
    maxx = max(p[0] for r in best.rooms for p in r.polygon)
    maxy = max(p[1] for r in best.rooms for p in r.polygon)

    tier1 = [r for r in best.rooms if r.type in {"living", "reception"}]
    assert tier1
    assert any(_touches(r, best_edge, minx, miny, maxx, maxy) for r in tier1)

    baths = [r for r in best.rooms if r.type in {"bathroom", "ensuite"}]
    assert all(not _touches(r, best_edge, minx, miny, maxx, maxy) for r in baths)
    assert all(not _touches(r, second_edge, minx, miny, maxx, maxy) for r in baths)


def test_grid_alignment():
    for prompt, _ in PARTI_CASES:
        best = _best(prompt)
        module_mm = int((best.zones.get("__grid_module_mm") or ["1200"])[0])
        module = module_mm / 1000.0
        pts = [pt for w in best.walls for pt in w.segment]
        on = 0
        for x, y in pts:
            sx = round(x / module) * module
            sy = round(y / module) * module
            if abs(x - sx) < 0.05 and abs(y - sy) < 0.05:
                on += 1
        alignment = 100.0 * on / max(1, len(pts))
        assert alignment >= 95.0, (prompt, alignment)


def test_corridor_budget():
    for prompt, _ in PARTI_CASES:
        best = _best(prompt)
        total = sum(r.area_sqm for r in best.rooms)
        corridor = sum(r.area_sqm for r in best.rooms if r.type == "corridor")
        if total > 0:
            assert corridor / total <= 0.10 + 1e-6, (prompt, corridor / total)


def test_minimum_dimensions():
    for prompt, _ in PARTI_CASES:
        best = _best(prompt)
        total = sum(r.area_sqm for r in best.rooms)
        bedrooms = [r for r in best.rooms if r.type == "bedroom"]
        master_id = max(bedrooms, key=lambda x: x.area_sqm).id if bedrooms else None

        for r in best.rooms:
            min_w, min_h = room_min_dims(r.type, r.area_sqm, total, is_master=(r.id == master_id))
            assert r.width_m + 1e-6 >= min_w, (prompt, r.id, r.width_m, min_w)
            assert r.depth_m + 1e-6 >= min_h, (prompt, r.id, r.depth_m, min_h)
