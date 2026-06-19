"""End-to-end API test: generate → ingest → recon → check endpoints."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_full_pipeline():
    r = client.post("/generate?seed=42")
    assert r.status_code == 200
    assert r.json()["txns_generated"] == 1000

    r = client.post("/settlements/ingest")
    assert r.status_code == 200
    assert r.json()["settlement_lines_ingested"] > 900

    r = client.post("/recon/run")
    assert r.status_code == 200
    data = r.json()["recon_results"]
    assert data["MATCHED"] > 0

    r = client.get("/recon/exceptions")
    assert r.status_code == 200
    assert len(r.json()) > 0

    r = client.get("/float/daily")
    assert r.status_code == 200
    floats = r.json()
    assert len(floats) > 0
    assert any(f["float_paise"] < 0 for f in floats)

    r = client.get("/ledger/balance")
    assert r.status_code == 200
    bal = r.json()
    assert bal["balanced"] is True
    assert bal["total"] == 0
