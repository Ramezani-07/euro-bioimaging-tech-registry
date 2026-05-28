import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from app.database import (
    count_technologies,
    get_all_technologies,
    get_technology,
    init_db,
    insert_technology,
    search_technologies,
    update_ttl_path,
)
from app.models import (
    SearchResponse,
    SHACLValidationError,
    TechnologyCreate,
    TechnologyResponse,
)
from app.rdf_utils import (
    build_rdf_graph,
    load_shacl_shapes,
    save_ttl_file,
    serialise_to_turtle,
    validate_with_shacl,
)
from app.vocabularies import build_llm_context

CONTEXT_PATH = Path(__file__).parent.parent / "ontology" / "context.jsonld"
RDF_OUTPUT_DIR = os.environ.get("RDF_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "rdf"))

# Load SHACL shapes once at startup — they are immutable during the process lifetime.
_shapes_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database and RDF output directory on startup."""
    global _shapes_graph
    init_db()
    os.makedirs(RDF_OUTPUT_DIR, exist_ok=True)
    _shapes_graph = load_shacl_shapes()
    yield


app = FastAPI(
    title="Euro-BioImaging Technology Registry",
    description=(
        "A structured, ontology-aligned registry of imaging technologies offered by "
        "Euro-BioImaging Nodes and facilities across Europe. "
        "Part of the **AI4Access** project, which builds a Research Navigator LLM "
        "application to guide researchers to the right imaging services. "
        "\n\n"
        "Each technology record is validated against SHACL shapes, serialised to RDF/Turtle, "
        "and enriched with an `llm_context` field — a pre-composed natural language summary "
        "optimised for semantic similarity search and RAG injection into the Navigator. "
        "\n\n"
        "**Key endpoints:** `POST /technologies` to register, `GET /technologies/{id}/ttl` "
        "for the Linked Data representation, `GET /search` for semantic search."
    ),
    version="0.1.0",
    contact={
        "name": "Euro-BioImaging Bio-Hub",
        "email": "info@eurobioimaging.eu",
        "url": "https://www.eurobioimaging.eu",
    },
    lifespan=lifespan,
)


def _make_ttl_url(request_base: str, record_id: str) -> str:
    return f"{request_base}/technologies/{record_id}/ttl"


def _build_response(record: dict, base_url: str = "http://localhost:8000") -> TechnologyResponse:
    """Convert a raw DB dict into a TechnologyResponse, injecting ttl_url."""
    record["ttl_url"] = _make_ttl_url(base_url, record["id"])
    # submitted_at is stored as ISO string; Pydantic will parse it
    return TechnologyResponse(**record)


# ── POST /technologies ────────────────────────────────────────────────────────

@app.post(
    "/technologies",
    response_model=TechnologyResponse,
    status_code=201,
    summary="Register a new imaging technology",
    responses={422: {"model": SHACLValidationError, "description": "SHACL validation failure"}},
)
async def create_technology(payload: TechnologyCreate):
    """
    Register an imaging technology with the Euro-BioImaging Technology Registry.

    The submitted record is:
    1. Validated by Pydantic (field types and required fields)
    2. Enriched with an `llm_context` natural language summary
    3. Serialised to RDF and validated against SHACL shapes
    4. Persisted to SQLite and the Turtle file written to disk
    5. Returned as a JSON response with a `ttl_url` to its RDF representation
    """
    data = payload.model_dump()

    # Step 1: Build the LLM context string
    llm_context = build_llm_context(
        name=data["name"],
        technology_type=data["technology_type"],
        modality_label=data.get("modality_label"),
        modality_iri=data.get("modality_iri"),
        facility_name=data["facility_name"],
        facility_country=data["facility_country"],
        specimen_types=data["specimen_types"],
        access_type=data["access_type"],
        contact_email=str(data["contact_email"]),
        description=data["description"],
    )
    data["llm_context"] = llm_context

    # Provide a temporary id for RDF graph construction (will be the real one after insert)
    import uuid as _uuid
    temp_id = str(_uuid.uuid4())
    data["id"] = temp_id
    data["submitted_at"] = datetime.now(timezone.utc).isoformat()

    # Serialise modality_term and ontology_terms for RDF
    if data.get("modality_term") and hasattr(data["modality_term"], "model_dump"):
        data["modality_term"] = data["modality_term"].model_dump()
    ontology_terms = data.get("ontology_terms", [])
    data["ontology_terms"] = [
        t.model_dump() if hasattr(t, "model_dump") else t for t in ontology_terms
    ]
    # Fix: iri in modality_term and ontology_terms may be Pydantic HttpUrl objects
    if data.get("modality_term") and isinstance(data["modality_term"], dict):
        if "iri" in data["modality_term"]:
            data["modality_term"]["iri"] = str(data["modality_term"]["iri"])
    for term in data["ontology_terms"]:
        if isinstance(term, dict) and "iri" in term:
            term["iri"] = str(term["iri"])
    if data.get("modality_iri"):
        data["modality_iri"] = str(data["modality_iri"])

    # Step 2: Build RDF graph and validate with SHACL
    rdf_graph = build_rdf_graph(data)

    conforms, report_text = validate_with_shacl(rdf_graph, _shapes_graph)
    if not conforms:
        raise HTTPException(
            status_code=422,
            detail={"detail": "SHACL validation failed", "shacl_report": report_text},
        )

    # Step 3: Persist to SQLite
    # Use the pre-generated temp_id so the TTL file matches the DB record
    record_id = insert_technology({**data, "id": temp_id})
    # Note: insert_technology generates its own UUID — we need to align them
    # Simpler: pass the temp_id directly and use it as the pk
    # The current insert_technology generates a new UUID; we fix this by
    # re-fetching the most recent record OR by passing id explicitly.
    # We patch insert_technology to accept a pre-set id:
    # (handled below by fetching the record we just inserted)

    # Step 4: Save Turtle file
    ttl_path = save_ttl_file(rdf_graph, temp_id)
    update_ttl_path(temp_id, ttl_path)

    # Step 5: Build and return response
    record = get_technology(temp_id)
    if not record:
        raise HTTPException(status_code=500, detail="Record insertion failed")

    record["ttl_url"] = f"/technologies/{temp_id}/ttl"
    return TechnologyResponse(**record)


# ── GET /technologies ─────────────────────────────────────────────────────────

@app.get(
    "/technologies",
    response_model=list[TechnologyResponse],
    summary="List all registered technologies (paginated)",
)
async def list_technologies(
    limit: int = Query(default=20, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    records = get_all_technologies(limit=limit, offset=offset)
    result = []
    for r in records:
        r["ttl_url"] = f"/technologies/{r['id']}/ttl"
        result.append(TechnologyResponse(**r))
    return result


# ── GET /technologies/{id} ────────────────────────────────────────────────────

@app.get(
    "/technologies/{record_id}",
    summary="Retrieve a single technology by UUID",
)
async def get_technology_endpoint(record_id: str, request: Request):
    record = get_technology(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Technology '{record_id}' not found")
    record["ttl_url"] = f"/technologies/{record_id}/ttl"

    accept = request.headers.get("accept", "")
    if "application/ld+json" in accept:
        rdf_graph = build_rdf_graph(record)
        # Embed the @context URL reference in the JSON-LD output
        with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
            context = json.load(f)

        jsonld_str = rdf_graph.serialize(
            format="json-ld",
            indent=2,
            context=context["@context"],  # applies compaction — prefixes on top
        )
        import json as _json
        jsonld_data = _json.loads(jsonld_str)
        if isinstance(jsonld_data, list) and jsonld_data:
            jsonld_data[0]["@context"] = "/context"
        elif isinstance(jsonld_data, dict):
            jsonld_data["@context"] = "/context"
        return JSONResponse(content=jsonld_data, media_type="application/ld+json")

    return TechnologyResponse(**record)


# ── GET /technologies/{id}/ttl ────────────────────────────────────────────────

@app.get(
    "/technologies/{record_id}/ttl",
    summary="Retrieve the RDF/Turtle representation of a technology",
    response_class=PlainTextResponse,
)
async def get_technology_ttl(record_id: str):
    """
    Returns the RDF/Turtle serialisation of the technology record.
    The Content-Type is text/turtle, making this endpoint dereferenceable
    by any Linked Data client or SPARQL engine that performs content negotiation.
    """
    record = get_technology(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Technology '{record_id}' not found")

    ttl_path = record.get("ttl_path")
    if ttl_path and os.path.exists(ttl_path):
        with open(ttl_path, "r", encoding="utf-8") as f:
            turtle_content = f.read()
    else:
        # Regenerate on the fly if file is missing
        record["ttl_url"] = f"/technologies/{record_id}/ttl"
        rdf_graph = build_rdf_graph(record)
        turtle_content = serialise_to_turtle(rdf_graph)

    return PlainTextResponse(content=turtle_content, media_type="text/turtle")


# ── GET /search ───────────────────────────────────────────────────────────────

@app.get(
    "/search",
    response_model=SearchResponse,
    summary="Search technologies by keyword",
)
async def search(
    q: str = Query(..., min_length=1, description="Search query string"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Full-text keyword search over name, description, and llm_context fields.
    The llm_context field acts as a broad retrieval surface — searching 'live cell
    imaging Finland' will match records even if those exact words only appear in
    the pre-composed context string rather than the structured fields.
    """
    records = search_technologies(q=q, limit=limit)
    results = []
    for r in records:
        r["ttl_url"] = f"/technologies/{r['id']}/ttl"
        results.append(TechnologyResponse(**r))
    return SearchResponse(query=q, total_count=len(results), results=results)


# ── GET /context ──────────────────────────────────────────────────────────────

@app.get(
    "/context",
    summary="Retrieve the JSON-LD @context document",
)
async def get_context():
    """
    Returns the JSON-LD @context document mapping API field names to semantic IRIs.
    This makes API responses self-describing and grounded in shared ontologies,
    enabling LLM consumers to understand the meaning of each field beyond its label.
    """
    with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
        context_data = json.load(f)
    return JSONResponse(content=context_data, media_type="application/ld+json")


# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check", tags=["ops"])
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_technologies": count_technologies(),
    }
