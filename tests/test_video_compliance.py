from __future__ import annotations

from tk_ops_workspace.video_compliance import check_video_compliance


def test_blocks_general_spanish_claims_and_unverified_numbers() -> None:
    report = check_video_compliance(
        fields={
            "script": "Es el mejor, 50% más rápido y funciona en 3 días. Oferta gratis.",
            "tags": "#oferta #wifimoney",
        },
        market="Mexico",
        category="wifi",
    )

    assert report.status == "blocked"
    rule_ids = {match.rule_id for match in report.matches}
    assert "absolute_best" in rule_ids
    assert "numeric_claim_without_pdp" in rule_ids
    assert "promotion_claim" in rule_ids
    assert "misleading_wifi_tag" in rule_ids


def test_supported_numbers_and_verified_promotion_are_allowed() -> None:
    pdp = "Velocidad teórica de 1200 Mbps. Oferta descuento 50% durante la campaña."
    report = check_video_compliance(
        fields={
            "script": "Velocidad teórica de 1200 Mbps. Descuento 50%.",
            "tags": "#oferta",
        },
        market="Mexico",
        category="wifi",
        pdp_text=pdp,
        promotion_verified=True,
        local_representative_confirmed=True,
        aviso_funcionamiento_confirmed=True,
        nom_141_label_confirmed=True,
        aviso_publicidad_confirmed=True,
    )

    assert report.status == "passed"
    assert report.matches == ()


def test_blocks_mexico_cosmetic_ai_visual_risks_and_requires_disclaimer() -> None:
    report = check_video_compliance(
        fields={"script": "Hidrata y deja la piel suave."},
        market="墨西哥",
        category="cosmetics",
        ai_generated=True,
        ai_label_enabled=False,
        visual_flags=("ai_skin_transformation", "doctor_expert", "outdoor"),
    )

    assert report.status == "blocked"
    rule_ids = {match.rule_id for match in report.matches}
    assert {
        "ai_label_missing",
        "ai_skin_transformation",
        "doctor_expert_visual",
        "unsupported_outdoor_scene",
        "cosmetic_effect_disclaimer_missing",
    } <= rule_ids


def test_safe_mexico_cosmetic_copy_can_pass_with_pdp_and_disclaimer() -> None:
    report = check_video_compliance(
        fields={
            "script": (
                "Esta crema tiene una textura ligera, se absorbe rápido y deja la piel suave. "
                "Contiene ácido hialurónico. Los resultados pueden variar."
            ),
            "subtitles": "textura ligera\nse absorbe rápido\nlos resultados pueden variar",
        },
        market="Mexico",
        category="skincare",
        pdp_text="Textura ligera. Se absorbe rápido. Deja la piel suave. Contiene ácido hialurónico.",
        ai_generated=True,
        ai_label_enabled=True,
        local_representative_confirmed=True,
        aviso_funcionamiento_confirmed=True,
        nom_141_label_confirmed=True,
        aviso_publicidad_confirmed=True,
    )

    assert report.status == "passed"
    assert report.matches == ()


def test_cosmetic_whitelist_word_without_pdp_support_is_blocked() -> None:
    report = check_video_compliance(
        fields={"script": "Esta crema hidrata."},
        market="Mexico",
        category="skincare",
        pdp_text="Presentación en frasco.",
        disclaimer_present=True,
        local_representative_confirmed=True,
        aviso_funcionamiento_confirmed=True,
        nom_141_label_confirmed=True,
        aviso_publicidad_confirmed=True,
    )

    assert report.status == "blocked"
    assert any(match.rule_id == "cosmetic_claim_not_in_pdp" for match in report.matches)


def test_mexico_cosmetic_ad_requires_label_disclaimer_age_and_regulatory_readiness() -> None:
    report = check_video_compliance(
        fields={"script": "Presentación del producto."},
        market="Mexico",
        category="beauty",
        ai_generated=True,
        advertisement=True,
    )

    rule_ids = {match.rule_id for match in report.matches}
    assert {
        "ai_label_missing",
        "ad_ai_disclaimer_missing",
        "beauty_ad_age_targeting_missing",
        "mexico_local_representative_missing",
        "mexico_aviso_funcionamiento_missing",
        "mexico_nom_141_label_missing",
        "mexico_aviso_publicidad_missing",
    } <= rule_ids
