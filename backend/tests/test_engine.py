"""Invariants every generated plan must satisfy, across many briefs."""

from collections import defaultdict

import pytest

from app.core.geometry import shared_edge
from app.engine.brief import interpret_brief
from app.engine.pipeline import generate
from app.engine.program import build_program
from app.engine.rooms import SPECS, min_side
from app.engine.validation import reachable_rooms, room_box
from tests.conftest import best, generated

BRIEFS = [
    "studio apartment 400 sqft",
    "1 bedroom apartment 550 sqft",
    "800 sqft, 2 bedrooms, kitchen, bathroom",
    "3 bedroom 2 bathroom house 1200 sqft open plan",
    "traditional 3 bed 2 bath house 1400 sqft with laundry",
    "4 bedroom 2.5 bathroom house 2000 sqft with master ensuite",
    "three bedroom home with a home office and 2-car garage, 1,650 sq ft",
    "two story house 1800 sqft, 3 bedrooms upstairs, living kitchen dining downstairs, 2 bathrooms",
    "small office 600 sqft, reception, 3 private offices, bathroom",
    "office for 12 people with 2 meeting rooms and a kitchen",
]


@pytest.mark.parametrize("prompt", BRIEFS)
def test_best_plan_is_valid(prompt):
    plan = best(prompt)
    assert plan.validation.valid, plan.validation.errors


@pytest.mark.parametrize("prompt", BRIEFS)
def test_rooms_tile_the_footprint(prompt):
    for c in generated(prompt).candidates:
        per_level = defaultdict(list)
        for r in c.rooms:
            per_level[r.floor].append(room_box(r))
        gross = c.footprint.width_m * c.footprint.depth_m
        for boxes in per_level.values():
            assert sum(b.area for b in boxes) == pytest.approx(gross, abs=0.05)
            for i, a in enumerate(boxes):
                assert a.x >= -1e-6 and a.y >= -1e-6
                assert a.x1 <= c.footprint.width_m + 1e-6 and a.y1 <= c.footprint.depth_m + 1e-6
                for b in boxes[i + 1 :]:
                    assert not a.intersects(b, tol=1e-3)


@pytest.mark.parametrize("prompt", BRIEFS)
def test_every_room_is_reachable(prompt):
    for c in generated(prompt).candidates:
        if c.validation.valid:
            assert reachable_rooms(c) == {r.id for r in c.rooms}


@pytest.mark.parametrize("prompt", BRIEFS)
def test_program_is_respected(prompt):
    brief = interpret_brief(prompt)
    program = build_program(brief)
    plan = best(prompt)
    assert sorted(r.id for r in plan.rooms) == sorted(r.id for r in program.rooms)
    assert plan.total_area_sqm == pytest.approx(brief.target_area_sqm, rel=0.06)


@pytest.mark.parametrize("prompt", BRIEFS)
def test_minimum_dimensions_and_daylight(prompt):
    plan = best(prompt)
    windows = {w.room_id for w in plan.windows}
    for r in plan.rooms:
        assert min(r.width_m, r.depth_m) + 1e-6 >= min_side(r.type, r.primary), r.name
        if SPECS[r.type].habitable:
            assert r.id in windows, f"{r.name} has no window"


@pytest.mark.parametrize("prompt", BRIEFS)
def test_doors_sit_on_shared_walls(prompt):
    plan = best(prompt)
    boxes = {r.id: room_box(r) for r in plan.rooms}
    for d in plan.doors:
        (x0, y0), (x1, y1) = d.segment
        if d.room_a == "exterior":
            b = boxes[d.room_b]
            on_facade = (
                abs(y0 - 0) < 1e-6
                or abs(x0 - 0) < 1e-6
                or abs(y0 - plan.footprint.depth_m) < 1e-6
                or abs(x0 - plan.footprint.width_m) < 1e-6
            )
            assert on_facade and b.contains_point(x0, y0) and b.contains_point(x1, y1)
            continue
        seg = shared_edge(boxes[d.room_a], boxes[d.room_b])
        assert seg is not None, d.id
        lo, hi = sorted((x0, x1)) if seg.horizontal else sorted((y0, y1))
        assert seg.lo - 1e-6 <= lo and hi <= seg.hi + 1e-6, d.id
        if d.kind == "door":
            sx, sy = d.swing
            assert boxes[d.room_b].contains_point(sx, sy), f"{d.id} swings outside {d.room_b}"


def test_multi_level_stair_lines_up():
    plan = best(BRIEFS[7])
    stairs = [room_box(r) for r in plan.rooms if r.type == "stair"]
    assert len(stairs) == 2
    assert stairs[0] == stairs[1]
    assert any(c.kind == "stair" for c in plan.connections)
    assert {r.floor for r in plan.rooms} == {1, 2}


def test_bedrooms_open_off_circulation():
    plan = best("3 bedroom 2 bathroom house 1200 sqft open plan")
    by_id = {r.id: r for r in plan.rooms}
    for c in plan.connections:
        target = by_id.get(c.to_room)
        if target and target.type == "bedroom":
            assert by_id[c.from_room].type in {"corridor", "entry", "stair"}


def test_generation_is_deterministic():
    brief = interpret_brief("3 bed 2 bath 1300 sqft")
    a = generate(brief)
    b = generate(brief)
    assert [c.model_dump() for c in a.candidates] == [c.model_dump() for c in b.candidates]


def test_candidates_are_ranked_and_distinct():
    result = generated(BRIEFS[3])
    scores = [c.score.total for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert result.best_candidate_id == result.candidates[0].id
    shapes = {tuple(tuple(r.polygon[0]) for r in c.rooms) for c in result.candidates}
    assert len(shapes) == len(result.candidates)


def test_overconstrained_brief_still_returns_a_plan():
    result = generate(interpret_brief("5 bedroom 3 bathroom house 600 sqft"))
    assert result.candidates
    assert result.candidates[0].rooms
