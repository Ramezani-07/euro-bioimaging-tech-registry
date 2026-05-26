"""
Namespace design: we mint a custom EBI namespace for Euro-BioImaging-specific
properties (ebi:ImagingTechnology, ebi:facilityName, etc.) rather than overloading
schema.org. dcterms:subject is used for ontology term links (modality IRI,
additional terms) because it is the established Dublin Core property for
'classification' and is well-understood by RDF consumers and SPARQL engines alike.
SHACL validation runs against the loaded shapes graph before DB insertion so
that any constraint violation is caught at the API layer, not discovered later
during graph consumption.
"""
import os
from pathlib import Path
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, XSD
import pyshacl

# ── Namespace declarations ──────────────────────────────────────────────────
EBI = Namespace("https://data.eurobioimaging.eu/technology/")
EBI_PROP = Namespace("https://data.eurobioimaging.eu/ontology/")
SCHEMA = Namespace("https://schema.org/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
FBBI = Namespace("http://purl.obolibrary.org/obo/")

SHAPES_PATH = Path(__file__).parent.parent / "shapes" / "technology_shape.ttl"
RDF_OUTPUT_DIR = os.environ.get("RDF_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "rdf"))


def build_rdf_graph(record: dict) -> Graph:
    """
    The technology URI follows the pattern EBI:{id}, making each record
    independently addressable as a Linked Data resource. We assert both
    schema:Thing and the custom ebi:ImagingTechnology class so the graph
    is compatible with schema.org-aware tooling and with our own SHACL shapes.
    """
    g = Graph()

    # Bind prefixes for readable Turtle serialisation
    g.bind("ebi", EBI)
    g.bind("ebip", EBI_PROP)
    g.bind("schema", SCHEMA)
    g.bind("dcat", DCAT)
    g.bind("dcterms", DCTERMS)
    g.bind("fbbi", FBBI)
    g.bind("xsd", XSD)

    tech_uri = EBI[record["id"]]

    # ── Type assertions ──────────────────────────────────────────────────────
    g.add((tech_uri, RDF.type, SCHEMA.Thing))
    g.add((tech_uri, RDF.type, EBI_PROP.ImagingTechnology))

    # ── Core descriptive properties ──────────────────────────────────────────
    g.add((tech_uri, SCHEMA.name, Literal(record["name"], datatype=XSD.string)))
    g.add((tech_uri, SCHEMA.description, Literal(record["description"], datatype=XSD.string)))

    if record.get("submitted_at"):
        g.add((tech_uri, DCTERMS.created, Literal(record["submitted_at"], datatype=XSD.dateTime)))

    # ── Facility and access properties ───────────────────────────────────────
    g.add((tech_uri, EBI_PROP.facilityName, Literal(record["facility_name"], datatype=XSD.string)))
    g.add((tech_uri, EBI_PROP.facilityCountry, Literal(record["facility_country"], datatype=XSD.string)))
    g.add((tech_uri, EBI_PROP.accessType, Literal(record["access_type"], datatype=XSD.string)))
    g.add((tech_uri, EBI_PROP.technologyType, Literal(record["technology_type"], datatype=XSD.string)))

    # ── Contact point ────────────────────────────────────────────────────────
    contact_node = EBI[f"{record['id']}/contact"]
    g.add((tech_uri, SCHEMA.contactPoint, contact_node))
    g.add((contact_node, RDF.type, SCHEMA.ContactPoint))
    g.add((contact_node, SCHEMA.email, Literal(record["contact_email"], datatype=XSD.string)))

    # ── Spatial coverage (country) ────────────────────────────────────────────
    g.add((tech_uri, SCHEMA.spatialCoverage, Literal(record["facility_country"], datatype=XSD.string)))

    # ── Specimen types ────────────────────────────────────────────────────────
    specimen_types = record.get("specimen_types", [])
    if isinstance(specimen_types, str):
        import json
        specimen_types = json.loads(specimen_types)
    for specimen in specimen_types:
        g.add((tech_uri, EBI_PROP.specimenType, Literal(specimen, datatype=XSD.string)))
    '''''
    # ── modality term ────────────────────────────────────────────────────────
    modality_term = record.get("modality_term", [])
    if isinstance(modality_term, str):
        import json
        modality_term = json.loads(modality_term)
    for modality in modality_term:
        g.add((tech_uri, EBI_PROP.modalityTerm, Literal(modality, datatype=XSD.string)))
    '''''
    # ── Primary modality (FBbi link) ──────────────────────────────────────────
    if record.get("modality_iri"):
        modality_ref = URIRef(record["modality_iri"])
        g.add((tech_uri, DCTERMS.subject, modality_ref))
        if record.get("modality_label"):
            g.add((modality_ref, RDFS.label, Literal(record["modality_label"])))

    # ── Additional ontology terms ─────────────────────────────────────────────
    ontology_terms = record.get("ontology_terms", [])
    if isinstance(ontology_terms, str):
        import json
        ontology_terms = json.loads(ontology_terms)
    for term in ontology_terms:
        if isinstance(term, dict) and term.get("iri"):
            term_uri = URIRef(str(term["iri"]))
            g.add((tech_uri, DCTERMS.subject, term_uri))
            if term.get("label"):
                g.add((term_uri, RDFS.label, Literal(term["label"])))

    # ── LLM context literal ────────────────────────────────────────────────────
    # This is the key differentiator: a pre-composed retrieval surface stored
    # directly in the graph for LLM-friendly SPARQL queries.
    g.add((tech_uri, EBI_PROP.llmContext, Literal(record["llm_context"], datatype=XSD.string)))

    return g


def serialise_to_turtle(graph: Graph) -> str:
    """Serialise an RDFLib graph to a Turtle string."""
    return graph.serialize(format="turtle")


def serialise_to_jsonld(graph: Graph) -> str:
    """Serialise an RDFLib graph to a JSON-LD string."""
    return graph.serialize(format="json-ld", indent=2)


def save_ttl_file(graph: Graph, record_id: str) -> str:
    """
    Write the Turtle serialisation to /data/rdf/{id}.ttl and return the path.
    The output directory is created if it does not exist (handles cold starts).
    """
    os.makedirs(RDF_OUTPUT_DIR, exist_ok=True)
    ttl_path = os.path.join(RDF_OUTPUT_DIR, f"{record_id}.ttl")
    turtle_str = serialise_to_turtle(graph)
    with open(ttl_path, "w", encoding="utf-8") as f:
        f.write(turtle_str)
    return ttl_path


def load_shacl_shapes() -> Graph:
    """Load the SHACL shapes graph from the bundled shapes/technology_shape.ttl file."""
    shapes_graph = Graph()
    shapes_graph.parse(str(SHAPES_PATH), format="turtle")
    return shapes_graph


def validate_with_shacl(
    data_graph: Graph, shapes_graph: Graph
) -> tuple[bool, str]:
    """
    Run pyshacl validation of data_graph against shapes_graph.

    Returns (conforms: bool, report_text: str).
    conforms=True means all SHACL constraints pass; False means at least one
    sh:PropertyShape constraint was violated. The report_text is the human-readable
    SHACL validation report serialised as plain text.
    """
    conforms, results_graph, results_text = pyshacl.validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    return conforms, results_text
