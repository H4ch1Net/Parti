# API reference

Base URL: `http://localhost:8000`. Interactive documentation is served at `/docs` (Swagger UI) and `/redoc`. Request and response models are defined in `backend/app/models/schemas.py`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check and version |
| GET | `/api/examples` | Sample briefs `[{title, prompt}]` |
| GET | `/api/room-types` | Room catalog for program editors |
| POST | `/api/interpret` | Prompt to structured brief |
| POST | `/api/generate` | Prompt or brief to ranked plan candidates |
| POST | `/api/validate` | Re-check any candidate |
| POST | `/api/export/{format}` | Download a candidate as `svg`, `pdf`, `png` or `dxf` |

## POST /api/interpret

```json
{ "prompt": "3 bed 2 bath house, 1,300 sq ft, open plan" }
```

Returns a `StructuredBrief`:

```json
{
  "raw_prompt": "3 bed 2 bath house, 1,300 sq ft, open plan",
  "building_type": "residential",
  "target_area_sqm": 120.77,
  "target_area_sqft": 1300.0,
  "area_source": "stated",
  "stories": 1,
  "style": "open_plan",
  "rooms": [
    { "type": "entry", "count": 1 },
    { "type": "living", "count": 1 },
    { "type": "dining", "count": 1 },
    { "type": "kitchen", "count": 1 },
    { "type": "bedroom", "count": 3 },
    { "type": "bathroom", "count": 2 }
  ],
  "preferences": { "daylight": false, "privacy": false, "compact": false },
  "notes": ["Added a dining area for a family-sized home"]
}
```

The interpreter understands digits and number words, hyphenated counts (`2-bedroom`), shorthand (`3br/2ba`), half baths (`2.5 bath` becomes two bathrooms and a powder room), areas in square feet or square metres (`1,200 sq ft`, `85 m2`), stories, garages (`2-car garage`), home offices, and commercial programs (reception, private and open offices, meeting rooms, break and server rooms). Anything it assumes is listed in `notes`.

## POST /api/generate

Send either a prompt or a brief (for example one returned by `/api/interpret` and then edited). `count` is the number of variants to return (1 to 12, default 6).

```json
{ "prompt": "2 bedroom apartment, 800 sqft", "count": 6 }
```

```json
{ "brief": { "...": "StructuredBrief" }, "count": 3 }
```

Response:

| Field | Description |
|---|---|
| `brief` | The brief that was used. The area may be raised if the request was too small, with a note. |
| `program` | Rooms with level, zone and target area, plus adjacency preferences |
| `candidates` | Plans ranked best first. Only valid plans are returned when any exist. |
| `best_candidate_id` | Id of the first candidate |
| `drawings` | Interactive SVG per candidate id, one string per level |
| `elapsed_ms` | Generation time |

A candidate contains:

| Field | Description |
|---|---|
| `id`, `label`, `strategy` | `variant-a`, `Variant A`, `Split plan` |
| `floors`, `footprint` | Level count and footprint `{width_m, depth_m, area_sqm}` |
| `rooms` | `{id, type, name, zone, floor, polygon, width_m, depth_m, area_sqm, target_area_sqm, primary, capacity}` |
| `walls` | Unique wall segments with thickness and an `exterior` flag |
| `doors` | `{kind, floor, room_a, room_b, segment, width, hinge, swing}`; kinds are `entry`, `door`, `opening`, `garage` |
| `windows` | `{room_id, floor, segment, width}` |
| `fixtures` | `{room_id, floor, type, footprint, facing}` |
| `connections` | Room graph: `{from_room, to_room, kind}` with kinds `door`, `opening`, `stair` |
| `score` | `{total, grade, categories[], summary}` |
| `validation` | `{valid, issues[]}`; each issue has `severity`, `code`, `message`, `room_ids` |

Coordinates are metres. `x` runs along the street front and `y` runs from the front facade (0) to the back.

## POST /api/validate

```json
{ "candidate": { "...": "Candidate" }, "target_area_sqm": 74.3 }
```

Returns a `ValidationReport`. Issue codes include `access.entry`, `access.unreachable`, `dims.min_width`, `dims.garage`, `dims.aspect`, `daylight.none`, `daylight.low`, `fixtures.missing`, `privacy.bedroom`, `privacy.bathroom`, `privacy.garage`, `area.total`, `area.cramped`, `area.oversized`, `circulation.share`, `geometry.overlap` and `geometry.void`.

## POST /api/export/{format}

```json
{ "candidate": { "...": "Candidate" }, "units": "imperial", "title": "Smith residence" }
```

| Format | Content |
|---|---|
| `svg` | Vector drawing at 1:100 when printed at 100% |
| `pdf` | A3 landscape sheet at the largest standard scale that fits, with title block |
| `png` | Raster preview, about 2400 px wide |
| `dxf` | R2010, metres, layers `A-WALL`, `A-DOOR`, `A-GLAZ`, `A-FURN`, `A-AREA`, `A-ANNO-TEXT`, `A-ANNO-DIMS`, `A-ANNO-SYMB` |

The response is a file download named `parti-<candidate id>.<format>`.

## Errors

Validation problems in the request return `422` with FastAPI's standard `detail` body. A brief with no rooms, or one that cannot be laid out, also returns `422` with a message in `detail`.
