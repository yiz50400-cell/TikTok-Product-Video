from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tk_ops_workspace.jimeng_prompt import (
    MAX_PROMPT_CHARS,
    MAX_REFERENCE_IMAGES,
    MIN_PROMPT_CHARS,
    JimengPromptError,
    build_jimeng_prompt,
    create_product_profile,
    generate_prompt_run,
    inspect_images,
    validate_prompt,
)


def _long_notes(label: str) -> str:
    return (
        f"{label}。产品是什么：这是一个厨房收纳工具。产品真实外观：白色主体，透明盖子，"
        "圆角长方形结构，有清晰包装正面和配件。怎么使用：打开包装后放在厨房台面，"
        "把物品按正确方向放入，再合上盖子。卖点和痛点：解决凌乱、拿取慢、占空间。"
        "包装：纸盒彩印，正面展示产品和用途。禁止生成错误：不要改变颜色，不要增加电线。"
    ) * 4


def _image(path: Path) -> Path:
    Image.new("RGB", (640, 960), color=(240, 240, 240)).save(path)
    return path


def test_build_prompt_stays_inside_required_length(tmp_path: Path) -> None:
    image = inspect_images([_image(tmp_path / "product.jpg")])

    prompt = build_jimeng_prompt(
        product_name="测试产品",
        market="墨西哥",
        language="西班牙语",
        product_notes=_long_notes("产品资料"),
        image_notes=_long_notes("图片观察"),
        research_notes=_long_notes("网络资料"),
        images=image,
    )

    validation = validate_prompt(prompt)
    assert validation["ok"] is True
    assert validation["missing"] == []
    assert MIN_PROMPT_CHARS <= len(prompt) <= MAX_PROMPT_CHARS
    assert "发布合规硬规则" in prompt
    assert "AI 生成内容标注" in prompt
    assert prompt.rfind("发布合规硬规则") > prompt.rfind("【节奏】")


def test_profile_can_be_studied_once_and_reused_many_times(tmp_path: Path) -> None:
    product_file = tmp_path / "product.md"
    image_notes = tmp_path / "image_notes.md"
    research_notes = tmp_path / "research.md"
    image = _image(tmp_path / "product.jpg")
    product_file.write_text(_long_notes("产品资料"), encoding="utf-8")
    image_notes.write_text(_long_notes("图片观察"), encoding="utf-8")
    research_notes.write_text(_long_notes("网络资料"), encoding="utf-8")

    profile = create_product_profile(
        product_name="测试产品",
        product_file=product_file,
        image_paths=[image],
        image_notes_path=image_notes,
        research_notes_path=research_notes,
        market="墨西哥",
        language="西班牙语",
        output_root=tmp_path / "outputs",
    )

    assert json.loads(profile.read_text(encoding="utf-8"))["product_name"] == "测试产品"
    receipt = generate_prompt_run(
        product_name=None,
        product_file=None,
        image_paths=(),
        image_notes_path=None,
        research_notes_path=None,
        market="TikTok Shop 目标市场",
        language="目标市场自然口语",
        profile_path=profile,
        count=3,
        output_root=tmp_path / "outputs",
    )

    assert len(receipt.prompt_paths) == 3
    assert all(path.is_file() for path in receipt.prompt_paths)
    assert all(MIN_PROMPT_CHARS <= chars <= MAX_PROMPT_CHARS for chars in receipt.prompt_chars)


def test_rejects_more_than_nine_images(tmp_path: Path) -> None:
    product_file = tmp_path / "product.md"
    image_notes = tmp_path / "image_notes.md"
    research_notes = tmp_path / "research.md"
    product_file.write_text(_long_notes("产品资料"), encoding="utf-8")
    image_notes.write_text(_long_notes("图片观察"), encoding="utf-8")
    research_notes.write_text(_long_notes("网络资料"), encoding="utf-8")
    images = [_image(tmp_path / f"{index}.jpg") for index in range(MAX_REFERENCE_IMAGES + 1)]

    try:
        create_product_profile(
            product_name="测试产品",
            product_file=product_file,
            image_paths=images,
            image_notes_path=image_notes,
            research_notes_path=research_notes,
            market="墨西哥",
            language="西班牙语",
            output_root=tmp_path / "outputs",
        )
    except JimengPromptError as error:
        assert "at most 9" in str(error)
    else:
        raise AssertionError("expected JimengPromptError")
