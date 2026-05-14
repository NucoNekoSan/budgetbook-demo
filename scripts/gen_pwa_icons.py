"""Generate PWA icon PNGs (pure stdlib, no Pillow).

Run once after manifest design changes:
  python scripts/gen_pwa_icons.py

Outputs (overwrites) under budgetbook/static/icons/:
  - icon-192.png        (any, 192x192)
  - icon-512.png        (any, 512x512)
  - icon-mask-512.png   (maskable, 512x512, larger safe area)
  - apple-touch-icon.png (180x180, iOS home screen)

Design: solid #2563eb background + simplified white "B" glyph composed of
rectangles. SVG (icon.svg) carries the higher-fidelity design for browsers
that support manifest SVG icons.
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

BG = (0x25, 0x63, 0xeb, 0xff)       # #2563eb
FG = (0xff, 0xff, 0xff, 0xff)       # white
TRANSPARENT = (0, 0, 0, 0)

OUT_DIR = Path(__file__).resolve().parent.parent / 'budgetbook' / 'static' / 'icons'


def _draw_b(width: int, height: int, padding_ratio: float, rounded: bool = True) -> list[list[tuple[int, int, int, int]]]:
    """Solid background + white blocky 'B' glyph.

    padding_ratio: ratio of side margin to width. 0.18 = 18% padding per side.
    rounded: if True, fake rounded corners by clearing 4 corner pixels of bg
             (kept off for maskable icons that need full bleed).
    """
    pad = int(width * padding_ratio)
    pixels: list[list[tuple[int, int, int, int]]] = [[BG] * width for _ in range(height)]

    # B glyph bounding box
    x0, y0 = pad, pad
    x1, y1 = width - pad, height - pad
    w = x1 - x0
    h = y1 - y0
    # Stem thickness ~= 22% of glyph width
    stem = max(2, w * 22 // 100)
    # Horizontal bar thickness ~= 18% of glyph height
    bar = max(2, h * 18 // 100)
    # Right bumps: protrude ~ 78% of glyph width
    right = x0 + w * 78 // 100
    # Middle bar position
    mid_top = y0 + (h - bar) // 2
    mid_bot = mid_top + bar

    def fill(rx0, ry0, rx1, ry1, color=FG):
        for y in range(max(0, ry0), min(height, ry1)):
            for x in range(max(0, rx0), min(width, rx1)):
                pixels[y][x] = color

    # Left stem
    fill(x0, y0, x0 + stem, y1)
    # Top bar (extends to right bump)
    fill(x0, y0, right, y0 + bar)
    # Bottom bar
    fill(x0, y1 - bar, right, y1)
    # Middle bar (slightly shorter for elegance)
    fill(x0, mid_top, right - w * 6 // 100, mid_bot)
    # Right vertical bumps (top half + bottom half)
    fill(right - stem, y0, right, mid_bot)
    fill(right - stem, mid_top, right, y1)

    if rounded:
        # Faux rounded corners: clear ~8% radius worth of corner pixels
        r = width * 8 // 100
        for y in range(r):
            for x in range(r):
                dx = r - x
                dy = r - y
                if dx * dx + dy * dy > r * r:
                    pixels[y][x] = TRANSPARENT
                    pixels[y][width - 1 - x] = TRANSPARENT
                    pixels[height - 1 - y][x] = TRANSPARENT
                    pixels[height - 1 - y][width - 1 - x] = TRANSPARENT
    return pixels


def _write_png(path: Path, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    height = len(pixels)
    width = len(pixels[0])
    # Build raw scanlines: each row prefixed with filter byte 0 (None)
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for px in row:
            raw.extend(px)
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    out = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    path.write_bytes(out)
    print(f'wrote {path} ({len(out)} bytes)')


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Any-purpose icons: rounded corners look nice on most launchers
    _write_png(OUT_DIR / 'icon-192.png', _draw_b(192, 192, padding_ratio=0.18, rounded=True))
    _write_png(OUT_DIR / 'icon-512.png', _draw_b(512, 512, padding_ratio=0.18, rounded=True))
    # Maskable: needs solid bleed to edge (launcher clips it)
    _write_png(OUT_DIR / 'icon-mask-512.png', _draw_b(512, 512, padding_ratio=0.26, rounded=False))
    # Apple touch icon (iOS auto-applies its own corner mask)
    _write_png(OUT_DIR / 'apple-touch-icon.png', _draw_b(180, 180, padding_ratio=0.18, rounded=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())