"""Generate JobTrail's raster app icons from a tiny pure-Python renderer.

Zero dependencies (stdlib only: ``zlib`` + ``struct``), matching the rest of
the project. The design mirrors ``assets/icon.svg`` — a terracotta app tile
with a cream clipboard and a green "done" badge — so platforms that need a
raster icon (.png/.ico/.icns) can build one locally at install time instead of
committing binary blobs to the open-source repo.

Used by ``install-desktop.py``; also runnable directly:

    python3 assets/icongen.py out_dir        # writes icon-<size>.png + icon.ico
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

# ---- brand palette (matches webapp/static/styles.css) ----
TILE_TOP = (188, 90, 69)     # #bc5a45
TILE_BOT = (161, 74, 56)     # #a14a38
CREAM = (250, 246, 236)      # #faf6ec
INK = (38, 33, 28)           # #26211c
ROW = (224, 216, 199)        # #e0d8c7
GREEN = (91, 138, 90)        # #5b8a5a

# Design space is 512x512 (same coordinates as the SVG).
DS = 512.0


def _round_rect(px, py, x, y, w, h, r):
    if px < x or px > x + w or py < y or py > y + h:
        return False
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy <= r * r


def _circle(px, py, cx, cy, r):
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def _near_polyline(px, py, pts, halfw):
    hw2 = halfw * halfw
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        seg2 = vx * vx + vy * vy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / seg2))
        dx, dy = wx - t * vx, wy - t * vy
        if dx * dx + dy * dy <= hw2:
            return True
    return False


def _sample(px, py):
    """Return (r, g, b, a) for a point in 512x512 design space."""
    # green "done" badge (drawn last, on top of clipboard)
    if _circle(px, py, 340, 356, 46):
        if _near_polyline(px, py, [(320, 356), (334, 370), (360, 340)], 7):
            return (*CREAM, 255)
        return (*GREEN, 255)

    # clipboard body
    if _round_rect(px, py, 132, 120, 248, 296, 28):
        # checklist rows
        for ry, rw in ((206, 160), (258, 160), (310, 120)):
            if _round_rect(px, py, 176, ry, rw, 18, 9):
                return (*ROW, 255)
        return (*CREAM, 255)

    # clip: cream paper tab over a dark base
    if _round_rect(px, py, 226, 104, 60, 40, 14):
        return (*CREAM, 255)
    if _round_rect(px, py, 214, 96, 84, 56, 18):
        return (*INK, 255)

    # background app tile (rounded, transparent corners)
    if _round_rect(px, py, 0, 0, 512, 512, 114):
        t = py / DS
        r = round(TILE_TOP[0] + (TILE_BOT[0] - TILE_TOP[0]) * t)
        g = round(TILE_TOP[1] + (TILE_BOT[1] - TILE_TOP[1]) * t)
        b = round(TILE_TOP[2] + (TILE_BOT[2] - TILE_TOP[2]) * t)
        return (r, g, b, 255)

    return (0, 0, 0, 0)


def render_master(res=512):
    """Render the icon at ``res``x``res`` into a flat RGBA bytearray."""
    buf = bytearray(res * res * 4)
    scale = DS / res
    i = 0
    for yy in range(res):
        py = (yy + 0.5) * scale
        for xx in range(res):
            px = (xx + 0.5) * scale
            r, g, b, a = _sample(px, py)
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = a
            i += 4
    return buf, res


def downscale(master, src, dst):
    """Area-average downscale of an RGBA buffer from src->dst resolution."""
    if dst == src:
        return master
    out = bytearray(dst * dst * 4)
    ratio = src / dst
    for dy in range(dst):
        sy0, sy1 = int(dy * ratio), max(int(dy * ratio) + 1, int((dy + 1) * ratio))
        for dx in range(dst):
            sx0, sx1 = int(dx * ratio), max(int(dx * ratio) + 1, int((dx + 1) * ratio))
            r = g = b = a = n = 0
            for sy in range(sy0, sy1):
                row = sy * src * 4
                for sx in range(sx0, sx1):
                    j = row + sx * 4
                    al = master[j + 3]
                    # average straight RGBA; weight color by coverage
                    r += master[j] * al
                    g += master[j + 1] * al
                    b += master[j + 2] * al
                    a += al
                    n += 1
            o = (dy * dst + dx) * 4
            if a:
                out[o] = r // a
                out[o + 1] = g // a
                out[o + 2] = b // a
                out[o + 3] = a // n
            else:
                out[o] = out[o + 1] = out[o + 2] = out[o + 3] = 0
    return out


def _png_bytes(buf, size):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # filter type 0 (None)
        raw += buf[y * stride:(y + 1) * stride]
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def write_png(path, buf, size):
    Path(path).write_bytes(_png_bytes(buf, size))


def write_ico(path, images):
    """images: list of (size, png_bytes). Stores PNG-compressed icons."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    offset = 6 + count * 16
    blobs = bytearray()
    for size, png in images:
        b = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    Path(path).write_bytes(header + bytes(entries) + bytes(blobs))


def build(out_dir, png_sizes=(512, 256, 128, 64, 48, 32, 16), ico_sizes=(256, 64, 48, 32, 16)):
    """Render and write all icon assets into out_dir. Returns dict of paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    master, mres = render_master(max(png_sizes))
    bufs = {mres: master}
    for s in set(png_sizes) | set(ico_sizes):
        if s not in bufs:
            bufs[s] = downscale(master, mres, s)

    written = {}
    for s in png_sizes:
        p = out / f"icon-{s}.png"
        write_png(p, bufs[s], s)
        written[f"png{s}"] = p
    # a canonical icon.png (largest)
    write_png(out / "icon.png", bufs[max(png_sizes)], max(png_sizes))
    written["png"] = out / "icon.png"
    # Windows .ico
    ico_imgs = [(s, _png_bytes(bufs[s], s)) for s in sorted(ico_sizes, reverse=True)]
    write_ico(out / "icon.ico", ico_imgs)
    written["ico"] = out / "icon.ico"
    return written


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    paths = build(target)
    for k, v in paths.items():
        print(f"{k:8} {v}")
