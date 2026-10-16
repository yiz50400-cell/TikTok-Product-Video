from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def make_arrow(output: Path) -> None:
    width, height = 260, 420
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    red = (224, 26, 34, 255)
    shadow = (70, 0, 0, 150)
    highlight = (255, 120, 120, 255)

    # Straight vertical down arrow with a large head.
    draw.rounded_rectangle((111, 28, 155, 278), radius=16, fill=shadow)
    draw.polygon([(55, 254), (211, 254), (133, 394)], fill=shadow)

    draw.rounded_rectangle((96, 18, 140, 268), radius=16, fill=red)
    draw.polygon([(40, 244), (196, 244), (118, 384)], fill=red)

    draw.rounded_rectangle((108, 30, 119, 238), radius=5, fill=highlight)
    draw.line((86, 265, 118, 326), fill=highlight, width=9)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    make_arrow(parser.parse_args().output)
