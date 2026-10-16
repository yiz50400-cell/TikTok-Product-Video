from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

COMPLIANCE_RULE_VERSION = "2026-09-v1"
MEXICO_MARKETS = frozenset({"mx", "mexico", "墨西哥", "es-mx", "es_mx"})
COSMETIC_CATEGORIES = (
    "cosmetic",
    "cosmetics",
    "beauty",
    "skincare",
    "makeup",
    "化妆",
    "护肤",
    "彩妆",
)


@dataclass(frozen=True, slots=True)
class ComplianceMatch:
    rule_id: str
    field: str
    matched_text: str
    severity: str
    action: str
    reason: str
    replacement: str = ""


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    rule_version: str
    market: str
    category: str
    status: str
    matches: tuple[ComplianceMatch, ...]
    checks: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["matches"] = [asdict(item) for item in self.matches]
        return payload


@dataclass(frozen=True, slots=True)
class _TextRule:
    rule_id: str
    pattern: str
    reason: str
    action: str = "删除或替换"
    replacement: str = ""
    requires_pdp: bool = False
    requires_promotion_verification: bool = False


GENERAL_RULES = (
    _TextRule(
        "absolute_100_natural_safe",
        r"100%\s*(?:natural|seguro|天然|安全)",
        "绝对化或安全保证",
    ),
    _TextRule(
        "absolute_best",
        r"\bel mejor\b|\bnúmero uno\b|\bel mejor del mercado\b|最好|全网第一",
        "最好或第一的无证据比较",
    ),
    _TextRule("absolute_unique", r"\búnico\b|唯一", "唯一的绝对化表述"),
    _TextRule("absolute_guarantee", r"\bgarantizado\b|保证", "保证性承诺"),
    _TextRule(
        "absolute_always_never",
        r"\bsiempre\b|\bnunca\b|永远|绝不会",
        "绝对化承诺",
    ),
    _TextRule("instant_effect", r"\binstantáneo\b|立刻见效|即时效果", "即时效果承诺"),
    _TextRule(
        "medical_treatment",
        r"\bcura\b|\btrata\b|\bpreviene\b|治疗|治愈|预防疾病",
        "医疗健康宣称",
    ),
    _TextRule(
        "medical_pain_weight",
        r"\balivia el dolor\b|\bbaja de peso\b|\badelgaza\b|缓解疼痛|减肥",
        "医疗或身体功能宣称",
    ),
    _TextRule(
        "medical_symptom",
        r"\belimina\s+[a-záéíóúñ ]{1,32}\b|\b消除症状\b",
        "消除症状的医疗宣称",
    ),
    _TextRule(
        "expert_endorsement",
        r"\bmédico\b|\bdoctor\b|\bdermatólogo\b|医生|皮肤科|白大褂",
        "冒充专家或专业背书",
    ),
    _TextRule(
        "unsupported_endorsement",
        r"\brecomendado por expertos\b|\bresultados clínicos\b|专家推荐|临床结果",
        "无证据的专家或临床背书",
    ),
    _TextRule(
        "regulatory_endorsement",
        r"\baprobado por (?:fda|cofepris)\b|FDA批准|COFEPRIS批准",
        "无证据的监管机构批准宣称",
    ),
    _TextRule(
        "numeric_claim_without_pdp",
        r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*%|\s*(?:por ciento|veces|d[ií]as?|horas?|minutos?|mbps))?",
        "数字、百分比、倍数或时限必须能在 PDP 找到原文",
        action="删除或补充 PDP 原文依据",
        requires_pdp=True,
    ),
    _TextRule(
        "time_claim",
        r"\ben\s+\d+\s+(?:d[ií]as?|horas?|minutos?)\b|在\d+天|约\d+天|[一二三四五六七八九十]+\s*天",
        "时限效果承诺必须有 PDP 原文依据",
        action="删除或补充 PDP 原文依据",
        requires_pdp=True,
    ),
    _TextRule(
        "promotion_claim",
        r"\bgratis\b|\bdescuento(?:\s+\d+%)?\b|\boferta\b|\bpor tiempo limitado\b|\bliquidación\b|\búltima oportunidad\b|免费|五折|限时优惠|清仓|最后机会",
        "促销、赠送或紧迫感必须真实且有 PDP/活动依据",
        action="删除或补充真实活动依据",
        requires_promotion_verification=True,
    ),
    _TextRule(
        "misleading_wifi_tag",
        r"#wifimoney",
        "与商品无关或暗示用 WiFi 赚钱的误导标签",
    ),
    _TextRule(
        "unverified_promo_tag",
        r"#(?:vivalaquincena|descuento|oferta|gratis)\b",
        "无真实促销时不得使用促销标签",
        action="删除或补充真实活动依据",
        requires_promotion_verification=True,
    ),
)

COSMETIC_RULES = (
    _TextRule(
        "cosmetic_acne",
        r"\belimina el acné\b|祛痘",
        "化妆品医疗化功效宣称",
        replacement="hidrata",
    ),
    _TextRule(
        "cosmetic_whitening",
        r"\bblanquea\b|\baclara la piel\b|美白|提亮肤色",
        "化妆品美白或肤色改变宣称",
        replacement="hidrata",
    ),
    _TextRule(
        "cosmetic_spots",
        r"\bquita manchas\b|祛斑|淡斑",
        "化妆品祛斑宣称",
        replacement="deja la piel suave",
    ),
    _TextRule(
        "cosmetic_wrinkles",
        r"\b(?:borra|elimina) las arrugas\b|\bdesaparecen las arrugas\b|去皱|消除皱纹",
        "化妆品去皱宣称",
        replacement="textura ligera",
    ),
    _TextRule(
        "cosmetic_rejuvenation",
        r"\brejuvenece\b|抗衰|逆龄",
        "化妆品抗衰或逆龄宣称",
        replacement="se absorbe rápido",
    ),
    _TextRule(
        "cosmetic_lifting",
        r"\breafirma la piel\b|\befecto lifting\b|紧致提拉|提拉效果",
        "化妆品提拉或紧致宣称",
        replacement="larga duración",
    ),
    _TextRule(
        "cosmetic_perfect_skin",
        r"\bpiel perfecta\b|完美肌肤",
        "化妆品绝对化肤质宣称",
        replacement="deja la piel suave",
    ),
    _TextRule(
        "cosmetic_treatment",
        r"\btratamiento\b|治疗方案|疗程",
        "化妆品医疗暗示",
        replacement="rutina diaria",
    ),
    _TextRule(
        "cosmetic_chemical_free",
        r"\blibre de químicos\b|\bsin tóxicos\b|无化学成分|无毒素",
        "虚假或绝对化成分安全宣称",
    ),
    _TextRule(
        "cosmetic_hypoallergenic",
        r"\bhipoalergénico\s*100%\b|100%低敏",
        "低敏宣称必须有测试依据",
        action="删除或补充测试依据",
        requires_pdp=True,
    ),
    _TextRule(
        "cosmetic_ingredient_effect",
        r"\b\d+%\s*(?:vitamina\s*c|niacinamida|ácido hialurónico)[^.\n]{0,40}\b(?:aclara|blanquea|rejuvenece)\b|成分功效",
        "成分功效必须有检测、备案或 PDP 依据",
        action="改为仅描述成分存在，或补充依据",
        requires_pdp=True,
    ),
)

CATEGORY_RULES = (
    _TextRule(
        "compression_claim",
        r"\bgran ahorro de sitio\b|\bahorra\s+\d+%\s+de espacio\b|\bcabe\s+\d+\s+chaquetas\b|大大节省空间|省\d+%空间",
        "压缩效果或容量数字必须有 PDP 原文",
        action="删除或补充 PDP 原文依据",
        requires_pdp=True,
    ),
    _TextRule(
        "wifi_performance_claim",
        r"\bhasta\s+\d+\s*mbps\b|\binternet\s+\d+\s*mbps\b|\b\d+%\s+más rápido que otros\b|\b100%\s*compatible\b|\bcobertura total de la casa\b|\bseñal en el balcón\b|\bduplica tu velocidad\b",
        "网络速率、覆盖或兼容性必须符合 PDP 的精确口径",
        action="删除或改为 PDP 原文口径",
        requires_pdp=True,
    ),
)

EFFECT_WORDS = re.compile(
    r"\bhidrata\b|\bdeja la piel suave\b|\btextura ligera\b|\bse absorbe rápido\b|\blarga duración\b|"
    r"保湿|滋润|肌肤柔滑|质地轻盈|快速吸收|持妆持久",
    flags=re.IGNORECASE,
)

VISUAL_FLAG_MESSAGES = {
    "ai_before_after": ("ai_before_after", "AI 生成使用前后效果对比属于效果造假"),
    "ai_skin_transformation": ("ai_skin_transformation", "不得生成皮肤变白、变光滑、痘痘消失等动态转化"),
    "beauty_filter": ("beauty_filter", "不得用滤镜伪造使用后肤质或妆效"),
    "fake_testimonial": ("fake_testimonial", "不得用 AI 冒充真人使用后好评"),
    "doctor_expert": ("doctor_expert_visual", "不得用医生、专家或白大褂形象暗示专业背书"),
    "unsupported_scene": ("unsupported_scene", "画面场景未被 PDP 支持"),
    "outdoor": ("unsupported_outdoor_scene", "墨西哥化妆品 AI 视频默认限室内，户外场景需有明确依据"),
    "ingredient_not_in_pdp": ("ingredient_not_in_pdp", "成分或质地不在 PDP/INCI 中"),
    "pdp_mismatch": ("pdp_mismatch", "容量、色号、质地、包装或数量与 PDP 不一致"),
    "ai_label_missing": ("ai_label_missing", "AI 生成视频上传前必须开启 AI 内容标注"),
}


def _is_mexico(market: str) -> bool:
    normalized = market.strip().casefold().replace("_", "-")
    return normalized in MEXICO_MARKETS


def _is_cosmetic(category: str) -> bool:
    normalized = category.strip().casefold()
    return any(term in normalized for term in COSMETIC_CATEGORIES)


def _contains_casefold(text: str, value: str) -> bool:
    return value.casefold() in text.casefold()


def _iter_matches(pattern: str, text: str) -> Iterable[re.Match[str]]:
    return re.finditer(pattern, text, flags=re.IGNORECASE)


def _append_text_matches(
    matches: list[ComplianceMatch],
    *,
    field: str,
    text: str,
    rules: Sequence[_TextRule],
    pdp_text: str,
    promotion_verified: bool,
) -> None:
    for rule in rules:
        for found in _iter_matches(rule.pattern, text):
            if rule.requires_pdp and _contains_casefold(pdp_text, found.group(0)):
                continue
            if rule.requires_promotion_verification and promotion_verified:
                continue
            matches.append(
                ComplianceMatch(
                    rule_id=rule.rule_id,
                    field=field,
                    matched_text=found.group(0),
                    severity="block",
                    action=rule.action,
                    reason=rule.reason,
                    replacement=rule.replacement,
                )
            )


def _append_cosmetic_pdp_support_matches(
    matches: list[ComplianceMatch],
    *,
    fields: Mapping[str, str],
    pdp_text: str,
) -> None:
    for field, text in fields.items():
        for found in EFFECT_WORDS.finditer(text):
            if _contains_casefold(pdp_text, found.group(0)):
                continue
            matches.append(
                ComplianceMatch(
                    rule_id="cosmetic_claim_not_in_pdp",
                    field=field,
                    matched_text=found.group(0),
                    severity="block",
                    action="删除该表述或补充 PDP 原文依据",
                    reason="化妆品体验/功效表述必须与 PDP 逐字一致",
                )
            )


def check_video_compliance(
    *,
    fields: Mapping[str, str],
    market: str,
    category: str,
    pdp_text: str = "",
    ai_generated: bool = False,
    ai_label_enabled: bool = False,
    visual_flags: Sequence[str] = (),
    promotion_verified: bool = False,
    advertisement: bool = False,
    disclaimer_present: bool = False,
    audience_18_plus: bool = False,
    local_representative_confirmed: bool = False,
    aviso_funcionamiento_confirmed: bool = False,
    nom_141_label_confirmed: bool = False,
    aviso_publicidad_confirmed: bool = False,
) -> ComplianceReport:
    matches: list[ComplianceMatch] = []
    rules = list(GENERAL_RULES)
    if _is_cosmetic(category):
        rules.extend(COSMETIC_RULES)
    rules.extend(CATEGORY_RULES)
    for field, text in fields.items():
        if text.strip():
            _append_text_matches(
                matches,
                field=field,
                text=text,
                rules=rules,
                pdp_text=pdp_text,
                promotion_verified=promotion_verified,
            )
    if _is_cosmetic(category):
        _append_cosmetic_pdp_support_matches(
            matches,
            fields=fields,
            pdp_text=pdp_text,
        )

    effective_visual_flags = tuple(visual_flags)
    if ai_generated and not ai_label_enabled:
        effective_visual_flags += ("ai_label_missing",)
    for flag in effective_visual_flags:
        if flag not in VISUAL_FLAG_MESSAGES:
            matches.append(
                ComplianceMatch(
                    rule_id="unknown_visual_flag",
                    field="visual",
                    matched_text=flag,
                    severity="block",
                    action="确认画面并删除该风险",
                    reason="未识别的画面风险标记，按未知风险阻断",
                )
            )
            continue
        rule_id, reason = VISUAL_FLAG_MESSAGES[flag]
        if flag == "outdoor" and not (_is_mexico(market) and _is_cosmetic(category)):
            continue
        matches.append(
            ComplianceMatch(
                rule_id=rule_id,
                field="visual",
                matched_text=flag,
                severity="block",
                action="删除画面或改用有依据的实拍素材",
                reason=reason,
            )
        )

    combined_text = "\n".join(fields.values())
    effect_disclaimer_required = (
        _is_mexico(market)
        and _is_cosmetic(category)
        and bool(EFFECT_WORDS.search(combined_text))
    )
    if effect_disclaimer_required and not disclaimer_present and not re.search(
        r"los resultados pueden variar|效果因人而异",
        combined_text,
        flags=re.IGNORECASE,
    ):
        matches.append(
            ComplianceMatch(
                rule_id="cosmetic_effect_disclaimer_missing",
                field="script",
                matched_text="",
                severity="block",
                action="补充“los resultados pueden variar”免责声明，或删除效果描述",
                reason="墨西哥化妆品涉及效果描述时需要免责声明",
            )
        )
    mexico_cosmetic = _is_mexico(market) and _is_cosmetic(category)
    if advertisement and ai_generated and not disclaimer_present:
        matches.append(
            ComplianceMatch(
                rule_id="ad_ai_disclaimer_missing",
                field="advertisement",
                matched_text="",
                severity="block",
                action="补充广告免责声明后再投放",
                reason="AI 广告素材必须带免责声明",
            )
        )
    if advertisement and mexico_cosmetic and not audience_18_plus:
        matches.append(
            ComplianceMatch(
                rule_id="beauty_ad_age_targeting_missing",
                field="advertisement",
                matched_text="",
                severity="block",
                action="将美容类广告定向设置为 18 岁以上",
                reason="墨西哥化妆品美容广告不得面向未满 18 岁用户",
            )
        )
    regulatory_ready = {
        "local_representative": local_representative_confirmed,
        "aviso_funcionamiento": aviso_funcionamiento_confirmed,
        "nom_141_label": nom_141_label_confirmed,
        "aviso_publicidad": aviso_publicidad_confirmed,
    }
    if mexico_cosmetic:
        for check_name, confirmed in regulatory_ready.items():
            if not confirmed:
                matches.append(
                    ComplianceMatch(
                        rule_id=f"mexico_{check_name}_missing",
                        field="regulatory",
                        matched_text="",
                        severity="block",
                        action="完成墨西哥合规确认后再发布",
                        reason=f"墨西哥化妆品合规准备项未确认：{check_name}",
                    )
                )

    checks = {
        "ai_label_enabled": ai_label_enabled if ai_generated else "not_applicable",
        "advertisement": advertisement,
        "audience_18_plus": audience_18_plus if advertisement else "not_applicable",
        "category_is_cosmetic": _is_cosmetic(category),
        "effect_disclaimer_required": effect_disclaimer_required,
        "market_is_mexico": _is_mexico(market),
        "pdp_provided": bool(pdp_text.strip()),
        "promotion_verified": promotion_verified,
        "regulatory_ready": regulatory_ready if mexico_cosmetic else "not_applicable",
        "text_fields_checked": sorted(field for field, text in fields.items() if text.strip()),
        "visual_flags_checked": list(effective_visual_flags),
    }
    status = "blocked" if matches else "passed"
    return ComplianceReport(
        rule_version=COMPLIANCE_RULE_VERSION,
        market=market,
        category=category,
        status=status,
        matches=tuple(matches),
        checks=checks,
    )


def compliance_prompt_block(*, market: str, product_notes: str) -> str:
    """Return a compact compliance block for AI video generation prompts."""
    cosmetic_mexico = _is_mexico(market) and _is_cosmetic(product_notes)
    block = (
        "【发布合规硬规则】口播、字幕、标签、画面文字逐词自查：禁止绝对化、保证、医疗、"
        "医生/专家背书、虚假促销；数字、百分比、倍数、时限、成分功效必须逐字有 PDP/INCI 依据，"
        "没有依据就删除。上传 AI 素材前必须开启 AI 生成内容标注。不得生成虚假使用前后对比、"
        "滤镜效果或冒充真人好评，画面只使用 PDP 支持的场景和真实商品配件。"
    )
    if cosmetic_mexico:
        block += (
            "墨西哥化妆品额外规则：只拍室内产品、包装、质地和涂抹动作；禁止皮肤变白/变光滑、"
            "痘痘或皱纹消失、医生专家形象和未经 PDP/INCI 的成分；涉及效果描述时加入 "
            "“los resultados pueden variar”。"
        )
    return block


def add_video_compliance_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "video-compliance",
        help="Check TikTok Shop video copy and visual compliance rules.",
    )
    nested = parser.add_subparsers(dest="compliance_command", required=True)
    check = nested.add_parser("check")
    check.add_argument("--script", type=Path)
    check.add_argument("--subtitles", type=Path)
    check.add_argument("--tags", type=Path)
    check.add_argument("--onscreen-text", type=Path)
    check.add_argument("--pdp", type=Path)
    check.add_argument("--market", required=True)
    check.add_argument("--category", required=True)
    check.add_argument("--ai-generated", action="store_true")
    check.add_argument("--ai-label-enabled", action="store_true")
    check.add_argument("--visual-flag", action="append", default=())
    check.add_argument("--promotion-verified", action="store_true")
    check.add_argument("--advertisement", action="store_true")
    check.add_argument("--disclaimer-present", action="store_true")
    check.add_argument("--audience-18-plus", action="store_true")
    check.add_argument("--local-representative-confirmed", action="store_true")
    check.add_argument("--aviso-funcionamiento-confirmed", action="store_true")
    check.add_argument("--nom-141-label-confirmed", action="store_true")
    check.add_argument("--aviso-publicidad-confirmed", action="store_true")


def handle_video_compliance(namespace: argparse.Namespace) -> int:
    if namespace.compliance_command != "check":
        return 2
    paths = {
        "script": namespace.script,
        "subtitles": namespace.subtitles,
        "tags": namespace.tags,
        "onscreen_text": namespace.onscreen_text,
    }
    try:
        fields = {
            field: path.read_text(encoding="utf-8")
            for field, path in paths.items()
            if path is not None
        }
        pdp_text = namespace.pdp.read_text(encoding="utf-8") if namespace.pdp else ""
    except (OSError, UnicodeError) as error:
        print(
            json.dumps(
                {
                    "error": "invalid_text_input",
                    "message": str(error),
                    "status": "blocked",
                    "rule_version": COMPLIANCE_RULE_VERSION,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    report = check_video_compliance(
        fields=fields,
        market=namespace.market,
        category=namespace.category,
        pdp_text=pdp_text,
        ai_generated=namespace.ai_generated,
        ai_label_enabled=namespace.ai_label_enabled,
        visual_flags=namespace.visual_flag,
        promotion_verified=namespace.promotion_verified,
        advertisement=namespace.advertisement,
        disclaimer_present=namespace.disclaimer_present,
        audience_18_plus=namespace.audience_18_plus,
        local_representative_confirmed=namespace.local_representative_confirmed,
        aviso_funcionamiento_confirmed=namespace.aviso_funcionamiento_confirmed,
        nom_141_label_confirmed=namespace.nom_141_label_confirmed,
        aviso_publicidad_confirmed=namespace.aviso_publicidad_confirmed,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.status == "passed" else 2


__all__ = [
    "COMPLIANCE_RULE_VERSION",
    "ComplianceMatch",
    "ComplianceReport",
    "add_video_compliance_parser",
    "check_video_compliance",
    "compliance_prompt_block",
    "handle_video_compliance",
]
