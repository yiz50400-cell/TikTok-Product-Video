# TikTok Shop Video Compliance Rules

Rule version: `2026-09-v1`

This is the internal pre-publish checklist derived from the employee-provided:

- `TikTok带货视频违规词自查清单.docx`
- `TikTok化妆品AI视频合规指南（墨西哥市场）.docx`

The latest Seller Center, TikTok Shop, TikTok Ads, and COFEPRIS wording takes precedence. This file is an operating gate, not legal advice.

## Scope

Check all four text carriers:

- voiceover;
- subtitles;
- hashtags;
- on-screen text, including generated packaging text.

Check the rendered video frame by frame for visual claims and product/PDP consistency.

## Block By Default

Delete or replace:

- absolute or guarantee wording: `100% natural`, `100% seguro`, `el mejor`, `número uno`, `único`, `garantizado`, `siempre`, `nunca`, `instantáneo`;
- unsupported numbers, percentages, multipliers, speed, capacity, coverage, or time-to-result claims;
- unverified promotions: `gratis`, `descuento`, `oferta`, `por tiempo limitado`, `liquidación`, `última oportunidad`;
- medical or body-function claims: `cura`, `trata`, `previene`, `alivia el dolor`, `adelgaza`, `elimina ...`;
- expert, clinical, or regulator endorsements without evidence: `médico`, `doctor`, `dermatólogo`, `recomendado por expertos`, `resultados clínicos`, `aprobado por FDA/COFEPRIS`;
- unrelated or misleading tags, including `#wifimoney` and unverified promotion tags.

Every number, percentage, ingredient, benefit, capacity, and time claim must match the PDP or INCI wording. If the source text cannot be found, the claim does not ship.

## Mexico Cosmetics

When market is Mexico and category is cosmetics, skincare, beauty, or makeup:

- block `elimina el acné`, `blanquea`, `aclara la piel`, `quita manchas`, `borra/elimina las arrugas`, `rejuvenece`, `reafirma la piel`, `efecto lifting`, `piel perfecta`, and `tratamiento`;
- do not generate skin whitening, smoothing, acne disappearance, wrinkle disappearance, filter-enhanced before/after, or any other AI effect transformation;
- do not use AI to impersonate a real user testimonial, doctor, expert, or clinical endorsement;
- use indoor scenes by default; outdoor, balcony, terrace, and yard scenes require explicit PDP support;
- show only PDP/INCI-supported ingredients, texture, volume, shade, packaging, and quantity;
- use safe experience wording such as `hidrata`, `textura ligera`, `se absorbe rápido`, `deja la piel suave`, and `rutina diaria` only when consistent with the PDP;
- add `los resultados pueden variar` when the approved copy describes an effect;
- enable the AI-generated-content label before upload;
- for ads, target users 18+ and add the required disclaimer;
- confirm local representative/importer responsibility, `Aviso de Funcionamiento`, `NOM-141` label readiness, and the applicable `Aviso de Publicidad` status before publishing.

The default safe AI scene is an indoor product/packaging/texture/application demonstration with no skin transformation.

## Workflow Gate

1. Extract a claim whitelist from the PDP and INCI.
2. Draft Chinese voiceover, then localize without adding claims.
3. Run `tk-ops-workspace video-compliance check` over voiceover, subtitles, tags, and on-screen text.
4. Inspect AI-generated frames for the visual flags in this file.
5. Stop and revise on any `blocked` result.
6. Keep the existing Chinese voiceover approval gate before final rendering.
