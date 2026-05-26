"""
OntologyTerm as a nested model (rather than flat strings) keeps the term_id,
label, and IRI co-located and individually validatable. The ttl_url field in
TechnologyResponse turns every record into a self-describing resource — a client
can discover the RDF representation of any record from the JSON response alone,
which is the core Linked Data principle applied to a REST API.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Annotated
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, BeforeValidator


class OntologyTerm(BaseModel):

    vocabulary: str = Field(
        description="Short name of the source vocabulary, e.g. 'FBbi', 'EDAM', 'schema.org'",
        examples=["FBbi"],
    )
    term_id: str = Field(
        description="Local identifier within the vocabulary, e.g. 'FBbi:00000251'",
        examples=["FBbi:00000251"],
    )
    label: str = Field(
        description="Human-readable label for the term",
        examples=["confocal microscopy"],
    )
    iri: HttpUrl = Field(
        description="Full IRI of the ontology term",
        examples=["http://purl.obolibrary.org/obo/FBbi_00000251"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vocabulary": "FBbi",
                "term_id": "FBbi:00000251",
                "label": "confocal microscopy",
                "iri": "http://purl.obolibrary.org/obo/FBbi_00000251",
            }
        }
    )


def to_uppercase(v: str) -> str:
    return v.upper() if isinstance(v, str) else v


class TechnologyCreate(BaseModel):
    """
    POST body for registering an imaging technology.
    All fields are described so they appear in the auto-generated OpenAPI /docs UI,
    making the API self-documenting for facility staff without additional training.
    """

    name: str = Field(
        min_length=2,
        max_length=200,
        description="Human-readable name for the imaging technology or instrument",
        examples=["LSM 980 Airyscan Confocal"],
    )
    description: str = Field(
        min_length=10,
        description=(
            "Detailed description of the technology, its capabilities, "
            "and typical use cases"
        ),
        examples=[
            "A laser scanning confocal microscope with Airyscan detector enabling "
            "super-resolution imaging of fixed and live biological specimens."
        ],
    )
    technology_type: str = Field(
        description=(
            "Primary technology category. Must be one of the controlled vocabulary values: "
            "light_microscopy, electron_microscopy, x_ray_imaging, mri, ultrasound, "
            "flow_cytometry, super_resolution, atomic_force_microscopy, "
            "optical_coherence_tomography, other"
        ),
        examples=["light_microscopy"],
    )
    modality_label: Optional[str] = Field(
        default=None,
        description="Specific imaging modality label, ideally from FBbi ontology",
        examples=["confocal microscopy"],
    )
    modality_iri: Optional[str] = Field(
        default=None,
        description="FBbi or other ontology IRI for the imaging modality",
        examples=["http://purl.obolibrary.org/obo/FBbi_00000251"],
    )
    modality_term: Optional[OntologyTerm] = Field(
        default=None,
        description="Structured ontology term reference for the primary imaging modality",
    )
    specimen_types: list[str] = Field(
        min_length=1,
        description=(
            "List of specimen types supported. Allowed values: "
            "fixed_cells, live_cells, tissue_sections, whole_organism, "
            "in_vitro, ex_vivo, clinical_sample"
        ),
        examples=[["fixed_cells", "live_cells"]],
    )
    access_type: str = Field(
        description=(
            "Access model for this technology. Must be one of: "
            "open_access, fee_for_service, remote_access, restricted"
        ),
        examples=["fee_for_service"],
    )
    facility_name: str = Field(
        min_length=2,
        max_length=300,
        description="Full name of the hosting Euro-BioImaging facility or Node",
        examples=["Finnish Advanced Microscopy Node (FAMN)"],
    )
    facility_country: Annotated[
        str,
        BeforeValidator(to_uppercase),
        Field(
            min_length=2,
            max_length=2,
            description="ISO 3166-1 alpha-2 country code",
            examples=["FI"],
        )
    ]
    contact_email: EmailStr = Field(
        description="Contact email address for this technology or facility",
        examples=["microscopy@helsinki.fi"],
    )
    ontology_terms: list[OntologyTerm] = Field(
        default_factory=list,
        description=(
            "Additional ontology term references (e.g. EDAM operations, schema.org types) "
            "beyond the primary modality term"
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "LSM 980 Airyscan Confocal",
                "description": (
                    "Zeiss LSM 980 with Airyscan 2 detector enabling super-resolution "
                    "confocal imaging at 1.7x improved resolution. Suitable for live-cell "
                    "time-lapse and fixed multi-channel fluorescence imaging."
                ),
                "technology_type": "light_microscopy",
                "modality_label": "confocal microscopy",
                "modality_iri": "http://purl.obolibrary.org/obo/FBbi_00000251",
                "modality_term": {
                    "vocabulary": "FBbi",
                    "term_id": "FBbi:00000251",
                    "label": "confocal microscopy",
                    "iri": "http://purl.obolibrary.org/obo/FBbi_00000251",
                },
                "specimen_types": ["fixed_cells", "live_cells"],
                "access_type": "fee_for_service",
                "facility_name": "Finnish Advanced Microscopy Node (FAMN)",
                "facility_country": "FI",
                "contact_email": "microscopy@helsinki.fi",
                "ontology_terms": [
                    {
                        "vocabulary": "EDAM",
                        "term_id": "operation_3552",
                        "label": "Microscopy image analysis",
                        "iri": "http://edamontology.org/operation_3552",
                    }
                ],
            }
        }
    )


class TechnologyResponse(TechnologyCreate):
    """
    GET response model — extends TechnologyCreate with server-assigned fields.
    ttl_url is the URL at which the RDF/Turtle representation of this record is served,
    implementing the Linked Data principle that every resource should be dereferenceable.
    """

    id: str = Field(description="UUID assigned at submission time")
    submitted_at: datetime = Field(description="ISO 8601 timestamp of submission")
    llm_context: str = Field(
        description=(
            "Pre-composed natural language context string, optimised for LLM ingestion "
            "and semantic similarity search in the Research Navigator"
        )
    )
    ttl_url: str = Field(
        description="URL to retrieve this record's RDF/Turtle representation"
    )

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Paginated search result wrapper."""

    query: str
    total_count: int
    results: list[TechnologyResponse]


class SHACLValidationError(BaseModel):
    """Returned when a submitted technology fails SHACL shape validation."""

    detail: str = "SHACL validation failed"
    shacl_report: str = Field(
        description="Full SHACL validation report text identifying which constraints were violated"
    )
