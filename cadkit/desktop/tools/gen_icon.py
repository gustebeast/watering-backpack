"""Draws the viewer's icon, desktop/icon.ico (py -3.12 tools/gen_icon.py; needs Pillow).

A cube seen from a corner, its three faces three shades of the viewer's blue, on the
viewer's dark backdrop with rounded corners: three flat shapes, so that it is still a
cube at 16 pixels. Each size is drawn for itself (large, then reduced), not scaled from
one picture: the small ones get a thinner margin and no gap between the faces.
"""
import io
import math
import pathlib
import struct

from PIL import Image, ImageDraw

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
BACK, TOP, LEFT, RIGHT = (22, 24, 28), (134, 184, 232), (77, 132, 184), (44, 84, 124)


def draw(size):
    k = 8                                           # drawn 8x, reduced: smooth edges
    n = size * k
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 0.2, fill=BACK + (255,))
    c, r = n / 2, n * (0.40 if size <= 24 else 0.37)
    gap = 0 if size <= 24 else n * 0.012            # a hairline between the faces, where there is room
    pts = [(c + r * math.cos(math.radians(a)), c - r * math.sin(math.radians(a))) for a in range(90, 450, 60)]
    up, ul, dl, dn, dr, ur = pts                    # the hexagon's corners, from the top, anticlockwise

    def face(poly, col):
        m = (sum(p[0] for p in poly) / 4, sum(p[1] for p in poly) / 4)
        poly = [(x + (m[0] - x) * gap / r, y + (m[1] - y) * gap / r) for x, y in poly]
        d.polygon(poly, fill=col + (255,))
    face([up, ur, (c, c), ul], TOP)
    face([ul, (c, c), dn, dl], LEFT)
    face([(c, c), ur, dr, dn], RIGHT)
    return im.resize((size, size), Image.LANCZOS)


def entry(im):
    """One picture as an .ico holds it: the small ones as plain bitmaps (every reader of
    icons takes those), the large as PNG (a quarter of a megabyte each otherwise)."""
    n = im.size[0]
    if n > 64:
        b = io.BytesIO()
        im.save(b, format="PNG")
        return b.getvalue()
    rows = [im.crop((0, y, n, y + 1)).tobytes("raw", "BGRA") for y in range(n - 1, -1, -1)]
    mask = bytes(((n + 31) // 32) * 4) * n          # the AND mask: unused beside an alpha channel
    return struct.pack("<IiiHHIIiiII", 40, n, 2 * n, 1, 32, 0, 0, 0, 0, 0, 0) + b"".join(rows) + mask


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[1] / "icon.ico"
    data = [(s, entry(draw(s))) for s in SIZES]
    head, at = struct.pack("<HHH", 0, 1, len(data)), 6 + 16 * len(data)
    for s, d in data:
        head += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(d), at)
        at += len(d)
    out.write_bytes(head + b"".join(d for _, d in data))
    print("wrote", out, out.stat().st_size, "bytes")
