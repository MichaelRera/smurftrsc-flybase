"""Chrome Web Store images: three 1280x800 screenshots and the 440x280 promo tile.
Usage: python3 make_store_images.py RAW_DIR OUT_DIR ICON128
RAW_DIR holds 1240-px-wide browser captures (raw_thor.png, raw_gclc.png, raw_both.png), made with
tools/store_capture.py. Same layout as the ProteoCast for FlyBase store images, so the two read as a family."""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

raw, out, icon = sys.argv[1], sys.argv[2], sys.argv[3]
FONT = "/usr/share/fonts/truetype/ubuntu/Ubuntu-{}.ttf"
B, R = ImageFont.truetype(FONT.format("B"), 34), ImageFont.truetype(FONT.format("R"), 20)
NAVY, BG = (31, 59, 115), (238, 242, 248)
SHOTS = [  # (raw file, crop box, title, subtitle)
    ("raw_thor.png", (0, 72, 1240, 692), "Smurf vs non-Smurf expression on every gene page",
     "Zane et al. 2023 (Aging Cell): all 32 samples by age and Smurf status, the DESeq2 contrasts, and the paper's "
     "other results for the gene. Thor: flat with age, higher in Smurfs."),
    ("raw_gclc.png", (0, 72, 1240, 692), "Tell Smurf status apart from age",
     "Gclc: up in Smurfs and in old non-Smurfs. Hover a sample for its details, or open the table of all 32 values."),
    ("raw_both.png", (0, 72, 1240, 692), "Protein, transcript and allele pages too",
     "Thor-PA: the panel shows the parent gene, under the ProteoCast for FlyBase panel when both extensions are "
     "installed. The data ships with the extension: no server, no tracking."),
]
for n, (f, box, title, sub) in enumerate(SHOTS, 1):
    im = Image.new("RGB", (1280, 800), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1280, 150], fill=NAVY)
    d.text((48, 34), title, font=B, fill="white")
    words, line, lines = sub.split(), "", []
    for w in words:
        t = (line + " " + w).strip()
        if d.textlength(t, font=R) > 1180: lines.append(line); line = w
        else: line = t
    lines.append(line)
    assert len(lines) <= 2, f"subtitle {n} needs {len(lines)} lines"
    for k, l in enumerate(lines): d.text((48, 86 + k * 26), l, font=R, fill=(214, 224, 240))
    shot = Image.open(f"{raw}/{f}").convert("RGB").crop(box)  # native pixels, no scaling
    x, y = (1280 - shot.width) // 2, 150 + (650 - shot.height) // 2
    shadow = Image.new("RGBA", (shot.width + 40, shot.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([20, 20, shot.width + 20, shot.height + 20], fill=(0, 0, 0, 70))
    blur = shadow.filter(ImageFilter.GaussianBlur(10))
    im.paste(blur, (x - 20, y - 14), blur)
    im.paste(shot, (x, y))
    im.save(f"{out}/screenshot-{n}.png")

# small promo tile 440x280
t = Image.new("RGB", (440, 280), NAVY); d = ImageDraw.Draw(t)
ic = Image.open(icon).convert("RGBA").resize((96, 96), Image.LANCZOS); t.paste(ic, (172, 34), ic)
for text, font, y in (("SmurfTrsc for FlyBase", ImageFont.truetype(FONT.format("B"), 30), 150),
                      ("Smurf vs non-Smurf gene expression", ImageFont.truetype(FONT.format("R"), 19), 200),
                      ("right on FlyBase pages", ImageFont.truetype(FONT.format("R"), 19), 226)):
    d.text(((440 - d.textlength(text, font=font)) / 2, y), text, font=font, fill="white" if y == 150 else (214, 224, 240))
t.save(f"{out}/promo-small-440x280.png")
