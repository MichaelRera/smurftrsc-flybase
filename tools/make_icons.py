#!/usr/bin/env python3
"""Draw the toolbar icons: two columns of dots on a blue tile, as in the panel's strip plot."""
import os
from PIL import Image, ImageDraw

BLUE, WHITE, PALE = (42, 120, 214), (255, 255, 255), (183, 211, 246)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
for size in (16, 48, 128):
    s = 8  # supersample
    n = size * s
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n // 5, fill=BLUE)
    r = n * 0.095
    for cx, cys, color in ((0.33, (0.70, 0.55), PALE), (0.67, (0.45, 0.30), WHITE)):
        for cy in cys:
            d.ellipse((n * cx - r, n * cy - r, n * cx + r, n * cy + r), fill=color)
    im.resize((size, size), Image.LANCZOS).save(os.path.join(out, f"icon{size}.png"))
