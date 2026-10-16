from __future__ import annotations

import argparse
import html
import json
import re
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .video_compliance import COMPLIANCE_RULE_VERSION, compliance_prompt_block

MIN_PROMPT_CHARS = 3900
MAX_PROMPT_CHARS = 4000
MAX_REFERENCE_IMAGES = 9
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)


class JimengPromptError(ValueError):
    """Raised when a Jimeng prompt run cannot be completed."""


@dataclass(frozen=True, slots=True)
class ImageRecord:
    path: Path
    width: int | None
    height: int | None
    format: str | None


@dataclass(frozen=True, slots=True)
class PromptReceipt:
    run_directory: Path
    prompt_paths: tuple[Path, ...]
    brief_path: Path
    selected_images_path: Path
    receipt_path: Path
    prompt_chars: tuple[int, ...]
    selected_image_count: int


def add_jimeng_prompt_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "jimeng-prompt",
        help="Create product research bundles and Jimeng AI vertical ad video prompts.",
    )
    nested = parser.add_subparsers(dest="jimeng_command", required=True)

    init_parser = nested.add_parser("init")
    init_parser.add_argument("--product-name", required=True)
    init_parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    init_parser.add_argument("--output-dir", type=Path, default=Path("outputs/jimeng_prompt"))

    research_parser = nested.add_parser("research")
    research_parser.add_argument("--query", action="append", default=())
    research_parser.add_argument("--url", action="append", default=())
    research_parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    research_parser.add_argument("--output-dir", type=Path, default=Path("outputs/jimeng_prompt"))
    research_parser.add_argument("--max-results", type=int, default=6)

    generate_parser = nested.add_parser("generate")
    generate_parser.add_argument("--product-name")
    generate_parser.add_argument("--product-file", type=Path)
    generate_parser.add_argument("--image", type=Path, action="append", default=())
    generate_parser.add_argument("--image-notes", type=Path)
    generate_parser.add_argument("--research-notes", type=Path)
    generate_parser.add_argument("--profile", type=Path)
    generate_parser.add_argument("--count", type=int, default=1)
    generate_parser.add_argument("--market", default="TikTok Shop 目标市场")
    generate_parser.add_argument("--language", default="目标市场自然口语")
    generate_parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    generate_parser.add_argument("--output-dir", type=Path, default=Path("outputs/jimeng_prompt"))

    study_parser = nested.add_parser("study")
    study_parser.add_argument("--product-name", required=True)
    study_parser.add_argument("--product-file", type=Path, required=True)
    study_parser.add_argument("--image", type=Path, action="append", required=True)
    study_parser.add_argument("--image-notes", type=Path, required=True)
    study_parser.add_argument("--research-notes", type=Path, required=True)
    study_parser.add_argument("--market", default="TikTok Shop 目标市场")
    study_parser.add_argument("--language", default="目标市场自然口语")
    study_parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    study_parser.add_argument("--output-dir", type=Path, default=Path("outputs/jimeng_prompt"))

    validate_parser = nested.add_parser("validate")
    validate_parser.add_argument("prompt", type=Path)


def handle_jimeng_prompt(namespace: argparse.Namespace) -> int:
    if namespace.jimeng_command == "init":
        run_dir = _new_run_directory(
            _resolve_output_dir(namespace.workspace_root, namespace.output_dir),
            namespace.product_name,
        )
        run_dir.mkdir(parents=True)
        _write_init_templates(run_dir, namespace.product_name)
        print(
            json.dumps(
                {
                    "performed_external_writes": False,
                    "product_file": str(run_dir / "product_info.md"),
                    "image_notes_file": str(run_dir / "image_notes.md"),
                    "research_notes_file": str(run_dir / "web_research.md"),
                    "run_directory": str(run_dir),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if namespace.jimeng_command == "research":
        output_dir = _new_run_directory(
            _resolve_output_dir(namespace.workspace_root, namespace.output_dir),
            "web-research",
        )
        output_dir.mkdir(parents=True)
        notes = collect_web_research(
            queries=namespace.query,
            urls=namespace.url,
            max_results=namespace.max_results,
        )
        research_path = output_dir / "web_research.md"
        research_path.write_text(notes, encoding="utf-8")
        print(
            json.dumps(
                {
                    "performed_external_writes": False,
                    "research_notes_file": str(research_path),
                    "run_directory": str(output_dir),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if namespace.jimeng_command == "generate":
        try:
            receipt = generate_prompt_run(
                product_name=namespace.product_name,
                product_file=(
                    _resolve_path(namespace.workspace_root, namespace.product_file)
                    if namespace.product_file is not None
                    else None
                ),
                image_paths=[
                    _resolve_path(namespace.workspace_root, image) for image in namespace.image
                ],
                image_notes_path=(
                    _resolve_path(namespace.workspace_root, namespace.image_notes)
                    if namespace.image_notes is not None
                    else None
                ),
                research_notes_path=(
                    _resolve_path(namespace.workspace_root, namespace.research_notes)
                    if namespace.research_notes is not None
                    else None
                ),
                market=namespace.market,
                language=namespace.language,
                profile_path=(
                    _resolve_path(namespace.workspace_root, namespace.profile)
                    if namespace.profile is not None
                    else None
                ),
                count=namespace.count,
                output_root=_resolve_output_dir(namespace.workspace_root, namespace.output_dir),
            )
        except JimengPromptError as error:
            print(
                json.dumps(
                    {
                        "error": str(error),
                        "performed_external_writes": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "brief_path": str(receipt.brief_path),
                    "performed_external_writes": False,
                    "prompt_chars": list(receipt.prompt_chars),
                    "prompt_paths": [str(path) for path in receipt.prompt_paths],
                    "receipt_path": str(receipt.receipt_path),
                    "run_directory": str(receipt.run_directory),
                    "selected_image_count": receipt.selected_image_count,
                    "selected_images_path": str(receipt.selected_images_path),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if namespace.jimeng_command == "study":
        try:
            profile_path = create_product_profile(
                product_name=namespace.product_name,
                product_file=_resolve_path(namespace.workspace_root, namespace.product_file),
                image_paths=[
                    _resolve_path(namespace.workspace_root, image) for image in namespace.image
                ],
                image_notes_path=_resolve_path(namespace.workspace_root, namespace.image_notes),
                research_notes_path=_resolve_path(namespace.workspace_root, namespace.research_notes),
                market=namespace.market,
                language=namespace.language,
                output_root=_resolve_output_dir(namespace.workspace_root, namespace.output_dir),
            )
        except JimengPromptError as error:
            print(
                json.dumps(
                    {
                        "error": str(error),
                        "performed_external_writes": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "performed_external_writes": False,
                    "profile_path": str(profile_path),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if namespace.jimeng_command == "validate":
        prompt = namespace.prompt.read_text(encoding="utf-8")
        validation = validate_prompt(prompt)
        print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
        return 0 if validation["ok"] else 2
    return 2


def _resolve_output_dir(workspace_root: Path, output_dir: Path) -> Path:
    root = Path(workspace_root).resolve()
    if output_dir.is_absolute():
        return output_dir.resolve()
    return (root / output_dir).resolve()


def _resolve_path(workspace_root: Path, path: Path) -> Path:
    root = Path(workspace_root).resolve()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _slug(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip().lower())
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "", normalized)
    return normalized[:60] or "product"


def _new_run_directory(output_root: Path, product_name: str) -> Path:
    date = time.strftime("%Y-%m-%d")
    run_id = time.strftime("%H%M%S")
    base = output_root / date / f"{run_id}-{_slug(product_name)}"
    candidate = base
    index = 2
    while candidate.exists():
        candidate = output_root / date / f"{run_id}-{_slug(product_name)}-{index}"
        index += 1
    return candidate


def _write_init_templates(run_dir: Path, product_name: str) -> None:
    product_template = f"""# {product_name}

## 产品是什么
写清楚产品中文名、英文/当地市场名称、所属类目、核心用途。

## 产品真实外观
写清楚形状、颜色、材质、尺寸感、部件、按钮、孔位、配件、包装盒正反面元素。

## 怎么使用
按真实顺序写：打开包装、安装/组装、放置位置、手怎么拿、怎么启动、使用前后状态、清洁或收纳。

## 卖点和痛点
列出消费者真实痛点、误区、卖点、适用人群、不能夸大的点。

## PDP / INCI 合规依据
列出商品详情页可直接支持的容量、色号、质地、成分、卖点、数字、百分比、时限和促销原文。
没有 PDP 或 INCI 依据的内容不得写入口播、字幕、标签或画面文字。

## 禁止生成错误
列出即梦最容易画错的东西：不要多生成零件、不要改颜色、不要改安装位置、不要把产品变成别的品类。
化妆品还要写明：禁止 AI 前后肤质变化、滤镜美化、医生/专家形象、未经 PDP/INCI 的成分和功效。
"""
    image_notes_template = """# 图片观察记录

每张图都要写清楚，不要只写“主图/细节图”。

1. 图片路径：
   画面里有什么：
   产品结构：
   包装文字/图案：
   可用于即梦辅助生成的原因：
"""
    research_template = """# 网络搜索记录

记录同款或高度相似产品的来源链接、使用方式、常见卖点、买家关心点、注意事项。
不要记录没有证据的猜测。
"""
    (run_dir / "product_info.md").write_text(product_template, encoding="utf-8")
    (run_dir / "image_notes.md").write_text(image_notes_template, encoding="utf-8")
    (run_dir / "web_research.md").write_text(research_template, encoding="utf-8")


def collect_web_research(
    *,
    queries: Sequence[str],
    urls: Sequence[str],
    max_results: int,
) -> str:
    if not queries and not urls:
        raise JimengPromptError("research requires at least one --query or --url")
    if max_results < 1 or max_results > 20:
        raise JimengPromptError("max-results must be between 1 and 20")

    discovered: list[tuple[str, str, str]] = []
    for query in queries:
        discovered.extend(_duckduckgo_results(query, max_results=max_results))
    for url in urls:
        discovered.append((url, url, "user_provided_url"))

    seen: set[str] = set()
    rows: list[str] = [
        "# 网络搜索记录",
        "",
        "说明：以下内容是程序从搜索结果或指定网页中提取的公开页面摘要，生成最终即梦提示词前仍要结合产品图片逐项核对。",
        "",
    ]
    for title, url, snippet in discovered:
        if url in seen:
            continue
        seen.add(url)
        excerpt = _fetch_page_excerpt(url)
        rows.extend(
            [
                f"## {title}",
                f"- 链接：{url}",
                f"- 搜索摘要：{snippet}",
                f"- 页面摘录：{excerpt}",
                "",
            ]
        )
        if len(seen) >= max_results:
            break
    if not seen:
        raise JimengPromptError("no web research results were collected")
    return "\n".join(rows).strip() + "\n"


def _duckduckgo_results(query: str, *, max_results: int) -> list[tuple[str, str, str]]:
    endpoint = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    payload = _fetch_url(endpoint)
    blocks = re.findall(
        r'<a rel="nofollow" class="result__a" href="(?P<href>[^"]+)".*?>(?P<title>.*?)</a>'
        r".*?<a class=\"result__snippet\".*?>(?P<snippet>.*?)</a>",
        payload,
        flags=re.DOTALL,
    )
    results: list[tuple[str, str, str]] = []
    for raw_href, raw_title, raw_snippet in blocks[:max_results]:
        href = html.unescape(_strip_tags(raw_href))
        title = _clean_text(raw_title)
        snippet = _clean_text(raw_snippet)
        parsed = urllib.parse.urlparse(href)
        if parsed.netloc == "duckduckgo.com" and parsed.path.startswith("/l/"):
            query_values = urllib.parse.parse_qs(parsed.query)
            if query_values.get("uddg"):
                href = query_values["uddg"][0]
        if href.startswith("http"):
            results.append((title or href, href, snippet))
    return results


def _fetch_page_excerpt(url: str) -> str:
    try:
        payload = _fetch_url(url)
    except JimengPromptError as error:
        return f"抓取失败：{error}"
    text = _clean_text(payload)
    return text[:900] if text else "页面无可读正文。"


def _fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            raw = response.read(1_500_000)
    except (urllib.error.URLError, TimeoutError) as error:
        raise JimengPromptError(f"unable to fetch {url}: {error}") from error
    return raw.decode(content_type, errors="replace")


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _clean_text(value: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    text = _strip_tags(text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def generate_prompt_run(
    *,
    product_name: str | None,
    product_file: Path | None,
    image_paths: Sequence[Path],
    image_notes_path: Path | None,
    research_notes_path: Path | None,
    market: str,
    language: str,
    profile_path: Path | None,
    count: int,
    output_root: Path,
) -> PromptReceipt:
    if count < 1 or count > 50:
        raise JimengPromptError("count must be between 1 and 50")

    if profile_path is not None:
        profile = _load_product_profile(profile_path)
        product_name = str(profile["product_name"])
        product_notes = str(profile["product_notes"])
        image_notes = str(profile["image_notes"])
        research_notes = str(profile["research_notes"])
        market = market if market != "TikTok Shop 目标市场" else str(profile["market"])
        language = language if language != "目标市场自然口语" else str(profile["language"])
        image_paths = tuple(Path(value) for value in _as_string_list(profile["selected_images"]))
    else:
        if product_name is None:
            raise JimengPromptError("product-name is required without --profile")
        if product_file is None or not product_file.is_file():
            raise JimengPromptError(f"product file is missing: {product_file}")
        if not image_paths:
            raise JimengPromptError("at least one product image is required")
        if len(image_paths) > MAX_REFERENCE_IMAGES:
            raise JimengPromptError("Jimeng accepts at most 9 reference images")
        product_notes = _read_required_text(product_file, "product file")
        image_notes = _read_optional_text(image_notes_path)
        research_notes = _read_optional_text(research_notes_path)

    images = inspect_images(image_paths)

    _require_enough_evidence(product_notes, image_notes, research_notes)
    selected_images = tuple(record.path for record in images[:MAX_REFERENCE_IMAGES])
    brief = _build_brief(
        product_name=product_name,
        market=market,
        language=language,
        product_notes=product_notes,
        image_notes=image_notes,
        research_notes=research_notes,
        images=images,
    )
    prompt_records: list[tuple[str, int]] = []
    for variant in range(1, count + 1):
        prompt = build_jimeng_prompt(
            product_name=product_name,
            market=market,
            language=language,
            product_notes=product_notes,
            image_notes=image_notes,
            research_notes=research_notes,
            images=images,
            variant=variant,
        )
        validation = validate_prompt(prompt)
        if not validation["ok"]:
            raise JimengPromptError(f"generated prompt failed validation: {validation}")
        prompt_records.append((prompt, len(prompt)))

    run_dir = _new_run_directory(output_root, product_name)
    run_dir.mkdir(parents=True)
    prompt_paths: list[Path] = []
    brief_path = run_dir / "product_brief.md"
    selected_images_path = run_dir / "selected_images.txt"
    receipt_path = run_dir / "receipt.json"
    for index, (prompt, _chars) in enumerate(prompt_records, start=1):
        prompt_path = run_dir / f"jimeng_prompt_{index:02d}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_paths.append(prompt_path)
    brief_path.write_text(brief, encoding="utf-8")
    selected_images_path.write_text(
        "\n".join(str(path) for path in selected_images) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "compliance_rule_version": COMPLIANCE_RULE_VERSION,
        "language": language,
        "market": market,
        "performed_external_writes": False,
        "product_file": str(product_file) if product_file is not None else None,
        "product_name": product_name,
        "prompt_chars": [chars for _prompt, chars in prompt_records],
        "schema_version": 1,
        "selected_images": [str(path) for path in selected_images],
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return PromptReceipt(
        run_directory=run_dir,
        prompt_paths=tuple(prompt_paths),
        brief_path=brief_path,
        selected_images_path=selected_images_path,
        receipt_path=receipt_path,
        prompt_chars=tuple(chars for _prompt, chars in prompt_records),
        selected_image_count=len(selected_images),
    )


def _read_required_text(path: Path, label: str) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if len(text) < 120:
        raise JimengPromptError(f"{label} is too short; describe the product in detail first")
    return text


def _read_optional_text(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.is_file():
        raise JimengPromptError(f"notes file is missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def _require_enough_evidence(product_notes: str, image_notes: str, research_notes: str) -> None:
    combined = f"{product_notes}\n{image_notes}\n{research_notes}"
    required_terms = ("外观", "使用", "卖点", "包装")
    missing = [term for term in required_terms if term not in combined]
    if missing:
        raise JimengPromptError(
            "missing required product evidence sections: " + ", ".join(missing)
        )
    if len(product_notes) + len(image_notes) < 500:
        raise JimengPromptError("product and image notes are not detailed enough for Jimeng")


def inspect_images(image_paths: Sequence[Path]) -> tuple[ImageRecord, ...]:
    records: list[ImageRecord] = []
    for path in image_paths:
        if not path.is_file():
            raise JimengPromptError(f"image is missing: {path}")
        try:
            with Image.open(path) as image:
                records.append(
                    ImageRecord(
                        path=path,
                        width=image.width,
                        height=image.height,
                        format=image.format,
                    )
                )
        except UnidentifiedImageError as error:
            raise JimengPromptError(f"not a readable image: {path}") from error
    return tuple(records)


def create_product_profile(
    *,
    product_name: str,
    product_file: Path,
    image_paths: Sequence[Path],
    image_notes_path: Path,
    research_notes_path: Path,
    market: str,
    language: str,
    output_root: Path,
) -> Path:
    if not product_file.is_file():
        raise JimengPromptError(f"product file is missing: {product_file}")
    product_notes = _read_required_text(product_file, "product file")
    image_notes = _read_required_text(image_notes_path, "image notes file")
    research_notes = _read_required_text(research_notes_path, "research notes file")
    if len(image_paths) > MAX_REFERENCE_IMAGES:
        raise JimengPromptError("Jimeng accepts at most 9 reference images")
    images = inspect_images(image_paths)
    _require_enough_evidence(product_notes, image_notes, research_notes)

    profile_dir = output_root / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f"{_slug(product_name)}.json"
    profile = {
        "image_notes": image_notes,
        "language": language,
        "market": market,
        "product_name": product_name,
        "product_notes": product_notes,
        "research_notes": research_notes,
        "schema_version": 1,
        "selected_images": [str(record.path) for record in images],
    }
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return profile_path


def _load_product_profile(profile_path: Path) -> dict[str, object]:
    if not profile_path.is_file():
        raise JimengPromptError(f"profile is missing: {profile_path}")
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise JimengPromptError(f"profile is not valid JSON: {profile_path}") from error
    if not isinstance(payload, dict):
        raise JimengPromptError("profile must be a JSON object")
    required = {
        "image_notes",
        "language",
        "market",
        "product_name",
        "product_notes",
        "research_notes",
        "selected_images",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise JimengPromptError("profile missing fields: " + ", ".join(missing))
    return payload


def _as_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise JimengPromptError("profile selected_images must be a list of strings")
    return tuple(value)


def _build_brief(
    *,
    product_name: str,
    market: str,
    language: str,
    product_notes: str,
    image_notes: str,
    research_notes: str,
    images: Sequence[ImageRecord],
) -> str:
    image_lines = "\n".join(
        f"- {record.path} ({record.width}x{record.height}, {record.format})"
        for record in images
    )
    return f"""# {product_name} 产品研究档案

## 目标
- 市场：{market}
- 语言：{language}
- 成片：15 秒，9:16 竖屏，TikTok Shop 爆款广告风格
- 即梦辅助图数量：{len(images)}，最多 9 张

## 产品资料
{product_notes}

## 图片观察
{image_notes or "未提供单独图片观察文件；请在投喂即梦前由 Codex 或员工补充每张图的视觉细节。"}

## 网络资料
{research_notes or "未提供网络研究文件；建议先运行 jimeng-prompt research 或让 Codex 搜索同款/同类产品。"}

## 图片清单
{image_lines}
"""


def build_jimeng_prompt(
    *,
    product_name: str,
    market: str,
    language: str,
    product_notes: str,
    image_notes: str,
    research_notes: str,
    images: Sequence[ImageRecord],
    variant: int = 1,
) -> str:
    compact_product = _summarize(product_notes, 900)
    compact_images = _summarize(image_notes, 760)
    compact_research = _summarize(research_notes, 520)
    image_list = "；".join(
        f"图{index}={record.path.name}，尺寸{record.width}x{record.height}，格式{record.format}"
        for index, record in enumerate(images, start=1)
    )
    angle = _variant_angle(variant)
    compliance_block = compliance_prompt_block(market=market, product_notes=product_notes)
    prompt = f"""你是即梦 AI 视频生成器，现在必须严格按下面导演分镜生成一条 15 秒、9:16 竖屏 TikTok Shop 爆款广告视频。硬规则：必须有口播、字幕、真实包装、真实使用过程、结尾购物车引导和明确防错约束。不要自由发挥，不要把产品改成相似品，不要增加不存在的零件、按钮、线材、屏幕、品牌标志或人物手势。产品名：{product_name}。目标市场：{market}。口播语言：{language}。参考图只使用我上传的这些图，最多 9 张：{image_list}。必须优先保持参考图里的真实外观、颜色、材质、比例、包装样式和配件数量。

【本条广告差异化方向】这是同一产品的第 {variant} 条脚本，主攻角度：{angle}。必须保持产品事实完全一致，但镜头切入、痛点顺序、字幕节奏和生活场景要与其他版本不同，不要复用同一个开场动作和同一套对比画面。

【产品真实信息，必须牢记】{compact_product}

【图片视觉依据，必须逐条遵守】{compact_images or "根据上传图片识别产品主体、包装、配件、使用方向和比例，不得凭空改造。"}

【网络资料和使用方式依据】{compact_research or "根据已确认的同款或同类产品资料表现真实使用方式，不夸大功效，不编造医学、认证、价格、物流和平台活动。"}

【总画面规则】全片竖屏 1080x1920，手机拍摄感，真实家庭/办公室/车内等符合产品用途的生活场景，画面明亮，主体清楚，产品始终占画面重要位置。每个镜头都要有不同动作，不能 15 秒一直重复旋转展示。人物只露手、手臂或局部生活状态即可，避免陌生脸抢镜。镜头用近景、特写、俯拍、侧拍交替，背景简洁，不出现乱码文字，不出现错误包装。字幕不是口播逐字稿，只放短促卖点词，位置在画面中下部安全区以上，白字黑描边或高对比色块，不能遮住产品关键结构。

【0.0-1.2 秒 Hook】竖屏近景，先出现真实痛点场景：把未使用前的问题状态拍清楚，例如凌乱、费力、脏乱、占空间、操作麻烦或效果差，必须与该产品用途一致。镜头从用户视角快速推进到问题位置，手指或手掌做出明显困扰动作。画面左上角出现短字幕“别再这样凑合了”。口播用自然惊讶语气说：如果你也被这个小问题烦到，先看这一下。

【1.2-2.5 秒 产品登场】切到桌面或手持特写，产品从包装旁边被拿起。必须按参考图表现真实包装：盒子/袋子/标签/颜色/印刷位置保持一致；如果参考图有配件，配件只按真实数量摆放。镜头 45 度俯拍，手慢慢转动产品半圈，让观众看见外壳、边缘、接口、盖子、固定点、纹理或功能区域。字幕写“不是普通替代品”。口播：我一开始也以为随便买一个就行，直到用了这个。

【2.5-4.2 秒 结构解释】进入超近特写，按真实产品结构从上到下或从外到内展示。镜头不要生成说明书风格动画，而是实拍手指指向每个关键部位。每个部位只停留 0.4 秒，画面要稳定清晰。若产品需要安装，必须展示安装前的正确方向；若产品是开盖、按压、粘贴、卡扣、插入、套上、拧紧或折叠使用，动作必须与产品真实方式一致。字幕写“关键在这个结构”。口播：它真正好用的地方，是这个结构把麻烦步骤省掉了。

【4.2-6.4 秒 使用步骤一】镜头切到真实使用位置，手把产品放到正确位置。必须明确产品和被使用对象的相对关系：谁在上方、谁在下方、哪一面朝外、哪一端先接触、手握哪里、力度轻重。不要让产品悬空乱飞，不要自动变形，不要换成其他工具。用 0.3 秒快切展示“对准、放好、固定/打开/启动”三个动作。字幕写“对准就能用”。口播：用的时候不用猜，按这个方向放好，手一动就能看到变化。

【6.4-8.7 秒 使用步骤二】给一个侧面或俯拍连续动作，展示产品实际工作过程。画面必须让观众理解它在做什么：清洁类就看到接触面和污渍变化，收纳类就看到物品被放入和空间变整齐，工具类就看到接触点和操作结果，家居类就看到安装位置和使用后的状态。不要夸张成魔法，不要一秒变全新。字幕写“省力，不乱”。口播：最明显的是不用来回折腾，过程干净很多，也顺手很多。

【8.7-10.6 秒 对比结果】左右或前后快切对比，左边是使用前问题，右边是使用后结果；如果做左右分屏，分界线居中，产品仍然在右侧画面里出现。对比必须真实可信，不要生成过度夸张的完美效果。镜头给 0.5 秒产品特写，再给 0.8 秒结果特写。字幕写“差别一眼看见”。口播：这种小东西不是炫技，是每天用的时候真的少烦一次。

【10.6-12.5 秒 生活化补刀】切到更自然的生活场景：用户再次快速拿起或收纳产品，画面表现轻松、干净、有秩序。背景可以有桌面、厨房台面、浴室台面、车内、衣柜、包里或产品真实适用场景，但必须符合产品用途。手部动作要连贯：拿起、使用、放回，三步不要乱序。字幕写“放哪都顺手”。口播：家里人看到也会用，不用解释一堆步骤。

【12.5-15.0 秒 结尾转化】产品与包装一起放在干净背景中，参考图中的主图角度和包装朝向要保持，旁边可以出现使用后的结果物，但不要堆太多道具。镜头缓慢推进，最后 0.5 秒定格在产品正面和关键结构。字幕写“点购物车看优惠”。口播：想少踩坑，就按这个样子选，趁现在去购物车看看。

【字幕设计】全片字幕只出现这些短句，不要逐字跟口播：别再这样凑合了、不是普通替代品、关键在这个结构、对准就能用、省力不乱、差别一眼看见、放哪都顺手、点购物车看优惠。字幕必须跟镜头内容对应，每条 0.8 到 1.4 秒，不能遮挡产品、手部动作、包装文字和前后对比结果。

【口播要求】口播要像真人在 TikTok 上快速分享，不要播音腔，不要品牌硬广腔，不要说绝对化承诺。语速偏快但清楚，15 秒内完整讲完。口播只保留上面每个镜头指定的句子，不能新增夸张功效，不能说最低价、全网第一、永久、治疗、官方认证等没有证据的话。

【即梦防错清单】第一，产品外观必须等同参考图，不要把颜色、材质、形状、尺寸比例改掉。第二，包装必须按照参考图真实呈现，不要生成虚构英文大字、错误 logo 或不存在的插画。第三，使用方式必须按照产品资料和网络资料，不能把安装方向反过来，不能把一次性物品拍成可长期循环，不能把手持产品拍成电动设备，不能把无电线产品生成电线。第四，画面不能出现多余品牌、夸张表情包、漂浮 3D 字、低清马赛克、错误人体手指、错位字幕。第五，结尾必须有明确购物车引导，但不要出现虚构价格、券额、销量和倒计时。

【节奏】全片 8 个镜头，平均每镜头 1 到 2 秒，转场用快速硬切和轻微推近，不用复杂炫光。每个镜头必须推进信息：痛点、产品、结构、步骤、过程、对比、生活化、下单引导。生成时保持真实手作演示质感，产品和包装是主角，广告要像能直接发 TikTok Shop 的爆款短视频。

{compliance_block}"""
    return _fit_prompt_length(prompt)


def _variant_angle(variant: int) -> str:
    angles = (
        "先放大日常痛点，再用产品结构解释为什么省事",
        "从错误用法或低效替代品切入，突出这个产品的正确用法",
        "用开箱和包装可信感开场，快速转到真实上手演示",
        "从家人或同事也会遇到的尴尬场景切入，强调人人能用",
        "先展示使用后清爽结果，再倒回展示前后差别",
        "聚焦安装/放置方向，防止观众误以为很复杂",
        "用近距离细节特写建立质感，再进入痛点解决",
        "强调收纳、清洁或维护轻松，结尾做购物车引导",
        "用连续手部动作增强真实感，避免过多静态摆拍",
        "用快节奏三连问题开头，结尾回到产品和包装同框",
    )
    return angles[(variant - 1) % len(angles)]


def _summarize(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _fit_prompt_length(prompt: str) -> str:
    prompt = textwrap.dedent(prompt).strip()
    filler_sentences = (
        "再次强调，画面里只允许出现资料中确认存在的产品主体、包装和配件，所有动作都围绕真实使用过程展开。",
        "如果某个细节在图片里看不清，就保持朴素真实的近景，不要发明新结构、新按钮、新文字或新功能。",
        "每一次切镜都要让观众更懂产品，不能重复空镜、重复摆拍、重复旋转，也不能让字幕和口播抢走产品主体。",
        "手部动作要符合普通消费者的实际力度和速度，产品接触位置、安装方向、前后变化必须稳定连贯。",
    )
    index = 0
    while len(prompt) < MIN_PROMPT_CHARS:
        prompt = _append_filler_before_compliance(
            prompt,
            "补充防错：" + filler_sentences[index % len(filler_sentences)],
        )
        index += 1
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = _trim_to_max(prompt)
    if len(prompt) < MIN_PROMPT_CHARS or len(prompt) > MAX_PROMPT_CHARS:
        raise JimengPromptError(
            f"unable to fit prompt into {MIN_PROMPT_CHARS}-{MAX_PROMPT_CHARS} chars"
        )
    return prompt


def _append_filler_before_compliance(prompt: str, sentence: str) -> str:
    compliance_marker = "【发布合规硬规则】"
    if compliance_marker not in prompt:
        return prompt + "\n" + sentence
    body, compliance = prompt.split(compliance_marker, 1)
    return body.rstrip() + "\n" + sentence + "\n" + compliance_marker + compliance


def _trim_to_max(prompt: str) -> str:
    compliance_marker = "【发布合规硬规则】"
    if compliance_marker in prompt:
        body, compliance = prompt.split(compliance_marker, 1)
        suffix = compliance_marker + compliance
        if len(suffix) >= MAX_PROMPT_CHARS:
            raise JimengPromptError("compliance block is too long for the prompt limit")
        available = MAX_PROMPT_CHARS - len(suffix) - 1
        body = body[:available].rstrip()
        boundary = max(body.rfind("。"), body.rfind("\n"))
        if boundary >= 0:
            body = body[: boundary + 1].rstrip()
        return (body + "\n" + suffix).rstrip()
    target = MAX_PROMPT_CHARS - 1
    trimmed = prompt[:target]
    boundary = max(trimmed.rfind("。"), trimmed.rfind("\n"))
    if boundary >= MIN_PROMPT_CHARS:
        trimmed = trimmed[: boundary + 1]
    if len(trimmed) < MIN_PROMPT_CHARS:
        trimmed = prompt[:MAX_PROMPT_CHARS]
    return trimmed.rstrip()


def validate_prompt(prompt: str) -> dict[str, object]:
    required_terms = {
        "15 秒": "duration",
        "9:16": "aspect_ratio",
        "TikTok": "platform",
        "口播": "voiceover",
        "字幕": "subtitles",
        "结尾": "ending",
        "包装": "packaging",
        "使用": "usage",
        "防错": "anti_error",
        "购物车": "cta",
        "发布合规硬规则": "compliance_gate",
        "AI 生成内容标注": "ai_label",
    }
    missing = [code for term, code in required_terms.items() if term not in prompt]
    length = len(prompt)
    return {
        "chars": length,
        "max_chars": MAX_PROMPT_CHARS,
        "min_chars": MIN_PROMPT_CHARS,
        "missing": missing,
        "ok": MIN_PROMPT_CHARS <= length <= MAX_PROMPT_CHARS and not missing,
    }


__all__ = [
    "JimengPromptError",
    "PromptReceipt",
    "add_jimeng_prompt_parser",
    "build_jimeng_prompt",
    "collect_web_research",
    "generate_prompt_run",
    "handle_jimeng_prompt",
    "inspect_images",
    "validate_prompt",
]
