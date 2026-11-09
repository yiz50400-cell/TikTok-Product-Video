"""Validate customer-provided reference descriptions without network access."""

RELATIONSHIPS = {
    "same_product_candidate": {"same_product_family"},
    "different_product_structure_reference": {"different_or_unverified_product"},
}
USE_SCOPES = {
    "material_candidate_and_structure",
    "structure_only",
}
EVIDENCE_SCOPES = {"visual_structure_only", "reference_text_adaptation"}
TRANSCRIPTION_STATUSES = {"unavailable", "provided", "verified"}


def validate_reference_package(package: dict) -> None:
    if not isinstance(package, dict) or package.get("schema_version") != 1:
        raise ValueError("reference package schema_version must be 1")
    product = package.get("product")
    if not isinstance(product, dict) or not product.get("name"):
        raise ValueError("reference package product.name is required")
    if package.get("market") not in {"MX", "BR", "ID", "PH"}:
        raise ValueError("reference package market is invalid")
    references = package.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("reference package needs references")
    seen = set()
    for item in references:
        if not isinstance(item, dict):
            raise ValueError("reference must be an object")
        candidate_id = item.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError("reference candidate_id is required")
        if candidate_id in seen:
            raise ValueError("reference candidate_id must be unique")
        seen.add(candidate_id)
        relationship = item.get("relationship")
        if relationship not in RELATIONSHIPS:
            raise ValueError("reference relationship is required")
        if item.get("use_scope") not in USE_SCOPES:
            raise ValueError("reference use_scope is required")
        if item.get("evidence_scope") not in EVIDENCE_SCOPES:
            raise ValueError("reference evidence_scope is required")
        if item.get("transcription_status") not in TRANSCRIPTION_STATUSES:
            raise ValueError("reference transcription_status is invalid")
        for field in ("hook", "buyer_concern", "proof", "objection_or_turn", "cta"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"reference {field} is required")
        if relationship == "different_product_structure_reference" and item["use_scope"] != "structure_only":
            raise ValueError("different-product reference must be structure_only")
