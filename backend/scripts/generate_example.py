import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.export_engine import export_dxf, export_pdf, export_png_preview, export_svg
from app.services.planner_pipeline import generate_from_prompt


PROMPT = "Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft"
OUT = ROOT.parent / "examples"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    response = generate_from_prompt(PROMPT)
    best = next(c for c in response.candidates if c.id == response.best_candidate_id)

    json_path = OUT / "golden_800sqft.json"
    svg_path = OUT / "golden_800sqft.svg"
    pdf_path = OUT / "golden_800sqft.pdf"
    dxf_path = OUT / "golden_800sqft.dxf"
    png_path = OUT / "golden_800sqft.png"

    json_path.write_text(json.dumps(response.model_dump(), indent=2), encoding="utf-8")
    export_svg(best, svg_path)
    export_pdf(best, pdf_path)
    export_dxf(best, dxf_path)
    export_png_preview(best, png_path)

    print(f"Wrote {json_path}")
    print(f"Wrote {svg_path}")
    print(f"Wrote {pdf_path}")
    print(f"Wrote {dxf_path}")
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
