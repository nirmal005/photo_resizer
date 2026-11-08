#!/usr/bin/env python3
"""
make_5x7_sheets.py - lay out 5x7 photos two per US Letter sheet for an Epson ET-4955.

Each Letter sheet (8.5 x 11 in, portrait) holds two 7 x 5 in photos stacked
vertically. Portrait photos are rotated 90 degrees to fit. The two photos share one
cut line in the middle, and crop ticks in the margins show where to trim.

500 photos -> 250 sheets, written as PDFs in batches (default 10 sheets each),
so you can print one batch, load more paper, and print the next.

BRIGHTNESS
  Prints usually look darker than a backlit screen. Two separate corrections:
  --lift X   Same brightening for every photo, to make up for the printer/paper
             (found with --test-sheet). It's a midtone curve: shadows and
             mid-tones come up, and white highlights don't blow out.
  --auto     Per-photo: dark/underexposed photos get brightened toward a normal
             exposure; photos that are already bright are left alone.
  Both can be used together. Auto runs first, then the lift.

Setup (once):
    pip install pillow img2pdf

Usage:
    # 1) Make one calibration sheet from a typical photo and print it
    python make_5x7_sheets.py  photos out --test-sheet photos/IMG_0123.jpg
    # 2) Pick the band that best matches a professional print, e.g. +0.15
    python make_5x7_sheets.py  photos out --auto --lift 0.15

    python make_5x7_sheets.py  photos out --fit          # don't crop; add white bars instead
    python make_5x7_sheets.py  photos out --ppi 720      # only if photos are >= 3600x5040 px
    python make_5x7_sheets.py  photos out --batch 5      # 5 sheets per PDF
    python make_5x7_sheets.py  photos out --sharpen 0.8  # 0 = off, 0.5 = subtle, 1 = strong
"""
import argparse
import io
import math
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageFont, ImageOps

import img2pdf

EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}
SHEET_W_IN, SHEET_H_IN = 8.5, 11.0
PHOTO_W_IN, PHOTO_H_IN = 7.0, 5.0   # landscape slot; two of them stack vertically


# ---------------------------------------------------------------- brightness
def gamma_for_lift(lift: float) -> float:
    """lift 0 = unchanged, 0.15 = moderate, 0.3 = strong. Returns the curve exponent."""
    return 1.0 / (1.0 + lift)


def apply_gamma(img: Image.Image, g: float) -> Image.Image:
    if abs(g - 1.0) < 1e-3:
        return img
    lut = [min(255, round(255 * ((i / 255) ** g))) for i in range(256)]
    return img.point(lut * 3)


def auto_lift(img: Image.Image, target: float, max_lift: float) -> float:
    """How much to brighten so the photo's average brightness reaches `target` (0-1).
    Only brightens, never darkens, and is capped so night shots don't turn grey."""
    small = img.convert("L").copy()
    small.thumbnail((400, 400))
    hist = small.histogram()
    total = sum(hist)
    # ignore the darkest and brightest 2% (black borders, sky, lamps) when averaging
    lo_cut, hi_cut, acc, s, n = total * 0.02, total * 0.98, 0, 0.0, 0
    for v, c in enumerate(hist):
        a, b = acc, acc + c
        keep = max(0, min(b, hi_cut) - max(a, lo_cut))
        s += v * keep
        n += keep
        acc = b
    mean = (s / n) / 255 if n else 0.5
    if mean <= 0.01 or mean >= target:
        return 0.0
    g = math.log(target) / math.log(mean)        # exponent that maps mean -> target
    return min(max_lift, 1.0 / g - 1.0)


# ---------------------------------------------------------------- sharpening
def sharpen(img: Image.Image, factor: float, ppi: int) -> Image.Image:
    """Unsharp mask at final print size. The radius scales with ppi so a given factor
    looks about the same on paper at any resolution."""
    if factor <= 0:
        return img
    return img.filter(ImageFilter.UnsharpMask(radius=ppi / 300, percent=round(factor * 100), threshold=2))


# ---------------------------------------------------------------- image prep
def to_srgb(img: Image.Image) -> Image.Image:
    """Convert an image with an embedded ICC profile (e.g. Adobe RGB, Display P3) to sRGB."""
    icc = img.info.get("icc_profile")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            img = ImageCms.profileToProfile(img, src, dst, renderingIntent=0, outputMode="RGB")
        except Exception:
            pass  # bad profile: keep the pixels as they are
    return img.convert("RGB")


def prepare(path: Path, slot_w: int, slot_h: int, opts) -> tuple[Image.Image, float]:
    """Returns the slot-sized image and the auto lift that was applied."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)          # honor camera rotation
    img = to_srgb(img)
    if img.height > img.width:                  # portrait photo -> rotate into landscape slot
        img = img.rotate(90, expand=True)
    if opts.fit:
        canvas = Image.new("RGB", (slot_w, slot_h), "white")
        img = ImageOps.contain(img, (slot_w, slot_h), Image.LANCZOS)
        a = auto_lift(img, opts.auto_target, opts.auto_max) if opts.auto else 0.0
        img = apply_gamma(img, gamma_for_lift(a) * gamma_for_lift(opts.lift))
        img = sharpen(img, opts.sharpen, opts.ppi)
        canvas.paste(img, ((slot_w - img.width) // 2, (slot_h - img.height) // 2))
        return canvas, a
    img = ImageOps.fit(img, (slot_w, slot_h), Image.LANCZOS, centering=(0.5, 0.5))
    a = auto_lift(img, opts.auto_target, opts.auto_max) if opts.auto else 0.0
    img = apply_gamma(img, gamma_for_lift(a) * gamma_for_lift(opts.lift))
    return sharpen(img, opts.sharpen, opts.ppi), a


def low_res_warning(path: Path) -> str | None:
    with Image.open(path) as im:
        size = im.size
    w, h = sorted(size)
    if w < 5 * 300 or h < 7 * 300:   # 300 ppi is the practical floor for a sharp 5x7
        return f"{path.name}: {size[0]}x{size[1]} px is below 1500x2100 (300 ppi at 5x7) - may look soft"
    return None


# ---------------------------------------------------------------- sheet layout
def sheet_geometry(ppi):
    sw, sh = int(SHEET_W_IN * ppi), int(SHEET_H_IN * ppi)
    pw, ph = int(PHOTO_W_IN * ppi), int(PHOTO_H_IN * ppi)
    return sw, sh, pw, ph, (sw - pw) // 2, (sh - 2 * ph) // 2   # 0.75" sides, 0.5" top/bottom


def draw_marks(sheet, ppi, x0, y0, pw, ph, rows):
    """Crop marks running from the photo edge to the paper edge, in the margins only."""
    d = ImageDraw.Draw(sheet)
    sw, sh = sheet.size
    lw = max(1, ppi // 180)
    ys = [y0 + k * ph for k in range(rows + 1)]
    for y in ys:
        d.line([(0, y), (x0 - 1, y)], fill="black", width=lw)
        d.line([(x0 + pw, y), (sw - 1, y)], fill="black", width=lw)
    for x in (x0, x0 + pw):
        d.line([(x, 0), (x, ys[0] - 1)], fill="black", width=lw)
        d.line([(x, ys[-1]), (x, sh - 1)], fill="black", width=lw)


def make_sheet(photos, opts):
    sw, sh, pw, ph, x0, y0 = sheet_geometry(opts.ppi)
    sheet = Image.new("RGB", (sw, sh), "white")
    lifts = []
    for i, p in enumerate(photos):
        img, a = prepare(p, pw, ph, opts)
        sheet.paste(img, (x0, y0 + i * ph))
        lifts.append(a)
    if not opts.no_marks:
        draw_marks(sheet, opts.ppi, x0, y0, pw, ph, len(photos))
    return sheet, lifts


def font(px):
    try:
        return ImageFont.load_default(size=px)
    except TypeError:            # older Pillow
        return ImageFont.load_default()


def make_test_sheet(photo: Path, opts):
    """One Letter sheet: the same photo twice, each split into 5 vertical bands at
    increasing brightness. Print it on the real paper and pick the best band."""
    sw, sh, pw, ph, x0, y0 = sheet_geometry(opts.ppi)
    sheet = Image.new("RGB", (sw, sh), "white")
    base_opts = argparse.Namespace(**{**vars(opts), "lift": 0.0, "auto": False})
    base, _ = prepare(photo, pw, ph, base_opts)
    rows = [[0.0, 0.05, 0.10, 0.15, 0.20], [0.25, 0.30, 0.35, 0.40, 0.50]]
    d = ImageDraw.Draw(sheet)
    f = font(int(0.16 * opts.ppi))
    band_w = pw // 5
    for r, lifts in enumerate(rows):
        for b, lift in enumerate(lifts):
            box = (b * band_w, 0, pw if b == 4 else (b + 1) * band_w, ph)
            band = apply_gamma(base.crop(box), gamma_for_lift(lift))
            sheet.paste(band, (x0 + box[0], y0 + r * ph))
            label = f"+{lift:.2f}"
            tx, ty = x0 + box[0] + int(0.08 * opts.ppi), y0 + r * ph + int(0.08 * opts.ppi)
            d.text((tx, ty), label, font=f, fill="white", stroke_width=max(2, opts.ppi // 90),
                   stroke_fill="black")
    d.text((x0, int(0.12 * opts.ppi)), f"Brightness test - {photo.name} - pick a band, then use --lift <value>",
           font=font(int(0.11 * opts.ppi)), fill="black")
    return sheet


# ---------------------------------------------------------------- output
def jpeg_bytes(img, ppi):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=97, subsampling=0, dpi=(ppi, ppi))
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="folder of photos")
    ap.add_argument("out", type=Path, help="output folder for PDFs")
    ap.add_argument("--ppi", type=int, default=360, choices=[300, 360, 720],
                    help="sheet resolution (Epson drivers work natively at 360/720; default 360)")
    ap.add_argument("--batch", type=int, default=10, help="sheets per PDF (default 10)")
    ap.add_argument("--fit", action="store_true", help="fit whole photo with white bars instead of cropping")
    ap.add_argument("--no-marks", action="store_true", help="omit crop ticks")
    ap.add_argument("--lift", type=float, default=0.0,
                    help="brighten every photo by this much (0.10 = slight, 0.20 = noticeable)")
    ap.add_argument("--auto", action="store_true", help="also brighten dark photos individually")
    ap.add_argument("--auto-target", type=float, default=0.45,
                    help="average brightness --auto aims for, 0-1 (default 0.45)")
    ap.add_argument("--auto-max", type=float, default=0.35, help="most --auto may brighten one photo")
    ap.add_argument("--sharpen", type=float, default=0.0, metavar="FACTOR",
                    help="sharpen every photo by this factor (0 = off, 0.5 = subtle, 1 = strong; default 0)")
    ap.add_argument("--test-sheet", type=Path, metavar="PHOTO",
                    help="make only a brightness calibration sheet from this photo")
    opts = ap.parse_args()
    if opts.sharpen < 0:
        ap.error("--sharpen must be 0 or higher")
    opts.out.mkdir(parents=True, exist_ok=True)

    letter = (img2pdf.in_to_pt(SHEET_W_IN), img2pdf.in_to_pt(SHEET_H_IN))
    layout = img2pdf.get_layout_fun(letter)

    if opts.test_sheet:
        out = opts.out / "brightness_test.pdf"
        out.write_bytes(img2pdf.convert([jpeg_bytes(make_test_sheet(opts.test_sheet, opts), opts.ppi)],
                                        layout_fun=layout))
        print(f"wrote {out} - print it with your normal photo settings and pick a band")
        return

    files = sorted(p for p in opts.src.rglob("*") if p.suffix.lower() in EXTS)
    if not files:
        sys.exit(f"No photos found in {opts.src}")

    warnings = [w for f in files if (w := low_res_warning(f))]
    pairs = [files[i:i + 2] for i in range(0, len(files), 2)]
    print(f"{len(files)} photos -> {len(pairs)} sheets at {opts.ppi} ppi"
          + (f", lift +{opts.lift:.2f}" if opts.lift else "") + (", auto-brighten on" if opts.auto else "")
          + (f", sharpen {opts.sharpen:g}" if opts.sharpen else ""))

    index_lines = []
    for b in range(0, len(pairs), opts.batch):
        chunk = pairs[b:b + opts.batch]
        pages = []
        for n, pair in enumerate(chunk, b + 1):
            sheet, lifts = make_sheet(pair, opts)
            pages.append(jpeg_bytes(sheet, opts.ppi))
            index_lines.append(f"sheet {n:03d}: " + " | ".join(
                p.name + (f" (auto +{a:.2f})" if a > 0.005 else "") for p, a in zip(pair, lifts)))
        name = opts.out / f"sheets_{b + 1:03d}-{b + len(chunk):03d}.pdf"
        name.write_bytes(img2pdf.convert(pages, layout_fun=layout))
        print(f"  wrote {name.name}  ({len(chunk)} sheets)")

    # which photo is on which sheet (and how much auto-brightening it got),
    # handy if a sheet misfeeds and needs a reprint
    (opts.out / "sheet_index.txt").write_text("\n".join(index_lines) + "\n")
    if warnings:
        (opts.out / "low_res_warnings.txt").write_text("\n".join(warnings) + "\n")
        print(f"{len(warnings)} photos are low resolution - see low_res_warnings.txt")


if __name__ == "__main__":
    main()