"""Native picture against the Blender tracer's: the numbers, and a side-by-side.

    py -3.12 compare.py <native.png> <blender.jpg> [out.png] [label]

mean |difference|: over every pixel and channel, 0..255, on the pictures as shown (sRGB).
luminance ratio:   mean linear luminance native / Blender (over the pixels that are not backdrop in either).
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def lin(a):
    a = a / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def measure(n, b):
    d = np.abs(n - b)
    bg = n[2, 2]
    model = (np.abs(n - bg).max(axis=2) > 3) | (np.abs(b - bg).max(axis=2) > 3)
    w = np.array([0.2126, 0.7152, 0.0722])
    ln, lb = lin(n) @ w, lin(b) @ w
    return dict(mean=d.mean(), mean_model=d[model].mean(), share=model.mean(), p95=np.percentile(d.max(axis=2), 95),
                over8=(d.max(axis=2) > 8).mean(), lum=ln[model].mean() / lb[model].mean(),
                enc=(n[model] @ w).mean() / (b[model] @ w).mean(), signed=(n - b)[model].mean(axis=0))


def main():
    a = sys.argv
    N, B = Image.open(a[1]).convert("RGB"), Image.open(a[2]).convert("RGB")
    n, b = np.asarray(N, dtype=np.float64), np.asarray(B, dtype=np.float64)
    m = measure(n, b)
    # the same with both pictures blurred a little: what is left when grain, JPEG blocks and the last
    # half-pixel of edge softness are out of it (a difference of LIGHT survives a blur, one of noise does not)
    g = lambda im: np.asarray(im.filter(ImageFilter.GaussianBlur(3)), dtype=np.float64)
    ms = measure(g(N), g(B))
    label = a[4] if len(a) > 4 else a[1]
    print(f"{label}: mean |native - Blender| {m['mean']:.2f}/255 over the picture, {m['mean_model']:.2f}/255 over the model's pixels ({100 * m['share']:.0f}% of it); "
          f"95th percentile {m['p95']:.0f}; {100 * m['over8']:.1f}% of pixels off by more than 8; "
          f"luminance native/Blender {m['lum']:.3f} (linear), {m['enc']:.3f} (as shown); mean signed difference on the model R,G,B {m['signed'].round(2).tolist()}; "
          f"blurred 3 px first: mean {ms['mean']:.2f}/255, on the model {ms['mean_model']:.2f}/255")
    if len(a) > 3 and a[3] != "-":
        W, H = N.size
        d = np.clip(np.abs(n - b) * 8, 0, 255).astype(np.uint8)
        gap = 12
        out = Image.new("RGB", (W * 3 + gap * 2, H + 44), (255, 255, 255))
        for i, (im, t) in enumerate(((N, "native (at rest)"), (B, "Blender (Cycles, OptiX denoised)"), (Image.fromarray(d), "|difference| x 8"))):
            out.paste(im, (i * (W + gap), 44))
            ImageDraw.Draw(out).text((i * (W + gap) + 8, 6), t, fill=(0, 0, 0), font_size=26)
        ImageDraw.Draw(out).text((W * 2 + gap * 2 + 300, 6), f"mean {m['mean']:.2f}/255   luminance ratio {m['lum']:.3f}", fill=(0, 0, 0), font_size=26)
        out.save(a[3])


main()
