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


def _rule_ids(report) -> set[str]:
    return {match.rule_id for match in report.matches}


def test_blocks_portuguese_exaggerations_for_brazil() -> None:
    report = check_video_compliance(
        fields={"script": "O melhor creme do mercado, garantido! Sempre funciona. Grátis hoje."},
        market="Brazil",
        category="general",
    )
    assert report.status == "blocked"
    assert {"absolute_best", "absolute_guarantee", "absolute_always_never", "promotion_claim"} <= (
        _rule_ids(report)
    )
    assert report.checks["market_family"] == "brazil"


def test_blocks_indonesian_exaggerations_for_indonesia() -> None:
    report = check_video_compliance(
        fields={"script": "Produk terbaik nomor satu, dijamin! Menyembuhkan jerawat, diskon hari ini."},
        market="印尼",
        category="general",
    )
    assert report.status == "blocked"
    assert {"absolute_best", "absolute_guarantee", "medical_treatment", "promotion_claim"} <= (
        _rule_ids(report)
    )


def test_review_reproduction_mixed_pt_id_copy_is_blocked_in_all_markets() -> None:
    text = "O melhor produto, garantido. Produk terbaik, dijamin."
    for market in ("Mexico", "Brazil", "Indonesia"):
        ids = _rule_ids(check_video_compliance(fields={"script": text}, market=market, category="general"))
        assert {"absolute_best", "absolute_guarantee"} <= ids, market


def test_pt_id_cosmetic_claims_are_blocked() -> None:
    report = check_video_compliance(
        fields={"script": "Clareia a pele e remove manchas. Memutihkan dan awet muda."},
        market="Brazil",
        category="cosmetics",
    )
    assert {"cosmetic_whitening", "cosmetic_spots", "cosmetic_rejuvenation"} <= _rule_ids(report)


def test_neutral_pt_and_id_copy_passes() -> None:
    for market, text in (
        ("Brazil", "Textura leve para o dia a dia. Peça no carrinho."),
        ("Indonesia", "Kopi instan praktis untuk pagi hari. Pesan di keranjang."),
    ):
        report = check_video_compliance(fields={"script": text}, market=market, category="general")
        assert report.status == "passed", (market, report.matches)


def test_unknown_market_is_not_silently_passed() -> None:
    report = check_video_compliance(fields={"script": "Hola"}, market="France", category="general")
    assert report.status == "blocked"
    assert "market_unsupported" in _rule_ids(report)


def test_numeric_units_in_pt_and_id_require_pdp() -> None:
    report = check_video_compliance(
        fields={"script": "Resultado em 7 dias. 3 kali lebih cepat."},
        market="Brazil",
        category="general",
    )
    assert "numeric_claim_without_pdp" in _rule_ids(report)
