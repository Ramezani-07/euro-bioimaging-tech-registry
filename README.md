# Euro-BioImaging Technology Registry

## Overview

This repository implements a structured, ontology-aligned registry for imaging technologies offered by Euro-BioImaging Nodes and facilities across Europe. It provides a validated data ingestion pipeline, a REST API, and an RDF/Linked Data layer — serving as a knowledge base fragment for the **AI4Access Research Navigator**, an LLM-based application that guides researchers to the right imaging services across the Euro-BioImaging infrastructure.

The system allows facility staff to submit technology descriptions in a structured way. Each submission is validated at three layers (API schema, controlled vocabulary, SHACL shapes), enriched with an LLM-optimised natural language summary, stored in SQLite, and simultaneously serialised to RDF/Turtle — making every record both query-friendly for humans and machine-interpretable by downstream LLM and semantic web tooling.

---

## Architecture & Design Decisions

### Hybrid SQLite + RDF rather than a triple store

The primary persistence layer is SQLite: it requires no infrastructure, runs inside a single Docker container, supports full-text LIKE search over the `llm_context` field, and is trivially replaceable with PostgreSQL by swapping `database.py`. RDF/Turtle files are written alongside the database as static artefacts — one `.ttl` per record in `/data/rdf/`. This separation is intentional: the SQL layer serves the API's read/write path; the RDF layer serves Linked Data dereferencability and future SPARQL federation. A triple store (GraphDB, Stardog) would be the right choice once the dataset grows to thousands of records and cross-named-graph SPARQL queries become the primary access pattern — this architecture makes that migration straightforward.

### Three-layer validation

Submissions pass through three independent validation gates before being accepted:

1. **Pydantic v2** — enforces field types, required fields, email format, and string length constraints at the HTTP boundary. Fast, returns standard 422 JSON errors.
2. **Controlled vocabularies** — `technology_type`, `access_type`, and `specimen_types` values are checked against the enum definitions in `vocabularies.py`. This ensures semantic consistency across facilities without requiring a full ontology lookup.
3. **SHACL shapes** (`shapes/technology_shape.ttl`) — the submitted record is serialised to RDF and validated against the shape graph using `pyshacl`. This catches semantic inconsistencies that Pydantic cannot. SHACL runs before DB insertion so invalid records are rejected cleanly.
Additionally, when no explicit modality term is provided by the submitter, build_rdf_graph() automatically looks up the technology_type value in a curated FBBI_TERMS dictionary and injects the corresponding FBbi OBO IRI as a dcterms:subject triple. This ensures every technology record carries at least one dereferenceable ontology anchor regardless of how much semantic detail the submitter provides.
### The `llm_context` field

Every stored record carries a pre-composed natural language summary, for example:

> *"LSM 980 Airyscan Confocal is a light microscopy (confocal microscopy, FBbi:00000251) technology offered by Finnish Advanced Microscopy Node (FAMN) in FI. Suitable for: fixed cells, live cells, tissue sections. Access: fee for service. Contact: microscopy@helsinki.fi. Description: ..."*

This field exists because the Research Navigator will use semantic similarity search (embedding-based retrieval) over technology descriptions. Storing a denormalised prose summary — one that redundantly captures technology type, modality, facility, specimens, and access model — maximises recall for a wide range of researcher query phrasings without requiring the Navigator to reconstruct this context from normalised SQL columns at query time. The `llm_context` field is also SHACL-enforced, guaranteeing it is always present in the RDF graph.

### The SHACL shapes file

`shapes/technology_shape.ttl` is the machine-readable contract for what constitutes a valid `ebip:ImagingTechnology` record. It is a SHACL `NodeShape` that targets the `ebip:ImagingTechnology` class and enforces property-level constraints: required fields, cardinality, datatypes, controlled value lists (via `sh:in`), and a regex pattern on contact email. Unlike Pydantic models — which are application-layer constructs — SHACL shapes are portable: any RDF-aware tool (Protégé, TopBraid Composer, a SPARQL endpoint with built-in validation) can validate a technology graph against these shapes independently of this codebase.

### Known limitations and next steps

| Limitation | Next step |
|---|---|
| SQLite LIKE search is not semantic | Replace with a vector store (Weaviate/Qdrant) over `llm_context` embeddings |
| Turtle files on local disk | Move to a named graph in a triple store; expose a SPARQL endpoint |
| No PID minting | Integrate DataCite or Handle.net to assign persistent identifiers to technology records |
| Single-container deployment | Add PostgreSQL service and migrate `database.py`; add Kubernetes manifests |
| No authentication | Add OAuth2/API key middleware before any production exposure |
| SHACL shapes are not versioned | Adopt a SKOS/OWL versioning strategy with `owl:versionInfo` and semantic change tracking |

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| API framework | FastAPI 0.111 | Async, auto-generated OpenAPI docs, Pydantic v2 native |
| Validation (API) | Pydantic v2 | Type-safe, field-level descriptions appear in /docs |
| Validation (RDF) | pyshacl 0.25 | W3C-standard SHACL; portable constraint logic |
| RDF library | RDFLib 7 | De-facto Python RDF; Turtle, JSON-LD, SPARQL support |
| Persistence | SQLite (stdlib) | Zero infrastructure; Docker-volume backed; easy migration path |
| Ontologies | FBbi, EDAM, schema.org, DCTERMS | Domain-standard; stable IRIs; LLM-recognisable |
| Container | Docker + Compose | Single-command startup; volume-isolated data |
| Runtime | Python 3.11 | Match production target; pattern-match syntax |
| Tests | pytest + httpx AsyncClient | In-process; no live server required |

---

## Getting Started

### Prerequisites

- Docker ≥ 24.0 and Docker Compose v2 (`docker compose` not `docker-compose`)
- OR Python 3.11 for local development

### Run with Docker (recommended)

```bash
# Clone the repository
git clone https://github.com/Ramezani-07/euro-bioimaging-tech-registry
cd euro-bioimaging-tech-registry

# Build and start
docker compose up --build

# The API is now available at http://localhost:8000
# Interactive docs: http://localhost:8000/docs
```

Data is persisted in a named Docker volume (`tech_data`). It survives `docker compose down` but is removed by `docker compose down -v`.

### Run locally (development)

```bash
# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create local data directories
mkdir -p data/rdf

# Set environment variables
export DB_PATH=./data/technologies.db
export RDF_OUTPUT_DIR=./data/rdf

# Start the API
uvicorn app.main:app --reload --port 8000
```

---

## API Reference

| Method | Path | Description | Example |
|---|---|---|---|
| `POST` | `/technologies` | Register a new imaging technology | `curl -X POST .../technologies -d @tests/sample_payload.json` |
| `GET` | `/technologies` | Paginated list of all technologies | `curl ".../technologies?limit=10&offset=0"` |
| `GET` | `/technologies/{id}` | Single technology by UUID | `curl .../technologies/abc-123` |
| `GET` | `/technologies/{id}/ttl` | RDF/Turtle representation | `curl -H "Accept: text/turtle" .../technologies/abc-123/ttl` |
| `GET` | `/search?q=...` | Keyword search over all fields | `curl ".../search?q=confocal"` |
| `GET` | `/context` | JSON-LD @context document | `curl .../context` |
| `GET` | `/health` | Health check + record count | `curl .../health` |
| `GET` | `/docs` | Interactive OpenAPI UI | Open in browser |

### Content Negotiation

`GET /technologies/{id}` supports content negotiation via the `Accept` header:

| Accept Header | Response Format |
|---|---|
| `application/json` (default) | Standard JSON response |
| `application/ld+json` | Compacted JSON-LD with `@context` embedded |

```bash
# JSON-LD representation
curl -H "Accept: application/ld+json" \
  http://localhost:8000/technologies/<id> | python3 -m json.tool
```

The raw `@context` document mapping all field names to semantic IRIs is available at `GET /context`.

### Submit a technology

```bash
curl -s -X POST http://localhost:8000/technologies \
  -H "Content-Type: application/json" \
  -d @tests/sample_payload.json | python3 -m json.tool
```

### Retrieve its Turtle representation

```bash
# Replace <id> with the UUID from the POST response
curl -H "Accept: text/turtle" http://localhost:8000/technologies/<id>/ttl
```

---

## Data Model

"The data model below reflects the scope of this prototype. A domain-appropriate model — grounded in Euro-BioImaging's existing metadata standards and informed by the facility data landscape — will be presented separately, along with an ontology that formalises the property mappings between the JSON representation and the RDF layer."

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Human-readable technology/instrument name |
| `description` | string | ✓ | Capability and use-case description (≥10 chars) |
| `technology_type` | enum | ✓ | Primary category (light_microscopy, electron_microscopy, …) |
| `modality_label` | string | — | Specific imaging modality (e.g. confocal microscopy) |
| `modality_iri` | IRI string | — | FBbi or equivalent ontology IRI for the modality |
| `modality_term` | OntologyTerm | — | Structured term with vocabulary, term_id, label, iri |
| `specimen_types` | list[enum] | ✓ | Supported specimen types (fixed_cells, live_cells, …) |
| `access_type` | enum | ✓ | Access model: open_access, fee_for_service, remote_access, restricted |
| `facility_name` | string | ✓ | Full name of the hosting Euro-BioImaging Node or facility |
| `facility_country` | string (ISO) | ✓ | 2-letter ISO 3166-1 country code |
| `contact_email` | email | ✓ | Contact address for this technology |
| `ontology_terms` | list[OntologyTerm] | — | Additional semantic annotations (EDAM, schema.org, etc.) |
| `id` | UUID | auto | Assigned at submission |
| `submitted_at` | datetime | auto | ISO 8601 UTC timestamp |
| `llm_context` | string | auto | Pre-composed natural language summary for LLM retrieval |
| `ttl_url` | URL | auto | URL to the RDF/Turtle endpoint for this record |

---

## Ontology & Controlled Vocabularies

- **FBbi** (Biological Imaging Methods Ontology) — modality IRIs, e.g. `FBbi:00000251` for confocal microscopy. Source: `http://purl.obolibrary.org/obo/fbbi.owl`
- **EDAM** — bioinformatics operation and data type terms, e.g. `operation_3552` for microscopy image analysis
- **schema.org** — facility contact points (`schema:contactPoint`), names, descriptions, spatial coverage
- **DCTERMS** — creation dates (`dcterms:created`), subject links to ontology terms (`dcterms:subject`)
- **Custom EBI namespace** (`https://data.eurobioimaging.eu/ontology/`) — domain-specific properties: `ebip:ImagingTechnology`, `ebip:facilityName`, `ebip:accessType`, `ebip:specimenType`, `ebip:llmContext`

---

## Testing

```bash
# Inside Docker
docker compose exec api pytest tests/ -v

# Locally (with venv active and env vars set)
pytest tests/ -v
```

Tests use `httpx.AsyncClient` with `ASGITransport` — no live server required. A temporary SQLite database and RDF directory are created per test session via `tempfile.mkdtemp()`.

---

## Repository Structure

```
eurobioimaging-tech-registry/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, all route handlers, lifespan
│   ├── models.py        # Pydantic v2 request/response models
│   ├── database.py      # SQLite persistence (stdlib sqlite3)
│   ├── rdf_utils.py     # RDFLib graph construction, SHACL validation, Turtle I/O
│   └── vocabularies.py  # Enums, FBbi term map, build_llm_context()
├── shapes/
│   └── technology_shape.ttl  # SHACL NodeShape for ebip:ImagingTechnology
├── ontology/
│   └── context.jsonld   # JSON-LD @context mapping fields to semantic IRIs
├── tests/
│   ├── test_api.py      # pytest async integration tests
│   └── sample_payload.json  # Realistic POST body (Finnish confocal node)
├── data/                # Runtime only — not committed (SQLite DB + Turtle files)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```
