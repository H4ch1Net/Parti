# Parti

**Work in progress.** The layout generator is functional but output quality is inconsistent. Expect broken plans, weird room proportions, and results that don't match the brief well. This is being actively worked on.

Parti is an AI-assisted architectural floor plan generator. You give it a natural language brief and it tries to produce a schematic layout with rooms, walls, doors, windows, and furniture proxies.

## Stack

- **Backend:** FastAPI + Python (planning pipeline, exports)
- **Frontend:** React + TypeScript (viewer, candidate browser)

## Pipeline

Brief text goes through a chain of engines:

1. Brief interpreter (NL to structured program)
2. Program generator (room schedule, areas, adjacency targets)
3. Zoning engine
4. Layout generator (multi-candidate, grid/slicing)
5. Geometry refiner
6. Openings engine (doors, windows)
7. Furniture evaluator
8. Validation + scoring
9. Export (SVG, PDF, DXF, PNG, JSON)

## Running

### Docker (recommended)

```bash
docker compose up --build
```

- Backend API + docs: `http://localhost:8000/docs`
- Frontend: `http://localhost:5173`

### Local

```bash
# Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev -- --host --port 5173
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/generate` | Generate floor plan from text prompt |
| POST | `/api/parse` | Parse an uploaded image/PDF plan |
| POST | `/api/validate` | Validate a candidate plan |
| POST | `/api/export/svg` | Export candidate as SVG |
| POST | `/api/export/pdf` | Export candidate as PDF |
| POST | `/api/export/dxf` | Export candidate as DXF |
| POST | `/api/export/png` | Export candidate as PNG |
| GET | `/api/examples` | Get example prompts |

Example prompt: `"Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft"`

## Tests

```bash
cd backend
pytest
```

## Status

| Component | State |
|-----------|-------|
| Brief interpreter | Working |
| Program / zoning | Working |
| Layout generation | Inconsistent |
| Geometry refinement | Partial |
| Openings placement | Working |
| Furniture evaluation | Working |
| Scoring / validation | Working |
| Exports (SVG, PDF, DXF) | Working |
| Frontend viewer | Working |
| Parser (image/PDF input) | Stub |
