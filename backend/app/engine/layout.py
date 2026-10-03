"""Layout engine: room program -> rectangular plan.

Plans are slicing trees. A ``Split`` divides its rectangle along one axis and
hands the pieces to its children; a ``Leaf`` is a room. Because every split
partitions its rectangle exactly (in integer grid units), the rooms always
tile the footprint with no overlaps and no voids.

Templates describe the tree shape for a plan type (a split plan with a hall
between a public front and a private back, or a wing plan with the private
rooms on a double-loaded hall). The search enumerates template variants,
room orders and footprint proportions, and the pipeline keeps the best
scoring results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations, permutations

from app.core.geometry import Box, r3, shared_edge
from app.engine.program import ADJACENCY
from app.engine.rooms import SPECS, min_side
from app.models.schemas import Program, ProgramRoom

GRID = 0.3  # planning grid in metres; every wall lands on it
HALL_UNITS = 4  # 1.2 m clear hall
WIDE_HALL_UNITS = 5  # 1.5 m for larger commercial floors
STAIR_UNITS = 4  # 1.2 m wide straight-run stair
ASPECTS = (0.9, 1.15, 1.4, 1.7, 2.05)


# ------------------------------------------------------------ tree types ----


@dataclass
class Leaf:
    room: ProgramRoom
    fixed: int | None = None  # fixed size in grid units along the parent split axis


@dataclass
class Split:
    axis: str  # "x": children left -> right, "y": children front -> back
    children: list[Leaf | Split]
    fixed: int | None = None


Node = Leaf | Split


@dataclass
class PlacedRoom:
    room: ProgramRoom
    box: Box


@dataclass
class Layout:
    strategy: str
    key: tuple
    width: float
    depth: float
    rooms: list[PlacedRoom]
    feasible: bool = True
    notes: list[str] = field(default_factory=list)

    def floor(self, level: int) -> list[PlacedRoom]:
        return [p for p in self.rooms if p.room.floor == level]


# ---------------------------------------------------------------- solver ----


class _Ctx:
    def __init__(self) -> None:
        self.feasible = True


def _weight(node: Node) -> float:
    if isinstance(node, Leaf):
        return max(node.room.target_area_sqm, 0.5)
    return sum(_weight(c) for c in node.children)


GARAGE_DEPTH_UNITS = 18  # 5.4 m: a car parked nose-in plus a walkway


def _leaf_min(room: ProgramRoom, cross: int | None, axis: str) -> int:
    spec = SPECS[room.type]
    units = math.ceil(min_side(room.type, room.primary) / GRID - 1e-9)
    if room.type == "garage" and axis == "y":
        units = max(units, GARAGE_DEPTH_UNITS)
    if cross:
        limit = min(spec.max_aspect, 2.4)
        units = max(units, math.ceil(cross / limit - 1e-9))
        units = max(units, math.ceil(room.min_area_sqm / (cross * GRID * GRID) - 1e-9))
    return units


def _min_units(node: Node, axis: str, cross: int | None) -> int:
    if node.fixed is not None and isinstance(node, Leaf):
        return node.fixed
    if isinstance(node, Leaf):
        return _leaf_min(node.room, cross, axis)
    if node.axis == axis:
        return sum(c.fixed if c.fixed is not None else _min_units(c, axis, cross) for c in node.children)
    return max(_min_units(c, axis, None) for c in node.children)


def _allocate(children: list[Node], total: int, axis: str, cross: int, ctx: _Ctx) -> list[int]:
    sizes = [0] * len(children)
    flex = []
    rem = total
    for i, c in enumerate(children):
        if c.fixed is not None:
            sizes[i] = c.fixed
            rem -= c.fixed
        else:
            flex.append(i)
    if not flex:
        if rem != 0:
            ctx.feasible = False
            sizes[-1] += rem
        return sizes

    mins = {i: _min_units(children[i], axis, cross) for i in flex}
    weights = {i: _weight(children[i]) for i in flex}
    if sum(mins.values()) > rem:
        ctx.feasible = False
        # Shrink the largest minimums until the pieces fit.
        while sum(mins.values()) > rem and max(mins.values()) > 1:
            j = max(mins, key=mins.get)  # type: ignore[arg-type]
            mins[j] -= 1

    pinned: dict[int, float] = {}
    active = set(flex)
    while active:
        budget = rem - sum(pinned.values())
        wsum = sum(weights[i] for i in active)
        ideal = {i: budget * weights[i] / wsum for i in active}
        low = [i for i in active if ideal[i] < mins[i]]
        if not low:
            pinned.update(ideal)
            break
        for i in low:
            pinned[i] = mins[i]
            active.discard(i)

    base = {i: max(mins[i], math.floor(pinned[i] + 1e-9)) for i in flex}
    left = rem - sum(base.values())
    order = sorted(flex, key=lambda i: pinned[i] - math.floor(pinned[i] + 1e-9), reverse=True)
    k = 0
    while left > 0:
        base[order[k % len(order)]] += 1
        left -= 1
        k += 1
    while left < 0:
        cand = [i for i in flex if base[i] > mins[i]] or flex
        j = max(cand, key=lambda i: base[i] - pinned[i])
        base[j] -= 1
        left += 1
    for i in flex:
        sizes[i] = base[i]
    return sizes


def _place(node: Node, x: int, y: int, w: int, h: int, out: list[tuple[ProgramRoom, int, int, int, int]], ctx: _Ctx) -> None:
    if isinstance(node, Leaf):
        out.append((node.room, x, y, w, h))
        return
    if node.axis == "x":
        sizes = _allocate(node.children, w, "x", h, ctx)
        cx = x
        for c, s in zip(node.children, sizes):
            _place(c, cx, y, s, h, out, ctx)
            cx += s
    else:
        sizes = _allocate(node.children, h, "y", w, ctx)
        cy = y
        for c, s in zip(node.children, sizes):
            _place(c, x, cy, w, s, out, ctx)
            cy += s


def solve(tree: Node, w_units: int, d_units: int) -> tuple[list[PlacedRoom], bool]:
    ctx = _Ctx()
    raw: list[tuple[ProgramRoom, int, int, int, int]] = []
    _place(tree, 0, 0, w_units, d_units, raw, ctx)
    placed = []
    for room, x, y, w, h in raw:
        if w <= 0 or h <= 0:
            ctx.feasible = False
            w, h = max(w, 1), max(h, 1)
        placed.append(PlacedRoom(room, Box(r3(x * GRID), r3(y * GRID), r3(w * GRID), r3(h * GRID))))
    return placed, ctx.feasible


# ------------------------------------------------------------- orderings ----


def _pair_weight(a: ProgramRoom, b: ProgramRoom) -> float:
    if {a.type, b.type} == {"bedroom", "ensuite"}:
        return 3.0 if (a.primary or b.primary) else -1.0
    w = ADJACENCY.get(frozenset({a.type, b.type}), 0.0)
    if SPECS[a.type].wet and SPECS[b.type].wet:
        w += 0.4  # shared plumbing wall
    if {a.type, b.type} & {"garage"} and {a.type, b.type} & {"bedroom", "living"}:
        w -= 0.8
    return w


def _order_score(seq: tuple[ProgramRoom, ...], role: str, start_bias: bool, ends: tuple) -> float:
    s = 0.0
    full = [ends[0], *seq, ends[1]]
    for a, b in zip(full, full[1:]):
        if a is not None and b is not None:
            s += 3.0 * _pair_weight(a, b)
    n = len(seq)
    for i, r in enumerate(seq):
        at_end = i in (0, n - 1)
        if r.type in {"entry", "reception"}:
            s += 2.0 if at_end else 0.0
            if start_bias and i == 0:
                s += 3.0
        if r.type == "garage" and at_end:
            s += 4.0
        if r.type == "kitchen" and at_end:
            s += 0.5
        if role == "back" and r.primary and at_end:
            s += 1.0
    return s


def orderings(
    rooms: list[ProgramRoom], role: str, k: int = 3, start_bias: bool = False, ends: tuple = (None, None)
) -> list[list[ProgramRoom]]:
    if len(rooms) <= 1:
        return [list(rooms)]
    if len(rooms) > 7:
        grouped = sorted(rooms, key=lambda r: (list(SPECS).index(r.type), r.id))
        return [grouped, grouped[::-1]]
    scored: dict[tuple[str, ...], tuple[float, tuple[ProgramRoom, ...]]] = {}
    for perm in permutations(rooms):
        sig = tuple(r.type + ("*" if r.primary else "") for r in perm)
        sc = _order_score(perm, role, start_bias, ends)
        if sig not in scored or sc > scored[sig][0]:
            scored[sig] = (sc, perm)
    best = sorted(scored.values(), key=lambda t: t[0], reverse=True)[:k]
    return [list(p) for _, p in best]


# --------------------------------------------------------------- stacking ----

# Small rooms can share one column of a band: the piece that needs an
# outside wall (entry, ensuite, laundry) sits on the facade side and the
# piece reached from the hall sits on the hall side.
EXT_PIECES = {"entry", "ensuite", "laundry"}
HALL_PIECES = {"powder", "storage", "bathroom", "laundry"}
STACK_MAX_AREA = 7.5

Item = ProgramRoom | tuple[ProgramRoom, ProgramRoom]  # room, or (facade piece, hall piece)


def _stackable(a: ProgramRoom, b: ProgramRoom) -> tuple[ProgramRoom, ProgramRoom] | None:
    for ext, hal in ((a, b), (b, a)):
        if ext.type not in EXT_PIECES or hal.type not in HALL_PIECES or ext.type == hal.type:
            continue
        if max(ext.target_area_sqm, hal.target_area_sqm) > STACK_MAX_AREA:
            continue
        if ext.type == "ensuite" and hal.type not in {"bathroom", "powder"}:
            continue
        return ext, hal
    return None


def _stack_adjacent(order: list[ProgramRoom]) -> list[Item]:
    items: list[Item] = []
    i = 0
    while i < len(order):
        pair = _stackable(order[i], order[i + 1]) if i + 1 < len(order) else None
        if pair:
            items.append(pair)
            i += 2
        else:
            items.append(order[i])
            i += 1
    return items


def stack_variants(order: list[ProgramRoom]) -> list[list[Item]]:
    """The order as is, with adjacent small rooms stacked, and with stackable
    partners pulled together so they can share a column."""
    out: list[list[Item]] = [list(order)]
    seen = {_sig(out[0])}
    candidates = [_stack_adjacent(order)]
    for i, a in enumerate(order):
        for j, b in enumerate(order):
            if abs(i - j) > 1 and _stackable(a, b):
                moved = [r for r in order if r is not b]
                moved.insert(moved.index(a) + 1, b)
                candidates.append(_stack_adjacent(moved))
    for items in candidates:
        sig = _sig(items)
        if sig not in seen and len(items) < len(order):
            seen.add(sig)
            out.append(items)
    return out[:3]


def _flat(items: list[Item]) -> list[ProgramRoom]:
    out: list[ProgramRoom] = []
    for it in items:
        out.extend(it if isinstance(it, tuple) else (it,))
    return out


def _sig(items: list[Item]) -> tuple:
    return tuple(tuple(r.id for r in it) if isinstance(it, tuple) else it.id for it in items)


def _row(items: list[Item], hall_side: str, fixed: int | None = None) -> Split:
    kids: list[Node] = []
    for it in items:
        if isinstance(it, tuple):
            ext, hal = it
            kids.append(Split("y", [Leaf(ext), Leaf(hal)] if hall_side == "back" else [Leaf(hal), Leaf(ext)]))
        else:
            kids.append(Leaf(it))
    return Split("x", kids, fixed=fixed)


# -------------------------------------------------------------- templates ----


FRONT_PINNED = {"entry", "reception", "garage", "living", "studio"}
FRONT_DEFAULT = {"dining", "kitchen", "open_office", "meeting_room", "powder"}
UPPER_MOVABLE = {"bedroom", "study", "storage", "laundry", "bathroom", "private_office"}


def _band_assignments(rooms: list[ProgramRoom]) -> list[tuple[list[ProgramRoom], list[ProgramRoom]]]:
    """Possible splits of an entry level into a street-side front and a private back."""
    rooms = [r for r in rooms if r.type not in {"corridor", "stair"}]
    front = [r for r in rooms if r.type in FRONT_PINNED or r.type in FRONT_DEFAULT]
    back = [r for r in rooms if r not in front]
    if not back:
        movable = [r for r in front if r.type not in {"entry", "reception", "living", "studio", "garage"}]
        options = [([r for r in front if r is not m], [m]) for m in movable]
        if len(movable) >= 2:
            options.append(([r for r in front if r not in movable[:2]], movable[:2]))
        if not options:
            mains = [r for r in front if r.type in {"living", "studio", "reception", "open_office"}]
            if mains and len(front) > 1:
                options.append(([r for r in front if r is not mains[0]], [mains[0]]))
        return _dedupe_assignments(options or [(front, back)])

    options = [(front, back)]
    flexible = [r for r in rooms if SPECS[r.type].band == "either" or (r.type == "bedroom" and not r.primary)]
    for r in flexible:
        if r in front:
            options.append(([x for x in front if x is not r], back + [r]))
        else:
            options.append((front + [r], [x for x in back if x is not r]))
    for i, a in enumerate(flexible):
        for b in flexible[i + 1 :]:
            if a in back and b in back:
                options.append((front + [a, b], [x for x in back if x is not a and x is not b]))
    return _dedupe_assignments(options)


def _upper_assignments(rooms: list[ProgramRoom]) -> list[tuple[list[ProgramRoom], list[ProgramRoom]]]:
    """Splits of a private upper level: some rooms face the front, the rest the back."""
    rooms = [r for r in rooms if r.type not in {"corridor", "stair"}]
    movable = [r for r in rooms if r.type in UPPER_MOVABLE and not r.primary]
    options = []
    for k in range(1, min(3, len(movable)) + 1):
        for combo in combinations(movable, k):
            if not any(r.type in {"bedroom", "study", "private_office"} for r in combo):
                continue
            options.append((list(combo), [r for r in rooms if r not in combo]))
    if not options and rooms:
        options = [([rooms[0]], rooms[1:])]
    return _dedupe_assignments(options)


def _dedupe_assignments(options):
    seen = set()
    out = []
    for f, b in options:
        sig = (tuple(sorted(r.id for r in f)), tuple(sorted(r.id for r in b)))
        if sig in seen or not f:
            continue
        seen.add(sig)
        out.append((f, b))
    return out


def _balance_penalty(front: list[ProgramRoom], back: list[ProgramRoom]) -> float:
    af = sum(r.target_area_sqm for r in front)
    ab = sum(r.target_area_sqm for r in back)
    if ab <= 0:
        return 10.0
    return abs(math.log(max(af, 1) / max(ab, 1)))


def _end_choices(back: list[ProgramRoom], has_hall: bool, stair: ProgramRoom | None):
    """(end_l, end_r, mode) options: rooms that span the full back depth at either end."""
    big = sorted(
        [r for r in back if r.type in {"bedroom", "private_office", "meeting_room", "study", "open_office"}],
        key=lambda r: (not r.primary, -r.target_area_sqm),
    )
    out = []
    if stair is not None:
        out.append((stair, None, "stair"))
        if has_hall and big:
            out.append((stair, big[0], "stair+end"))
        return out
    out.append((None, None, "full"))
    if big:
        out.append((None, big[0], "end"))
        if has_hall and len(big) >= 2:
            out.append((big[1], big[0], "both"))
    return out


def _band_tree(
    front: list[Item],
    middle: list[Item],
    end_l: ProgramRoom | None,
    end_r: ProgramRoom | None,
    hall: ProgramRoom | None,
    hall_units: int,
    front_fixed: int | None = None,
) -> Split | None:
    back_children: list[Node] = []
    if end_l is not None:
        back_children.append(Leaf(end_l, fixed=STAIR_UNITS if end_l.type == "stair" else None))
    if hall is not None:
        if not middle:
            return None
        back_children.append(Split("y", [Leaf(hall, fixed=hall_units), _row(middle, "front")]))
    else:
        back_children.extend(_row(middle, "front").children)
    if end_r is not None:
        back_children.append(Leaf(end_r))
    if not back_children or not front:
        return None
    return Split("y", [_row(front, "back", fixed=front_fixed), Split("x", back_children)])


def _footprints(area: float) -> list[tuple[int, int]]:
    out = []
    seen = set()
    for a in ASPECTS:
        w = max(3, round(math.sqrt(area * a) / GRID))
        d = max(3, round(area / (w * GRID) / GRID))
        if (w, d) not in seen:
            seen.add((w, d))
            out.append((w, d))
    return out


# ---------------------------------------------------------------- search ----


def _quick_penalty(placed: list[PlacedRoom], width: float, depth: float) -> float:
    """Cheap proxy for plan quality, used to prune the search before scoring."""
    pen = 0.0
    serving = [p for p in placed if SPECS[p.room.type].serves]
    for p in placed:
        spec = SPECS[p.room.type]
        b = p.box
        pen += max(0.0, b.aspect - min(spec.max_aspect, 2.5)) * 10
        pen += max(0.0, min_side(p.room.type, p.room.primary) - b.short) * 20
        if p.room.target_area_sqm > 0 and p.room.type != "corridor":
            pen += abs(b.area - p.room.target_area_sqm) / p.room.target_area_sqm
        if spec.habitable and not (b.x < 1e-4 or b.y < 1e-4 or abs(b.x1 - width) < 1e-4 or abs(b.y1 - depth) < 1e-4):
            pen += 30
        if not spec.serves and p.room.type not in {"ensuite", "garage"}:
            touching = False
            for s in serving:
                if s.room.floor != p.room.floor:
                    continue
                seg = shared_edge(b, s.box)
                if seg is not None and seg.length >= 1.0:
                    touching = True
                    break
            if not touching:
                pen += 15
    return pen


class _Collector:
    """Keeps the best layouts per structural key so the search stays bounded."""

    def __init__(self, per_key: int = 3) -> None:
        self.per_key = per_key
        self.by_key: dict[tuple, list[tuple[float, Layout]]] = {}

    def add(self, layout: Layout) -> None:
        pen = _quick_penalty(layout.rooms, layout.width, layout.depth) + (0 if layout.feasible else 25)
        bucket = self.by_key.setdefault(layout.key, [])
        bucket.append((pen, layout))
        bucket.sort(key=lambda t: t[0])
        del bucket[self.per_key :]

    def best(self, limit: int) -> list[Layout]:
        flat = sorted((t for b in self.by_key.values() for t in b), key=lambda t: t[0])
        return [lay for _, lay in flat[:limit]]


def layout_candidates(program: Program, building_type: str, limit: int = 160) -> list[Layout]:
    """Enumerate plausible layouts, best first by a cheap pre-score."""
    total = sum(r.target_area_sqm for r in program.rooms)
    hall_units = WIDE_HALL_UNITS if building_type == "commercial" and total >= 150 else HALL_UNITS
    levels = sorted({r.floor for r in program.rooms})
    per_level_area = sum(r.target_area_sqm for r in program.rooms) / len(levels)
    footprints = _footprints(per_level_area)
    found = _Collector()

    if len(levels) == 1:
        rooms = program.rooms
        hall = next((r for r in rooms if r.type == "corridor"), None)
        assigns = sorted(_band_assignments(rooms), key=lambda fb: _balance_penalty(*fb))[:6]
        for ai, (front, back) in enumerate(assigns):
            for end_l, end_r, mode in _end_choices(back, hall is not None, None):
                start_bias = hall is not None and end_l is None
                middle = [r for r in back if r is not end_l and r is not end_r]
                for fo in orderings(front, "front", 3, start_bias):
                    for bo in orderings(middle, "back", 2, ends=(end_l, end_r)):
                        for fi in stack_variants(fo):
                            for bi in stack_variants(bo):
                                tree = _band_tree(fi, bi, end_l, end_r, hall, hall_units)
                                if tree is None:
                                    continue
                                key = ("band", ai, mode, _sig(fi), _sig(bi))
                                for w, d in footprints:
                                    placed, ok = solve(tree, w, d)
                                    found.add(Layout("Split plan" if hall else "Open plan", key, r3(w * GRID), r3(d * GRID), placed, ok))
        _wing_candidates(rooms, hall, hall_units, footprints, found)
        return found.best(limit)

    # Multi-level: identical footprint on every level, stair pinned in the
    # same place so it lines up vertically.
    base = levels[0]
    ground = [r for r in program.rooms if r.floor == base]
    g_hall = next((r for r in ground if r.type == "corridor"), None)
    g_stair = next(r for r in ground if r.type == "stair")
    g_assigns = sorted(_band_assignments(ground), key=lambda fb: _balance_penalty(*fb))[:4]
    uppers = []
    for lv in levels[1:]:
        lv_rooms = [r for r in program.rooms if r.floor == lv]
        uppers.append(
            (
                next((r for r in lv_rooms if r.type == "corridor"), None),
                next(r for r in lv_rooms if r.type == "stair"),
                _upper_assignments(lv_rooms),
            )
        )

    for ai, (front, back) in enumerate(g_assigns):
        back = back + [g_stair]
        for end_l, end_r, mode in _end_choices(back, g_hall is not None, g_stair):
            middle = [r for r in back if r is not end_l and r is not end_r]
            for fo in orderings(front, "front", 2, True):
                for bo in orderings(middle, "back", 2, ends=(end_l, end_r)) if middle else [[]]:
                    for fi in stack_variants(fo):
                        tree = _band_tree(fi, bo, end_l, end_r, g_hall, hall_units)
                        if tree is None:
                            continue
                        for w, d in footprints:
                            g_placed, ok = solve(tree, w, d)
                            front_ids = {r.id for r in _flat(fi)}
                            front_units = round(max(p.box.y1 for p in g_placed if p.room.id in front_ids) / GRID)
                            all_placed = list(g_placed)
                            feasible = ok
                            for lv_hall, lv_stair, lv_assigns in uppers:
                                best_lv = _best_upper(lv_assigns, lv_hall, lv_stair, hall_units, front_units, w, d)
                                if best_lv is None:
                                    feasible = False
                                    continue
                                all_placed.extend(best_lv[0])
                                feasible = feasible and best_lv[1]
                            key = ("stack", ai, mode, _sig(fi), tuple(r.id for r in bo))
                            found.add(Layout("Stacked levels", key, r3(w * GRID), r3(d * GRID), all_placed, feasible))
    return found.best(limit)


def _best_upper(assigns, hall, stair, hall_units, front_units, w, d):
    target_front = w * front_units * GRID * GRID
    ranked = sorted(assigns, key=lambda fb: abs(sum(r.target_area_sqm for r in fb[0]) - target_front))[:5]
    best = None
    for uf, ub in ranked:
        ub = ub + [stair]
        for el, er, _mode in _end_choices(ub, hall is not None, stair):
            mid = [r for r in ub if r is not el and r is not er]
            for ufo in orderings(uf, "front", 2):
                for ubo in orderings(mid, "back", 2, ends=(el, er)):
                    for ubi in stack_variants(ubo):
                        t = _band_tree(ufo, ubi, el, er, hall, hall_units, front_fixed=front_units)
                        if t is None:
                            continue
                        placed, ok = solve(t, w, d)
                        pen = _quick_penalty(placed, w * GRID, d * GRID) + (0 if ok else 50)
                        if best is None or pen < best[0]:
                            best = (pen, placed, ok)
    return None if best is None else (best[1], best[2])


def _split_private(rooms: list[ProgramRoom]) -> list[tuple[list[ProgramRoom], list[ProgramRoom]]]:
    """Two-row splits of private rooms for a double-loaded wing."""
    primary = next((r for r in rooms if r.primary), None)
    ensuite = next((r for r in rooms if r.type == "ensuite"), None)
    rest = sorted([r for r in rooms if r is not primary and r is not ensuite], key=lambda r: -r.target_area_sqm)
    a: list[ProgramRoom] = [x for x in (primary, ensuite) if x is not None]
    b: list[ProgramRoom] = []
    for r in rest:
        (a if sum(x.target_area_sqm for x in a) <= sum(x.target_area_sqm for x in b) else b).append(r)
    return [(f, k) for f, k in ((b, a), (a, b)) if f and k]


def _wing_candidates(rooms, hall, hall_units, footprints, found: _Collector) -> None:
    """Public block at one end, private rooms on a double-loaded hall."""
    if hall is None:
        return
    private = [r for r in rooms if r.type in {"bedroom", "bathroom", "ensuite", "private_office", "study", "server_room"}]
    public = [r for r in rooms if r not in private and r.type != "corridor"]
    if len([r for r in private if r.type in {"bedroom", "private_office"}]) < 3 or len(public) < 2:
        return
    pub_front = [r for r in public if r.type in {"entry", "reception", "living", "garage", "studio"}]
    pub_back = [r for r in public if r not in pub_front]
    if not pub_back and len(pub_front) > 2:
        pub_back = [pub_front.pop()]
    for si, (pf, pb) in enumerate(_split_private(private)):
        for public_left in (True, False):
            for fo in orderings(pub_front, "front", 2, start_bias=not public_left):
                pbo = orderings(pub_back, "front", 1)[0] if pub_back else []
                for fi in stack_variants(fo):
                    for pfi in stack_variants(orderings(pf, "back", 1)[0]):
                        pki = stack_variants(orderings(pb, "back", 1)[0])[-1]
                        pub_rows: list[Node] = [_row(fi, "back")]
                        if pbo:
                            pub_rows.append(_row(stack_variants(pbo)[-1], "front"))
                        public_block = pub_rows[0] if len(pub_rows) == 1 else Split("y", pub_rows)
                        private_block = Split("y", [_row(pfi, "back"), Leaf(hall, fixed=hall_units), _row(pki, "front")])
                        tree = Split("x", [public_block, private_block] if public_left else [private_block, public_block])
                        key = ("wing", si, public_left, _sig(fi), _sig(pfi))
                        for w, d in footprints:
                            placed, ok = solve(tree, w, d)
                            found.add(Layout("Wing plan", key, r3(w * GRID), r3(d * GRID), placed, ok))
