# System Architecture

## End-to-End Pipeline

1. Brief Interpreter (`brief_interpreter.py`)
2. Program Generator (`program_generator.py`)
3. Zoning Engine (`zoning_engine.py`)
4. Layout Generator (`layout_generator.py`)
5. Geometry Refiner (`geometry_refiner.py`)
6. Openings Engine (`openings_engine.py`)
7. Furniture Evaluator (`furniture_evaluator.py`)
8. Validation Engine (`validation_engine.py`)
9. Scoring Engine (`scoring_engine.py`)
10. Drafting and Annotation (`drafting_engine.py`)
11. Export Engine (`export_engine.py`)
12. Parser (`parser_engine.py`)

## Canonical Plan Representation

Each candidate includes:
- rooms (polygon + area + dimensions + type + zone)
- walls (segments + thickness + exterior/interior)
- openings (doors/windows)
- fixtures (furniture proxies)
- zones
- circulation graph edges
- room schedule
- scoring breakdown
- validation report

## Candidate Generation Strategy

- Area-constrained rectangular envelope
- Room strip partitioning by program and zone priorities
- Minimum width constraints by room type
- Multiple variants (ordering + envelope ratio perturbation)

## Validation Rules

- positive room area
- room-type minimum dimensions
- overlap detection
- door references validity
- window sanity checks

## Exports

- JSON canonical: from generation response
- SVG: line-weighted walls, labels, legends, schedule
- PDF: vector linework and labels via ReportLab
- DXF: LWPolyline + text labels
- PNG: quick raster preview

## Parser

- edge detection (Canny)
- wall segment extraction (Hough lines)
- room contour extraction (contours + poly approx)
- basic labels array (OCR placeholder for extension)
