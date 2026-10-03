from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.drawing.render import app_svgs, export_file
from app.engine.brief import interpret_brief
from app.engine.pipeline import generate
from app.engine.rooms import COMMERCIAL_TYPES, RESIDENTIAL_TYPES, SPECS
from app.engine.validation import validate_candidate
from app.models.schemas import (
    ExportRequest,
    GenerateRequest,
    GenerateResponse,
    InterpretRequest,
    StructuredBrief,
    ValidateRequest,
    ValidationReport,
)

router = APIRouter(prefix="/api", tags=["planner"])

EXAMPLES = [
    {"title": "Studio", "prompt": "Studio apartment, 400 sq ft, with a full bathroom"},
    {"title": "Two-bedroom flat", "prompt": "2 bedroom apartment, 800 sqft, open kitchen and good daylight"},
    {"title": "Family house", "prompt": "3 bed 2 bath house, 1,300 sq ft, open plan with a dining area"},
    {"title": "House with garage", "prompt": "Three bedroom home with a home office, laundry and a 2-car garage, 1,650 sq ft"},
    {"title": "Large house", "prompt": "4 bedroom 2.5 bathroom house, 2000 sqft, master ensuite, privacy for bedrooms"},
    {"title": "Two storeys", "prompt": "Two story house, 1800 sqft, 3 bedrooms upstairs, living, kitchen and dining downstairs"},
    {"title": "Small office", "prompt": "Small office, 600 sqft: reception, 3 private offices and a restroom"},
    {"title": "Team office", "prompt": "Office for 12 people with 2 meeting rooms, a break room and a server room"},
]

MEDIA = {
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "png": "image/png",
    "dxf": "application/dxf",
}


@router.get("/examples")
def examples() -> list[dict[str, str]]:
    return EXAMPLES


@router.get("/room-types")
def room_types() -> list[dict]:
    """Catalog used by the program editor."""
    return [
        {
            "type": s.type,
            "label": s.label,
            "zone": s.zone,
            "residential": s.type in RESIDENTIAL_TYPES,
            "commercial": s.type in COMMERCIAL_TYPES,
        }
        for s in SPECS.values()
        if s.type not in {"corridor", "stair"}
    ]


@router.post("/interpret", response_model=StructuredBrief)
def interpret(req: InterpretRequest) -> StructuredBrief:
    return interpret_brief(req.prompt)


@router.post("/generate", response_model=GenerateResponse)
def generate_plans(req: GenerateRequest) -> GenerateResponse:
    brief = req.brief or interpret_brief(req.prompt or "")
    if not any(r.count > 0 for r in brief.rooms):
        raise HTTPException(status_code=422, detail="The brief has no rooms")
    try:
        result = generate(brief, req.count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result.drawings = {c.id: app_svgs(c) for c in result.candidates}
    return result


@router.post("/validate", response_model=ValidationReport)
def validate(req: ValidateRequest) -> ValidationReport:
    return validate_candidate(req.candidate, req.target_area_sqm)


@router.post("/export/{fmt}")
def export(fmt: Literal["svg", "pdf", "png", "dxf"], req: ExportRequest) -> Response:
    data = export_file(req.candidate, fmt, req.units, req.title)
    filename = f"parti-{req.candidate.id}.{fmt}"
    return Response(
        content=data,
        media_type=MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
