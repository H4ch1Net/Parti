"""Entry points that turn a candidate into drawings."""

from __future__ import annotations

from datetime import date

from app.drawing import units as fmt
from app.drawing.sheet import Sheet, build_sheet
from app.drawing.svg import render_svg
from app.models.schemas import Candidate


def sheets(candidate: Candidate, units: str) -> list[Sheet]:
    levels = sorted({r.floor for r in candidate.rooms})
    return [build_sheet(candidate, lv, units) for lv in levels]


def app_svgs(candidate: Candidate) -> list[str]:
    """One interactive SVG per level, carrying both unit systems."""
    return [render_svg([s], mode="app") for s in sheets(candidate, "both")]


def title_lines(candidate: Candidate, units: str, title: str | None) -> list[str]:
    area = fmt.area(candidate.total_area_sqm, units)
    fp = f"{fmt.length(candidate.footprint.width_m, units)} × {fmt.length(candidate.footprint.depth_m, units)}"
    return [
        title or f"Parti · {candidate.label}",
        f"{candidate.strategy} · {area} · footprint {fp}{' m' if units == 'metric' else ''} · score {candidate.score.total:.0f}/100",
        f"Schematic only, not for construction · scale 1:100 at printed size · {date.today().isoformat()}",
    ]


def export_svg(candidate: Candidate, units: str = "metric", title: str | None = None) -> str:
    return render_svg(sheets(candidate, units), mode="export", title_lines=title_lines(candidate, units, title))


def export_file(candidate: Candidate, fmt_name: str, units: str = "metric", title: str | None = None) -> bytes:
    from app.drawing.dxf import render_dxf
    from app.drawing.pdf import render_pdf
    from app.drawing.png import render_png

    pages = sheets(candidate, units)
    lines = title_lines(candidate, units, title)
    if fmt_name == "svg":
        return render_svg(pages, mode="export", title_lines=lines).encode("utf-8")
    if fmt_name == "pdf":
        return render_pdf(pages, lines)
    if fmt_name == "png":
        return render_png(pages, lines)
    if fmt_name == "dxf":
        return render_dxf(pages)
    raise ValueError(f"Unsupported format: {fmt_name}")
