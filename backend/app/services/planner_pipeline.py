from __future__ import annotations

from app.models.schemas import GenerateResponse
from app.services.brief_interpreter import interpret_brief
from app.services.furniture_evaluator import evaluate_furniture
from app.services.geometry_refiner import refine_geometry
from app.services.layout_generator import generate_layout_candidates
from app.services.openings_engine import place_openings
from app.services.parti_selector import ProgramBrief, select_parti
from app.services.program_generator import build_program
from app.services.scoring_engine import lowest_scoring_category, score_candidate
from app.services.validation_engine import validate_candidate
from app.services.zoning_engine import build_zones


def generate_from_prompt(prompt: str) -> GenerateResponse:
    brief = interpret_brief(prompt)
    program = build_program(brief)
    zones = build_zones(program)
    parti_brief = ProgramBrief.from_structured(brief)
    parti = select_parti(parti_brief)

    scored = []
    for attempt in range(3):
        candidates = generate_layout_candidates(program, parti_brief, parti, zones, count=5, variant_offset=attempt * 5)
        for c in candidates:
            c = refine_geometry(c)
            c = place_openings(c)
            c, furn_score = evaluate_furniture(c)
            c.validation = validate_candidate(c, target_area_sqm=program.target_area_sqm, building_type=brief.building_type)
            c.score = score_candidate(c, program, furn_score)
            scored.append(c)

    if not scored:
        raise ValueError("No layout candidates were generated")

    scored.sort(key=lambda x: (x.validation.valid, x.score.total), reverse=True)
    best = scored[0]  # Best available, valid or not

    return GenerateResponse(brief=brief, program=program, candidates=scored, best_candidate_id=best.id)
