#!/usr/bin/env python3
"""Makes the two logo files the label stamper uses, from assets/logo_colour_source.png:

    assets/logo_colour.png   the logo cropped to its content (transparent background)
    assets/logo_thermal.png  black and white version for the thermal label printer

Thermal label printers print only black dots (no colours, no real greys), so pale colours such as the
yellow of the bee turn into faint dither speckle. This keeps only the DARK parts (the black lettering, the
outlines and the dark stripe) as solid black on white, and drops the light yellow and the pale teal shadow.

Run it again if you change the source logo or the threshold:   py make_logo.py [threshold 0-255, default 110]
Needs Pillow (pip install -r requirements.txt).
"""
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
SRC = HERE / "assets" / "logo_colour_source.png"
OUT_COLOUR = HERE / "assets" / "logo_colour.png"
OUT_THERMAL = HERE / "assets" / "logo_thermal.png"
MARGIN = 6          # pixels of white kept around the cropped logo
SCALE = 2           # work at 2x so edges are smooth, then shrink back


def main():
    threshold = int(sys.argv[1]) if len(sys.argv) > 1 else 110
    im = Image.open(SRC).convert("RGBA")
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(white, im).convert("RGB")

    # crop to the content
    bg = Image.new("RGB", flat.size, (255, 255, 255))
    box = ImageChops.difference(flat, bg).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
    box = (max(0, box[0] - MARGIN), max(0, box[1] - MARGIN), min(im.width, box[2] + MARGIN), min(im.height, box[3] + MARGIN))
    colour = im.crop(box)
    colour.save(OUT_COLOUR)

    # thermal: dark parts only, hard black on white
    big = flat.crop(box).resize((colour.width * SCALE, colour.height * SCALE), Image.LANCZOS)
    grey = big.convert("L")
    bw = grey.point(lambda v: 0 if v < threshold else 255)
    bw = bw.filter(ImageFilter.MedianFilter(3))             # remove single stray dots
    out = bw.resize(colour.size, Image.LANCZOS)              # soft edges again, still black and white
    out.save(OUT_THERMAL)
    print(f"wrote {OUT_COLOUR.name} and {OUT_THERMAL.name} ({colour.width} x {colour.height}, threshold {threshold})")


if __name__ == "__main__":
    main()
