"""Generation pipeline: brief -> ranked plan candidates."""

from __future__ import annotations

import logging
import time
from string import ascii_uppercase

from app.engine.access import plan_access
from app.engine.brief import interpret_brief
from app.engine.furniture import furnish
from app.engine.layout import Layout, layout_candidates
from app.engine.program import build_program
from app.engine.scoring import score_candidate
from app.engine.validation import validate_candidate
from app.engine.walls import build_walls
from app.engine.windows import place_windows
from app.models.schemas import (
    Candidate,
    Fixture,
    Footprint,
    GenerateResponse,
    Program,
    Room,
    Score,
    StructuredBrief,
    ValidationReport,
)

log = logging.getLogger(__name__)

_PENDING_SCORE = Score(total=0, grade="weak", categories=[], summary="")


def _assemble(layout: Layout, brief: StructuredBrief, fixtures: list[Fixture] | None) -> tuple[Candidate, list]:
    commercial = brief.building_type == "commercial"
    access = plan_access(layout, brief.style, commercial)
    windows = place_windows(layout, access.doors)
    rooms = [
        Room(
            id=p.room.id,
            type=p.room.type,
            name=p.room.name,
            zone=p.room.zone,
            floor=p.room.floor,
            polygon=p.box.polygon(),
            width_m=p.box.w,
            depth_m=p.box.h,
            area_sqm=round(p.box.area, 2),
            target_area_sqm=p.room.target_area_sqm,
            primary=p.room.primary,
        )
        for p in layout.rooms
    ]
    zones: dict[str, list[str]] = {}
    for r in rooms:
        zones.setdefault(r.zone, []).append(r.id)
    candidate = Candidate(
        id="pending",
        label="",
        strategy=layout.strategy,
        floors=len({r.floor for r in rooms}),
        footprint=Footprint(width_m=layout.width, depth_m=layout.depth),
        rooms=rooms,
        walls=build_walls(layout) if fixtures is not None else [],
        doors=access.doors,
        windows=windows,
        fixtures=fixtures or [],
        connections=access.connections,
        zones=zones,
        score=_PENDING_SCORE,
        validation=ValidationReport(valid=False),
    )
    return candidate, access.unreachable


def _evaluate(candidate: Candidate, program: Program, brief: StructuredBrief, furnished: bool) -> Candidate:
    candidate.validation = validate_candidate(candidate, program.target_area_sqm, check_fixtures=furnished)
    candidate.score = score_candidate(candidate, program, brief.preferences)
    return candidate


def _rank_key(c: Candidate) -> tuple:
    errors = sum(1 for i in c.validation.issues if i.severity == "error")
    narrow = sum(1 for i in c.validation.issues if i.code == "dims.aspect")
    return (errors, narrow, -c.score.total)


def generate(brief: StructuredBrief, count: int = 6) -> GenerateResponse:
    started = time.perf_counter()
    program = build_program(brief)
    layouts = layout_candidates(program, brief.building_type)

    # Pass 1: quick evaluation without furniture.
    seen: set[tuple] = set()
    quick: list[tuple[Candidate, Layout]] = []
    for layout in layouts:
        sig = tuple(sorted((p.room.id, p.box.x, p.box.y, p.box.w, p.box.h) for p in layout.rooms))
        mirrored = tuple(sorted((p.room.id, round(layout.width - p.box.x1, 3), p.box.y, p.box.w, p.box.h) for p in layout.rooms))
        if sig in seen or mirrored in seen:
            continue
        seen.add(sig)
        cand, _ = _assemble(layout, brief, None)
        quick.append((_evaluate(cand, program, brief, furnished=False), layout))
    quick.sort(key=lambda t: _rank_key(t[0]))

    # Pass 2: furnish the most promising layouts, keeping structural variety.
    shortlist: list[Layout] = []
    keys: dict[tuple, int] = {}
    for _cand, layout in quick:
        if len(shortlist) >= count * 3:
            break
        k = layout.key
        if keys.get(k, 0) >= 1 and len(quick) > count * 3:
            continue
        keys[k] = keys.get(k, 0) + 1
        shortlist.append(layout)

    final: list[tuple[Candidate, Layout]] = []
    for layout in shortlist:
        draft, _ = _assemble(layout, brief, None)
        fixtures, _missing = furnish(layout, draft.doors, draft.windows)
        cand, _ = _assemble(layout, brief, fixtures)
        final.append((_evaluate(cand, program, brief, furnished=True), layout))
    final.sort(key=lambda t: _rank_key(t[0]))

    # Prefer structurally different plans; near-identical twins only fill gaps.
    chosen: list[Candidate] = []
    strategy_count: dict[tuple, int] = {}
    fingerprints: set[tuple] = set()
    for cand, layout in final:
        sk = layout.key[:3]
        fp = (round(cand.score.total), cand.footprint.width_m, cand.footprint.depth_m)
        if strategy_count.get(sk, 0) >= 2 or fp in fingerprints:
            continue
        strategy_count[sk] = strategy_count.get(sk, 0) + 1
        fingerprints.add(fp)
        chosen.append(cand)
        if len(chosen) == count:
            break
    for cand, _ in final:
        if len(chosen) >= count:
            break
        if cand not in chosen:
            chosen.append(cand)
    chosen.sort(key=_rank_key)
    # Broken plans are only worth showing when nothing better exists.
    if any(c.validation.valid for c in chosen):
        chosen = [c for c in chosen if c.validation.valid]
    else:
        chosen = chosen[:3]

    if not chosen:
        raise ValueError("No layout could be generated for this brief")
    for i, cand in enumerate(chosen):
        letter = ascii_uppercase[i]
        cand.id = f"variant-{letter.lower()}"
        cand.label = f"Variant {letter}"

    elapsed = int((time.perf_counter() - started) * 1000)
    log.info("generated %d candidates from %d layouts in %d ms", len(chosen), len(layouts), elapsed)
    return GenerateResponse(
        brief=brief,
        program=program,
        candidates=chosen,
        best_candidate_id=chosen[0].id,
        elapsed_ms=elapsed,
    )


def generate_from_prompt(prompt: str, count: int = 6) -> GenerateResponse:
    return generate(interpret_brief(prompt), count)
