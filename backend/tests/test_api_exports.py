from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _best_candidate():
    res = client.post("/api/generate", json={"prompt": "800 sqft, 2 bedrooms, kitchen, bathroom"})
    assert res.status_code == 200
    payload = res.json()
    best_id = payload["best_candidate_id"]
    candidate = next(c for c in payload["candidates"] if c["id"] == best_id)
    return candidate


def test_export_svg_pdf_dxf_endpoints():
    candidate = _best_candidate()
    svg = client.post("/api/export/svg", json={"candidate": candidate})
    pdf = client.post("/api/export/pdf", json={"candidate": candidate})
    dxf = client.post("/api/export/dxf", json={"candidate": candidate})
    assert svg.status_code == 200
    assert pdf.status_code == 200
    assert dxf.status_code == 200
