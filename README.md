# Architect Planner

Architect Planner is a production-oriented AI-assisted architectural layout engine that converts natural-language briefs into structured, editable, architect-style schematic floor plans.

## Features

- Natural-language architectural brief interpretation
- Program generation with room schedule, zoning, and adjacency targets
- Multi-candidate layout generation (grid, slicing, adjacency-aware)
- Geometry refinement and topology cleanup
- Door and window placement with symbolic drafting
- Furniture-aware usability evaluation
- Multi-factor scoring and ranking
- Validation engine for architectural plausibility
- Exports: JSON, SVG, PDF, DXF, PNG preview
- Secondary parser for image/PDF plans
- React frontend for interactive generation and review

## Monorepo Structure

- `backend/`: FastAPI service and planning engines
- `frontend/`: React + TypeScript UI
- `examples/`: sample generated outputs
- `docs/`: architecture and API notes

## Quick Start (Docker)

```bash
docker compose up --build
```

Backend: http://localhost:8000/docs  
Frontend: http://localhost:5173

## Local Development

### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host --port 5173
```

## Example Prompt

- "Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft"

## API Endpoints

- `POST /api/generate`
- `POST /api/parse`
- `POST /api/validate`
- `POST /api/export/svg`
- `POST /api/export/pdf`
- `POST /api/export/dxf`
- `GET /api/examples`

## Testing

```bash
cd backend
pytest
```

Includes a golden test for: `800 sqft, 2 bedrooms, kitchen, bathroom`.
