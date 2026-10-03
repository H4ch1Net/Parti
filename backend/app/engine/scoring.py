"""Plan scoring.

Seven categories, each 0-100, combined by weight. Every category carries a
one-line explanation so the UI can say why a plan scored the way it did.
"""

from __future__ import annotations

from app.core.geometry import shared_edge
from app.engine.furniture import REQUIRED
from app.engine.rooms import SPECS, min_side
from app.engine.validation import fixture_kinds, parents, reachable_rooms, room_box
from app.engine.windows import glazing_ratio
from app.models.schemas import Candidate, Preferences, Program, Score, ScoreCategory

PUBLIC_ROOMS = {"living", "dining", "kitchen", "studio"}
GOOD_PARENTS = {"corridor", "entry", "stair", "reception"}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _area(c: Candidate, target: float) -> tuple[float, str]:
    total = c.total_area_sqm
    dev = (total - target) / max(target, 1.0)
    total_score = max(0.0, 1.0 - abs(dev) / 0.2)
    fits = []
    for r in c.rooms:
        if r.type in {"corridor", "stair"} or r.target_area_sqm <= 0:
            continue
        fits.append(max(0.0, 1.0 - abs(r.area_sqm - r.target_area_sqm) / r.target_area_sqm / 0.6))
    room_score = sum(fits) / len(fits) if fits else 1.0
    return _clamp(100 * (0.5 * total_score + 0.5 * room_score)), f"{total:.1f} m² against a {target:.1f} m² target ({dev * 100:+.1f}%)"


def _proportion(c: Candidate) -> tuple[float, str]:
    weighted = 0.0
    weights = 0.0
    narrow = []
    for r in c.rooms:
        if r.type in {"corridor", "stair"}:
            continue
        b = room_box(r)
        a = b.aspect
        s = 1.0 if a <= 1.6 else 1.0 - 0.4 * (a - 1.6) / 0.9 if a <= 2.5 else max(0.0, 0.6 - 0.6 * (a - 2.5))
        if b.short + 0.01 < min_side(r.type, r.primary):
            s = min(s, 0.2)
        if a > 2.5:
            narrow.append(r.name)
        weighted += s * r.area_sqm
        weights += r.area_sqm
    score = 100 * weighted / max(weights, 1e-6)
    detail = "Every room is within 1:2.5" if not narrow else f"Elongated: {', '.join(narrow)}"
    return _clamp(score), detail


def _daylight(c: Candidate) -> tuple[float, str]:
    habitable = [r for r in c.rooms if SPECS[r.type].habitable]
    if not habitable:
        return 100.0, "No rooms need daylight"
    by_room: dict[str, list] = {}
    for w in c.windows:
        by_room.setdefault(w.room_id, []).append(w)
    ok = 0
    total = 0.0
    for r in habitable:
        ratio = glazing_ratio(r.area_sqm, by_room.get(r.id, []))
        total += min(1.0, ratio / 0.10)
        ok += ratio >= 0.10
    return _clamp(100 * total / len(habitable)), f"{ok} of {len(habitable)} habitable rooms reach 10% glazing"


def _circulation(c: Candidate) -> tuple[float, str]:
    total = c.total_area_sqm
    hall = sum(r.area_sqm for r in c.rooms if r.type == "corridor")
    share = hall / max(total, 1e-6)
    share_score = 1.0 if share <= 0.10 else max(0.3, 1.0 - (share - 0.10) / 0.10 * 0.7)
    reach = reachable_rooms(c)
    reach_score = len(reach & {r.id for r in c.rooms}) / max(len(c.rooms), 1)
    entered = parents(c)
    by_id = {r.id: r for r in c.rooms}
    leaves = [r for r in c.rooms if not SPECS[r.type].serves]
    direct = 0.0
    for r in leaves:
        src = by_id.get(entered.get(r.id, ""))
        if src is None:
            continue
        if (
            src.type in GOOD_PARENTS
            or (r.type == "ensuite" and src.type == "bedroom")
            or r.type in {"laundry", "storage"}
            and src.type in {"kitchen", "garage"}
        ):
            direct += 1.0
        elif src.type in PUBLIC_ROOMS | {"open_office"}:
            direct += 0.5
    direct_score = direct / len(leaves) if leaves else 1.0
    score = 100 * (0.35 * share_score + 0.35 * direct_score + 0.30 * reach_score)
    detail = f"Halls are {share:.0%} of the floor area"
    if leaves:
        detail += f"; {direct_score:.0%} of enclosed rooms open off circulation"
    return _clamp(score), detail


def _privacy(c: Candidate) -> tuple[float, str]:
    entered = parents(c)
    by_id = {r.id: r for r in c.rooms}
    private = [r for r in c.rooms if r.type in {"bedroom", "bathroom", "ensuite", "private_office"}]
    if not private:
        return 100.0, "No private rooms in the program"
    total = 0.0
    exposed = []
    for r in private:
        src = by_id.get(entered.get(r.id, ""))
        if src is None:
            continue
        if src.type in PUBLIC_ROOMS or src.type in {"reception", "open_office"} and r.type != "bathroom":
            total += 0.3
            exposed.append(r.name)
        else:
            total += 1.0
    score = 100 * total / len(private)
    detail = "Private rooms open off halls or their own suite" if not exposed else f"Opens off a living space: {', '.join(exposed)}"
    return _clamp(score), detail


def _adjacency(c: Candidate, program: Program) -> tuple[float, str]:
    if not program.adjacency:
        return 100.0, "No adjacency preferences"
    boxes = {r.id: room_box(r) for r in c.rooms}
    floors = {r.id: r.floor for r in c.rooms}
    linked = {frozenset((x.from_room, x.to_room)) for x in c.connections}
    got = 0.0
    want = 0.0
    for pref in program.adjacency:
        if pref.a not in boxes or pref.b not in boxes:
            continue
        want += pref.weight
        if frozenset((pref.a, pref.b)) in linked:
            got += pref.weight
        elif floors[pref.a] == floors[pref.b]:
            seg = shared_edge(boxes[pref.a], boxes[pref.b])
            if seg is not None and seg.length >= 0.8:
                got += pref.weight * 0.7
    ratio = got / want if want else 1.0
    return _clamp(100 * ratio), f"{ratio:.0%} of preferred room relationships are met"


def _furniture(c: Candidate) -> tuple[float, str]:
    kinds = fixture_kinds(c)
    need = 0
    have = 0
    for r in c.rooms:
        req = REQUIRED.get(r.type, [])
        need += len(req)
        have += sum(1 for k in req if k in kinds[r.id])
    if need == 0:
        return 100.0, "No furniture requirements"
    if not c.fixtures:
        return 70.0, "Furniture not evaluated"
    return _clamp(100 * have / need), f"{have} of {need} essential furniture items fit"


def score_candidate(c: Candidate, program: Program, prefs: Preferences | None = None) -> Score:
    prefs = prefs or Preferences()
    parts = [
        ("area", "Area fit", 15.0, _area(c, program.target_area_sqm)),
        ("proportion", "Proportions", 15.0, _proportion(c)),
        ("daylight", "Daylight", 20.0 if prefs.daylight else 14.0, _daylight(c)),
        ("circulation", "Circulation", 20.0 if prefs.compact else 16.0, _circulation(c)),
        ("privacy", "Privacy", 16.0 if prefs.privacy else 10.0, _privacy(c)),
        ("adjacency", "Adjacency", 15.0, _adjacency(c, program)),
        ("furniture", "Furnishability", 15.0, _furniture(c)),
    ]
    categories = [ScoreCategory(key=k, label=label, score=round(s, 1), weight=w, detail=detail) for k, label, w, (s, detail) in parts]
    total = sum(x.score * x.weight for x in categories) / sum(x.weight for x in categories)
    if not c.validation.valid:
        total = min(total, 55.0)
    grade = "excellent" if total >= 85 else "good" if total >= 72 else "fair" if total >= 58 else "weak"
    ranked = sorted(categories, key=lambda x: x.score)
    summary = (
        f"Strongest: {ranked[-1].label.lower()}. Weakest: {ranked[0].label.lower()} ({ranked[0].detail[0].lower() + ranked[0].detail[1:]})."
    )
    return Score(total=round(total, 1), grade=grade, categories=categories, summary=summary)  # type: ignore[arg-type]
