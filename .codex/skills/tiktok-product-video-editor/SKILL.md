---
name: tiktok-product-video-editor
description: Edit multi-market TikTok/TK Shop product short videos from user-provided clips or found product material. Use when the user or employee asks to剪辑产品视频, 剪一条/再剪一条, 找素材, 找各平台素材, 下载可用视频素材, 写/改口播文案, 做 TK 爆款感产品短视频, choose Mexico/Brazil/Indonesia or another target market, add voiceover/subtitles/cover, or deliver clickable final MP4/SRT files for ecommerce content.
---

# TikTok Product Video Editor

## Positioning

Use this skill as the product-video editing agent for TikTok Shop operation. The editing workflow stays the same across markets; only language, slang, CTA wording, currency/promo phrasing, and cultural framing change by target market.

Supported default markets:

- Mexico: Spanish, `es-MX`
- Brazil: Portuguese, `pt-BR`
- Indonesia: Indonesian, `id-ID`

If the user names another market, adapt to that market if feasible. If the target market is not stated and cannot be inferred, ask one short question before final localization/rendering. Do not block early material inspection or Chinese draft planning.

## Core rule

Move fast, but keep the checks that prevent bad videos:

1. Inspect/search material.
2. Plan clip order and runtime.
3. Show the exact Chinese voiceover draft and wait for approval.
4. Localize to the selected market and render only after approval.
5. QA freezes, pauses, codec/playability, subtitles, and delivery links.

Do not spawn subagents unless the user explicitly asks for subagents, delegation, or parallel agent work.

## Input handling

- If the user provides a bounded set of clips for “one new video”, use every provided clip by default. Assign each clip a role before scripting: hook, pain scene, product/action demo, result, CTA, or transition.
- Do not drop any provided clip unless it is unusable. If dropping one, say why before the draft.
- If the user says the clips are not sorted, decide the order yourself based on continuity and conversion flow.
- If the user gives only a product, SKU, link, image, title, or general request, search for related material first.
- If the user explicitly says “找素材”, start searching immediately. Prioritize quantity and usable files; do not only return links.
- Do not present long material-classification tables by default. Decide internally how material will be used. Show details only if the user asks.

## Material search standard

Collect product-relevant material broadly: same product, similar appearance, same use case, similar pain scene, similar demo, or usable lifestyle/action footage.

Prioritize:

- vertical 9:16 video;
- diverse creators, hands, rooms, scenes, platforms, and angles;
- real demo/use footage over static product shots;
- multiple platforms/sources when practical;
- files that can be previewed directly by the user.

Avoid:

- only one actor/creator/source series;
- horizontal/square clips as primary material unless there are not enough vertical options;
- unrelated products;
- low-resolution unreadable clips;
- watermarks that dominate the frame;
- AV1/VP9/HEVC/WebM/DASH fragments as final preview files.

When delivering found material, transcode/remux primary preview files to broadly playable MP4:

- H.264 video;
- AAC audio if audio exists;
- `yuv420p`;
- `+faststart`.

When a platform blocks simple download, do lightweight reverse analysis only: inspect HTML, embedded JSON, network/player manifests, CDN URLs, file signatures, and downloader logs. Use the user's already-authorized browser/session only when available. Do not do CAPTCHA cracking, credential theft, payment-gated bypass, or risky account automation.

## Market selection and localization

Ask or infer the target market before final voiceover/subtitles:

- If user says 墨西哥/MX/Mexico: localize to Mexican Spanish.
- If user says 巴西/BR/Brazil: localize to Brazilian Portuguese.
- If user says 印尼/ID/Indonesia: localize to Indonesian.
- If the user says multiple markets, produce one approved Chinese master script first, then localize separate versions per market.

Localization must preserve the approved selling logic, not translate mechanically. Adjust:

- natural spoken phrasing;
- local household scene wording;
- local CTA phrasing such as cart/order/promo;
- currency or platform wording only when the user provides it or it is safe to infer;
- voice tone for the product category and target audience.

If market-specific claims, prices, promotions, shipping terms, compliance language, or platform rules are unknown, avoid inventing them. Use generic CTA such as “mira la oferta”, “confira a oferta”, or “cek promo di keranjang”.

## Compliance gate

Before final localization or rendering, read `references/tiktok-shop-video-compliance.md` and run the compliance check over the voiceover, subtitles, hashtags, and on-screen text. The check is a blocking gate:

- absolute, guarantee, medical, expert/clinical endorsement, unrelated hashtag, and unverified promotion wording must be deleted or replaced;
- every number, percentage, multiplier, capacity, time claim, ingredient, and benefit must match the PDP/INCI wording; unsupported claims do not ship;
- AI content must be labeled before upload, and AI must not fabricate before/after results, skin transformations, or real-user testimonials;
- for Mexico cosmetics, use indoor product/packaging/texture/application scenes by default, block medicalized beauty claims, and verify PDP/INCI consistency;
- for Mexico cosmetics advertising, confirm 18+ targeting, the required disclaimer, and the local compliance readiness items before publishing.

Use the local checker when structured text files are available:

`tk-ops-workspace video-compliance check --market Mexico --category cosmetics --script script.txt --subtitles subtitles.txt --tags tags.txt --onscreen-text onscreen.txt --pdp pdp.txt --ai-generated --ai-label-enabled`

Any `blocked` result requires revision and a new check. Keep the existing Chinese voiceover approval gate; compliance checking does not replace employee approval.

## TK爆款口播 standard

Before rendering, always show the exact Chinese voiceover draft and wait for approval, even if the user says “直接剪辑”. “直接” means short communication and no unnecessary process; it does not mean skipping copy approval. Only skip this if the user explicitly says not to show the script/voiceover first.

The draft must fit the planned runtime. Do not write copy first and force it into the edit later.

For TikTok commerce videos, the script must include:

- strong hook in the first 1-2 seconds;
- concrete real-life pain point;
- household/lived conflict or embarrassment;
- mistaken assumption or diagnosis twist;
- visible try/use/action sequence;
- before/after feeling or result;
- direct order/cart/promo CTA at the end.

Avoid stiff ad copy, neat slogan structure, pure feature explanations, domestic hard-sell phrasing, and vague “problem solved” lines. Write like a real person speaking from a specific annoyance.

If the user says “不够爆款”, revise the voiceover first and show the new exact text for approval before rendering.

If any approved copy, subtitle, timing, speed, cover text, or structure changes later, show the changed exact text/plan and wait for approval again.

## Editing standard

- Build a fast-paced vertical TikTok edit. Add speed-up where useful, especially low-information movement, setup, repeated hand action, long pans, or waiting shots.
- Preserve action continuity. Do not speed up so much that product use becomes unclear.
- Do not pad runtime with static product display, frozen phone screens, lights, empty tabletop, or dead reaction shots.
- Voiceover should substantially fill the video. Avoid long pauses between lines and avoid voice ending far before the video ends.
- Prefer active shots: hand use, before/after, compression, cleaning, plugging in, unboxing, close result, problem scene, and CTA shot.
- Keep clip transitions simple and fast unless the user asks for a specific style.
- Default final format is vertical 9:16 MP4.

## Voice, subtitles, and cover

- Use local Kokoro/TTS when available for speed. Record the voice name and speed in notes when practical.
- Match voice language to the selected market.
- Subtitles should be synced phrase-by-phrase, not as long multi-sentence blocks.
- Keep subtitles fully visible and above the platform lower safety area.
- If the user asks for no black subtitle background, remove it and keep readability with placement, stroke, shadow, and shorter lines.
- Default delivery may include a clean video plus separate `.srt`; burn subtitles only if the user asks or the current workflow requires it.
- Cover/title text must be centered, readable, and product-angle focused when created.

## QA before delivery

Run proportionate checks before saying the video is done:

- verify all required user-provided clips were used, or explain exclusions;
- check final duration and pacing against approved script;
- inspect for dead air and frozen/static padding;
- run `ffmpeg`/`ffprobe` checks when available;
- run `freezedetect`; any freeze segment `>= 0.8s` must be inspected and recut rather than explained away;
- verify final preview is H.264/AAC-compatible MP4 with `yuv420p` and faststart when possible;
- open or sample the final output if practical.
- complete the compliance gate and record its rule version and any blocked items in the run notes;
- for AI-generated Mexico cosmetics, verify the upload AI label, indoor scene constraint, 18+ ad targeting when applicable, disclaimer, and the local compliance confirmations.

## Output and handoff

Save work outside the source-material folder, for example:

- Employee workspace default: `outputs/video/<market>/<YYYY-MM-DD>/<run-id>/`

- `F:\成片过程\<project>\analysis`
- `F:\成片过程\<project>\outputs`
- `E:\成片过程\<project>\analysis`
- `E:\成片过程\<project>\outputs`

Do not put analysis, render scripts, subtitle files, or outputs back into the user's raw material folder.
Allocate a unique run ID for every edit or retry. 不覆盖历史成片、字幕、分析记录或失败记录。

Final response must include:

- selected target market and language;
- clickable local link to final MP4;
- clickable local link to subtitle file when created;
- exact final voiceover text unless the user explicitly said not to show it;
- concise material-role map when the user provided a bounded file set;
- short source note when material was searched by Codex.

Update durable memory when the user gives feedback that should affect future edits, especially: market selection, script approval rules, material search preferences, codec/playability problems, subtitle placement, pacing, CTA expectations, and repeated editing mistakes.
