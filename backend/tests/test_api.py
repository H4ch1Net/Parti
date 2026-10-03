from io import StringIO
from xml.etree import ElementTree

import ezdxf
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _generate(prompt: str = "800 sqft, 2 bedrooms, kitchen, bathroom") -> dict:
    res = client.post("/api/generate", json={"prompt": prompt})
    assert res.status_code == 200, res.text
    return res.json()


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_examples_and_room_types():
    examples = client.get("/api/examples").json()
    assert len(examples) >= 4 and all(e["prompt"] for e in examples)
    types = {t["type"] for t in client.get("/api/room-types").json()}
    assert {"bedroom", "kitchen", "private_office"} <= types
    assert "corridor" not in types


def test_interpret():
    res = client.post("/api/interpret", json={"prompt": "3 bed 2 bath, 1300 sq ft"})
    assert res.status_code == 200
    body = res.json()
    assert body["target_area_sqft"] == 1300.0
    assert {r["type"]: r["count"] for r in body["rooms"]}["bedroom"] == 3


def test_generate_returns_candidates_and_drawings():
    data = _generate()
    assert data["candidates"]
    assert data["best_candidate_id"] == data["candidates"][0]["id"]
    for c in data["candidates"]:
        svgs = data["drawings"][c["id"]]
        assert len(svgs) == c["floors"]
        root = ElementTree.fromstring(svgs[0])
        assert root.tag.endswith("svg")
        assert 'data-room="bedroom_1"' in svgs[0]


def test_generate_from_structured_brief():
    brief = client.post("/api/interpret", json={"prompt": "2 bed apartment 75 m2"}).json()
    brief["rooms"] = [r for r in brief["rooms"] if r["type"] != "bedroom"] + [{"type": "bedroom", "count": 3}]
    brief["target_area_sqm"] = 100
    res = client.post("/api/generate", json={"brief": brief, "count": 3})
    assert res.status_code == 200
    plan = res.json()["candidates"][0]
    assert sum(1 for r in plan["rooms"] if r["type"] == "bedroom") == 3
    assert len(res.json()["candidates"]) <= 3


def test_generate_rejects_bad_input():
    assert client.post("/api/generate", json={}).status_code == 422
    assert client.post("/api/generate", json={"prompt": "   "}).status_code == 422
    assert client.post("/api/generate", json={"prompt": "x" * 3000}).status_code == 422
    bad_brief = {"target_area_sqm": 80, "rooms": [{"type": "bedroom", "count": 0}]}
    assert client.post("/api/generate", json={"brief": bad_brief}).status_code == 422


def test_validate_roundtrip():
    candidate = _generate()["candidates"][0]
    res = client.post("/api/validate", json={"candidate": candidate})
    assert res.status_code == 200 and res.json()["valid"] is True
    candidate["doors"] = [d for d in candidate["doors"] if d["kind"] != "entry"]
    report = client.post("/api/validate", json={"candidate": candidate}).json()
    assert report["valid"] is False
    assert any(i["code"] == "access.entry" for i in report["issues"])


def test_exports():
    candidate = _generate()["candidates"][0]
    for fmt, magic in (("svg", b"<?xml"), ("pdf", b"%PDF"), ("png", b"\x89PNG"), ("dxf", b"  0")):
        res = client.post(f"/api/export/{fmt}", json={"candidate": candidate, "units": "imperial"})
        assert res.status_code == 200, fmt
        assert res.content.startswith(magic), fmt
        assert f"parti-{candidate['id']}.{fmt}" in res.headers["content-disposition"]
    dxf = client.post("/api/export/dxf", json={"candidate": candidate}).content
    doc = ezdxf.read(StringIO(dxf.decode()))
    assert {"A-WALL", "A-DOOR", "A-FURN"} <= {layer.dxf.name for layer in doc.layers}
    assert client.post("/api/export/gif", json={"candidate": candidate}).status_code == 422
