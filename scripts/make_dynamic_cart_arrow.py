from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def make_arrow(output: Path, scale: float = 1.5) -> None:
    width = int(360 * scale)
    height = int(320 * scale)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    red = (224, 26, 34, 255)
    shadow = (75, 0, 0, 155)
    s = scale

    def xy(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
        return [(round(x * s), round(y * s)) for x, y in points]

    # A curved, downward-left arrow. Its different silhouette avoids a generic
    # straight pointer while keeping the cart target visually obvious.
    curve = xy([(296, 28), (292, 82), (278, 132), (247, 177), (205, 214), (155, 238)])
    draw.line(curve, fill=shadow, width=round(31 * s), joint="curve")
    draw.line(curve, fill=red, width=round(24 * s), joint="curve")
    draw.line(
        xy([(288, 28), (284, 80), (270, 127), (241, 170), (201, 207), (157, 231)]),
        fill=(255, 112, 112, 255),
        width=max(3, round(5 * s)),
        joint="curve",
    )

    shadow_head = xy([(115, 304), (92, 230), (168, 241)])
    main_head = xy([(105, 290), (82, 216), (158, 227)])
    draw.polygon(shadow_head, fill=shadow)
    draw.polygon(main_head, fill=red)
    draw.line(xy([(104, 244), (127, 273)]), fill=(255, 112, 112, 255), width=max(3, round(5 * s)))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    make_arrow(args.output)
