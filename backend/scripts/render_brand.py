"""Render the brand mark to PNG, with no image library.

Telegram's @BotFather will not take an SVG for a bot's profile photo, and this
box has no Pillow, no cairosvg, no rsvg-convert and no ImageMagick. So this
rasterises the three shapes in ``app/web/static/brand/nera-avatar.svg`` directly
and writes the PNG bytes itself. ``zlib`` and ``struct`` are the only imports,
and both are in the standard library.

    python scripts/render_brand.py

It does **not** parse the SVG — it re-declares the same geometry below. That is a
duplication, and a deliberate one: a general SVG rasteriser is a large piece of
software to carry for four files, while these three shapes are a diamond and two
rounded rectangles. The constants are named after the elements they mirror, and
``test_brand.py`` reads both files and fails if the numbers drift apart, so the
copy cannot rot silently.

Antialiasing is by supersampling, and only where it is needed: a pixel whose
corners and centre all agree is filled or empty outright, and the ~2% along an
edge get 16 samples. That is the difference between this finishing in a second
and taking half a minute.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# The canvas nera-avatar.svg is drawn on. Every constant below is in these
# units, and the output is scaled from them.
CANVAS = 512

# rect width=512 height=512 rx=112
PLATE_RADIUS = 112

# path M256 108 356 208 256 308 156 208Z — a diamond, expressed as its centre
# and half-diagonal because that is what an inside test needs.
DIAMOND_CENTRE = (256, 208)
DIAMOND_REACH = 100

# The two rules of the price list.
BARS = (
    (164, 348, 184, 22, 11),
    (196, 386, 120, 22, 11),
)

PLATE_COLOUR = (0x1C, 0x5D, 0x43)   # --accent
INK_COLOUR = (0xFB, 0xFA, 0xF9)     # --paper

BRAND_DIR = Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "brand"

# 512 is @BotFather's minimum for a profile photo. The rest are the sizes a
# browser and a phone home screen ask for.
OUTPUTS = (
    ("nera-avatar-512.png", 512),
    ("nera-avatar-128.png", 128),
    ("favicon-180.png", 180),
    ("favicon-32.png", 32),
)

SAMPLES = 4


def rounded_rect(x0: float, y0: float, w: float, h: float, r: float):
    """An inside test for a rounded rectangle."""
    x1, y1 = x0 + w, y0 + h
    inner_x0, inner_x1 = x0 + r, x1 - r
    inner_y0, inner_y1 = y0 + r, y1 - r
    r_squared = r * r

    def inside(px: float, py: float) -> bool:
        if px < x0 or px > x1 or py < y0 or py > y1:
            return False

        # Clamped to the rectangle of corner centres: in the straight-edge
        # regions this lands on the point itself and the distance is zero, so
        # one test covers both the edges and the corners.
        cx = inner_x0 if px < inner_x0 else (inner_x1 if px > inner_x1 else px)
        cy = inner_y0 if py < inner_y0 else (inner_y1 if py > inner_y1 else py)
        dx, dy = px - cx, py - cy

        return dx * dx + dy * dy <= r_squared

    return inside


def diamond(cx: float, cy: float, reach: float):
    """An inside test for a diamond — the L1 ball, which is all a diamond is."""

    def inside(px: float, py: float) -> bool:
        return abs(px - cx) + abs(py - cy) <= reach

    return inside


INK_SHAPES = (
    diamond(*DIAMOND_CENTRE, DIAMOND_REACH),
    *(rounded_rect(*bar) for bar in BARS),
)

PLATE_SHAPE = rounded_rect(0, 0, CANVAS, CANVAS, PLATE_RADIUS)


def _in_ink(px: float, py: float) -> bool:
    return any(shape(px, py) for shape in INK_SHAPES)


def coverage(shape, px: float, py: float, step: float) -> float:
    """How much of one pixel a shape covers, in 0..1.

    ``px``/``py`` are the pixel's top-left corner in canvas units and ``step`` is
    its width. The corners and centre are checked first because they settle the
    overwhelming majority of pixels without sampling further.
    """
    half = step / 2
    probes = (
        shape(px + half, py + half),
        shape(px, py),
        shape(px + step, py),
        shape(px, py + step),
        shape(px + step, py + step),
    )

    if all(probes):
        return 1.0

    if not any(probes):
        return 0.0

    offsets = [(i + 0.5) * step / SAMPLES for i in range(SAMPLES)]
    hits = sum(
        1
        for dy in offsets
        for dx in offsets
        if shape(px + dx, py + dy)
    )

    return hits / (SAMPLES * SAMPLES)


def render(size: int) -> bytearray:
    """The avatar at ``size``x``size``, as RGBA rows."""
    step = CANVAS / size
    pixels = bytearray(size * size * 4)
    plate_r, plate_g, plate_b = PLATE_COLOUR
    ink_r, ink_g, ink_b = INK_COLOUR

    for row in range(size):
        py = row * step
        offset = row * size * 4

        for col in range(size):
            px = col * step

            plate = coverage(PLATE_SHAPE, px, py, step)

            if plate == 0.0:
                offset += 4
                continue

            ink = coverage(_in_ink, px, py, step)

            # Ink over plate, then the pair over transparency. Compositing in
            # this order is what keeps the rounded corners clean: the alpha
            # comes from the plate, the colour from the mix above it.
            pixels[offset] = round(plate_r + (ink_r - plate_r) * ink)
            pixels[offset + 1] = round(plate_g + (ink_g - plate_g) * ink)
            pixels[offset + 2] = round(plate_b + (ink_b - plate_b) * ink)
            pixels[offset + 3] = round(255 * plate)
            offset += 4

    return pixels


def write_png(path: Path, size: int, pixels: bytearray) -> None:
    stride = size * 4
    raw = bytearray()

    for row in range(size):
        raw.append(0)  # filter type 0: none
        raw += pixels[row * stride : (row + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    for name, size in OUTPUTS:
        path = BRAND_DIR / name
        write_png(path, size, render(size))
        print(f"{path.relative_to(BRAND_DIR.parents[4])}  {size}x{size}  "
              f"{path.stat().st_size:,} bytes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
