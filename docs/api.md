# API Reference

Base URL: `http://localhost:8000`

## Endpoints

- `POST /api/generate`
  - input: `{ "prompt": "..." }`
  - output: full brief/program/candidates/best id

- `POST /api/parse`
  - input: multipart upload (`file`)
  - output: parsed walls and room polygons

- `POST /api/validate`
  - input: `{ "candidate": { ... } }`
  - output: validation report

- `POST /api/export/svg`
- `POST /api/export/pdf`
- `POST /api/export/dxf`
- `POST /api/export/png`
  - input: `{ "candidate": { ... } }`
  - output: downloadable file

- `POST /api/export/svg-inline`
  - input: `{ "candidate": { ... } }`
  - output: svg markup text

- `GET /api/examples`
  - output: list of sample prompts

- `GET /health`
  - output: `{ "status": "ok" }`
