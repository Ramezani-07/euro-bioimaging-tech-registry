# test_db.py — run with: python test_db.py
import os, json
os.environ["DB_PATH"] = "/tmp/test_technologies.db"  # use temp file

from app.database import init_db, insert_technology, get_technology, search_technologies

init_db()

record = {
    "name": "Leica SP8 Confocal",
    "description": "Point-scanning confocal for live imaging",
    "technology_type": "confocal_microscopy",
    "modality_term": json.dumps({"vocabulary": "FBbi", "term_id": "FBbi_00000243",
                                  "label": "confocal", "iri": "http://purl.obolibrary.org/obo/FBbi_00000243"}),
    "specimen_types": json.dumps(["fixed_cells", "live_cells"]),
    "access_type": "fee_for_service",
    "facility_name": "Helsinki BioImaging",
    "facility_country": "FI",
    "contact_email": "info@helsinki.fi",
    "ontology_terms": json.dumps([]),
    "llm_context": "Leica SP8 is a confocal microscopy technology at Helsinki BioImaging in Finland.",
    "ttl_path": None,
}

tech_id = insert_technology(record)
print("Inserted with id:", tech_id)

retrieved = get_technology(tech_id)
print("Retrieved:", retrieved)
assert retrieved["name"] == "Leica SP8 Confocal"

results = search_technologies("confocal")
print("Search results:", results, "(should be 1)")

print("ALL TESTS PASSED")