from enum import StrEnum


class TechnologyType(StrEnum):
    light_microscopy = "light_microscopy"
    electron_microscopy = "electron_microscopy"
    x_ray_imaging = "x_ray_imaging"
    mri = "mri"
    ultrasound = "ultrasound"
    flow_cytometry = "flow_cytometry"
    super_resolution = "super_resolution"
    atomic_force_microscopy = "atomic_force_microscopy"
    optical_coherence_tomography = "optical_coherence_tomography"
    other = "other"


class SpecimenType(StrEnum):
    fixed_cells = "fixed_cells"
    live_cells = "live_cells"
    tissue_sections = "tissue_sections"
    whole_organism = "whole_organism"
    in_vitro = "in_vitro"
    ex_vivo = "ex_vivo"
    clinical_sample = "clinical_sample"


class AccessType(StrEnum):
    open_access = "open_access"
    fee_for_service = "fee_for_service"
    remote_access = "remote_access"
    restricted = "restricted"


FBBI_TERMS: dict[str, dict] = {
    "confocal microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000251",
        "label": "confocal microscopy",
    },
    "widefield fluorescence microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000246",
        "label": "widefield fluorescence microscopy",
    },
    "TIRF microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000274",
        "label": "total internal reflection fluorescence microscopy",
    },
    "STED microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000253",
        "label": "stimulated emission depletion microscopy",
    },
    "PALM microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000258",
        "label": "photoactivated localization microscopy",
    },
    "STORM microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000257",
        "label": "stochastic optical reconstruction microscopy",
    },
    "transmission electron microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000258",
        "label": "transmission electron microscopy",
    },
    "scanning electron microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000271",
        "label": "scanning electron microscopy",
    },
    "light sheet microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000369",
        "label": "light sheet fluorescence microscopy",
    },
    "two-photon microscopy": {
        "iri": "http://purl.obolibrary.org/obo/FBbi_00000249",
        "label": "two-photon laser scanning microscopy",
    },
}


def build_llm_context(
    name: str,
    technology_type: str,
    modality_label: str | None,
    modality_iri: str | None,
    facility_name: str,
    facility_country: str,
    specimen_types: list[str],
    access_type: str,
    contact_email: str,
    description: str,
) -> str:

    modality_part = ""
    if modality_label and modality_iri:
        fbbi_id = modality_iri.split("/")[-1].replace("_", ":")
        modality_part = f" ({modality_label}, {fbbi_id})"
    elif modality_label:
        modality_part = f" ({modality_label})"

    tech_type_human = technology_type.replace("_", " ")
    specimens_human = ", ".join(s.replace("_", " ") for s in specimen_types)
    access_human = access_type.replace("_", " ")
    country_upper = facility_country.upper()

    context = (
        f"{name} is a {tech_type_human}{modality_part} technology "
        f"offered by {facility_name} in {country_upper}. "
        f"Suitable for: {specimens_human}. "
        f"Access: {access_human}. "
        f"Contact: {contact_email}. "
        f"Description: {description}"
    )
    return context