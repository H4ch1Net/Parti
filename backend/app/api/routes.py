from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.core.config import OUTPUT_DIR
from app.models.schemas import BriefRequest, ExportRequest, GenerateResponse, ParseResponse, ValidateRequest
from app.services.drafting_engine import draft_svg
from app.services.export_engine import export_dxf, export_pdf, export_pdf_bytes, export_png_preview, export_svg
from app.services.parser_engine import parse_plan
from app.services.planner_pipeline import generate_from_prompt
from app.services.validation_engine import validate_candidate

router = APIRouter(prefix="/api", tags=["planner"])


def _ensure_exportable(req: ExportRequest) -> None:
    c = req.candidate
    if not c.validation.valid:
        raise HTTPException(status_code=400, detail="Candidate is not valid and cannot be exported")
    if c.score.total < 70.0:
        raise HTTPException(status_code=400, detail="Candidate does not meet export quality threshold: total >= 70")


@router.post("/generate", response_model=GenerateResponse)
def generate(req: BriefRequest) -> GenerateResponse:
    return generate_from_prompt(req.prompt)


@router.post("/parse", response_model=ParseResponse)
async def parse(file: UploadFile = File(...)) -> ParseResponse:
    dest = OUTPUT_DIR / file.filename
    dest.write_bytes(await file.read())
    return parse_plan(dest)


@router.post("/validate")
def validate(req: ValidateRequest):
    report = validate_candidate(req.candidate)
    return report.model_dump()


@router.post("/export/svg")
def export_to_svg(req: ExportRequest):
    _ensure_exportable(req)
    path = OUTPUT_DIR / f"{req.candidate.id}.svg"
    export_svg(req.candidate, path)
    return FileResponse(path, media_type="image/svg+xml", filename=path.name)


@router.post("/export/pdf")
def export_to_pdf(req: ExportRequest):
    _ensure_exportable(req)
    path = OUTPUT_DIR / f"{req.candidate.id}.pdf"
    export_pdf(req.candidate, path)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/export/dxf")
def export_to_dxf(req: ExportRequest):
    _ensure_exportable(req)
    path = OUTPUT_DIR / f"{req.candidate.id}.dxf"
    export_dxf(req.candidate, path)
    return FileResponse(path, media_type="application/dxf", filename=path.name)


@router.post("/export/png")
def export_to_png(req: ExportRequest):
    _ensure_exportable(req)
    path = OUTPUT_DIR / f"{req.candidate.id}.png"
    export_png_preview(req.candidate, path)
    return FileResponse(path, media_type="image/png", filename=path.name)


@router.post("/export/svg-inline")
def export_svg_inline(req: ExportRequest):
    _ensure_exportable(req)
    return Response(content=draft_svg(req.candidate), media_type="image/svg+xml")


@router.get("/examples")
def examples():
    return JSONResponse(
        [
            "Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft",
            "Design a compact 2-bedroom apartment with open kitchen and good daylight",
            "Create a 3-bedroom house around 1400 sqft with master suite privacy and efficient circulation",
        ]
    )
