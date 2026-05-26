"""
Run locally:  pytest tests/ -v
Run in Docker: docker compose exec api pytest tests/ -v

"""
import json
import os
import tempfile
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

# Override DB and RDF paths to temp locations BEFORE importing the app
_tmp_dir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp_dir, "test.db")
os.environ["RDF_OUTPUT_DIR"] = os.path.join(_tmp_dir, "rdf")
os.makedirs(os.environ["RDF_OUTPUT_DIR"], exist_ok=True)

from app.main import app  # noqa: E402

SAMPLE_PAYLOAD_PATH = Path(__file__).parent / "sample_payload.json"


@pytest.fixture(scope="module")
def sample_payload() -> dict:
    with open(SAMPLE_PAYLOAD_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
async def client():
    # lifespan=True triggers the FastAPI startup (init_db + load shapes)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Manually trigger lifespan
        from app.database import init_db
        from app.rdf_utils import load_shacl_shapes
        import app.main as main_module
        init_db()
        main_module._shapes_graph = load_shacl_shapes()
        yield ac


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


async def test_post_technology_valid(client, sample_payload):
    resp = await client.post("/technologies", json=sample_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "id" in data
    assert "llm_context" in data
    assert "ttl_url" in data
    assert "LSM 980" in data["llm_context"]
    assert data["facility_country"] == "FI"


async def test_post_technology_invalid_missing_required(client):
    bad_payload = {"description": "test", "technology_type": "light_microscopy"}
    resp = await client.post("/technologies", json=bad_payload)
    assert resp.status_code == 422


async def test_get_technology_by_id(client, sample_payload):
    resp = await client.post("/technologies", json=sample_payload)
    assert resp.status_code == 201
    record_id = resp.json()["id"]

    resp2 = await client.get(f"/technologies/{record_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["id"] == record_id
    assert data["name"] == sample_payload["name"]


async def test_get_all_technologies(client):
    resp = await client.get("/technologies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test_search(client, sample_payload):
    await client.post("/technologies", json=sample_payload)
    resp = await client.get("/search", params={"q": "confocal"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] >= 1
    assert any("confocal" in r["llm_context"].lower() for r in data["results"])


async def test_get_ttl(client, sample_payload):
    resp = await client.post("/technologies", json=sample_payload)
    assert resp.status_code == 201
    record_id = resp.json()["id"]

    ttl_resp = await client.get(f"/technologies/{record_id}/ttl")
    assert ttl_resp.status_code == 200
    assert "text/turtle" in ttl_resp.headers["content-type"]
    body = ttl_resp.text
    assert "ImagingTechnology" in body


async def test_get_context(client):
    resp = await client.get("/context")
    assert resp.status_code == 200
    assert "application/ld+json" in resp.headers["content-type"]
    data = resp.json()
    assert "@context" in data


async def test_get_technology_not_found(client):
    resp = await client.get("/technologies/nonexistent-uuid-0000")
    assert resp.status_code == 404


async def test_search_no_results(client):
    resp = await client.get("/search", params={"q": "zzznomatchzzz"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 0


async def test_pagination(client, sample_payload):
    for _ in range(3):
        await client.post("/technologies", json=sample_payload)
    resp = await client.get("/technologies", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2
