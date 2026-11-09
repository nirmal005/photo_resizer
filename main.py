#!/usr/bin/env python3
"""
main.py - lay out 5x7 photos two per US Letter sheet for an Epson ET-4955.

Each Letter sheet (8.5 x 11 in, portrait) holds two 7 x 5 in photos stacked
vertically. Portrait photos are rotated 90 degrees to fit. The two photos share one
cut line in the middle, and crop ticks in the margins show where to trim.

Sheets are written as PDFs in batches (default 10 sheets each) named batch_1.pdf,
batch_2.pdf, ... Numbering continues from the highest batch already in the output
folder. After each batch PDF is written, its photos are moved to SRC/processed so
they are not printed again on the next run (use --no-move to keep them in place).

BRIGHTNESS
  Prints usually look darker than a backlit screen. Two separate corrections:
  --lift X   Same brightening for every photo, to make up for the printer/paper
             (found with --test-sheet). It's a midtone curve: shadows and
             mid-tones come up, and white highlights don't blow out.
  --auto     Per-photo: dark/underexposed photos get brightened toward a normal
             exposure; photos that are already bright are left alone.
  Both can be used together. Auto runs first, then the lift.

WATERMARK
  --enable_watermark true   Stamp each photo with the 5-digit code at the start of
                            its file name (e.g. 12345_beach.jpg -> "12345").
  Position, opacity, size, color and font come from the .env file next to main.py
  (see .env.example).

Setup (once):
    pip install -r requirements.txt

Usage:
    # 1) Make one calibration sheet from a typical photo and print it
    python main.py  photos out --test-sheet photos/IMG_0123.jpg
    # 2) Pick the band that best matches a professional print, e.g. +0.15
    python main.py  photos out --auto --lift 0.15

    python main.py  photos out --fit                     # don't crop; add white bars instead
    python main.py  photos out --ppi 720                 # only if photos are >= 3600x5040 px
    python main.py  photos out --batch 5                 # 5 sheets per PDF
    python main.py  photos out --sharpen 0.8             # 0 = off, 0.5 = subtle, 1 = strong
    python main.py  photos out --enable_watermark true   # stamp the 5-digit code on each photo
"""
import argparse
import io
import math
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageCms, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

import img2pdf

EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}
SHEET_W_IN, SHEET_H_IN = 8.5, 11.0
PHOTO_W_IN, PHOTO_H_IN = 7.0, 5.0   # landscape slot; two of them stack vertically
PROCESSED_DIR = "processed"
CODE_RE = re.compile(r"^(\d{5})_")
BATCH_RE = re.compile(r"^batch_(\d+)\.pdf$", re.IGNORECASE)


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


# ---------------------------------------------------------------- watermark
def str2bool(v: str) -> bool:
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got {v!r}")


def photo_code(path: Path) -> str | None:
    """The 5-digit code at the start of the file name, e.g. 12345_beach.jpg -> '12345'."""
    m = CODE_RE.match(path.name)
    return m.group(1) if m else None


def load_watermark_settings(ap: argparse.ArgumentParser) -> argparse.Namespace:
    """Read watermark settings from .env next to this script (real environment
    variables take precedence)."""
    load_dotenv(Path(__file__).resolve().with_name(".env"))

    def num(name, default, lo, hi):
        raw = os.getenv(name, str(default))
        try:
            val = float(raw)
        except ValueError:
            ap.error(f"{name}={raw!r} in .env is not a number")
        if not lo <= val <= hi:
            ap.error(f"{name}={val} in .env must be between {lo} and {hi}")
        return val

    color = os.getenv("WATERMARK_COLOR", "white")
    try:
        rgb = ImageColor.getrgb(color)[:3]
    except ValueError:
        ap.error(f"WATERMARK_COLOR={color!r} in .env is not a color (use a name like white or #RRGGBB)")
    return argparse.Namespace(
        x=num("WATERMARK_X", 0.95, 0.0, 1.0),
        y=num("WATERMARK_Y", 0.95, 0.0, 1.0),
        opacity=num("WATERMARK_OPACITY", 0.5, 0.0, 1.0),
        size=num("WATERMARK_SIZE", 0.06, 0.005, 1.0),
        color=rgb,
        font=os.getenv("WATERMARK_FONT", "arial.ttf"),
    )


def watermark_font(name: str, px: int):
    try:
        return ImageFont.truetype(name, px)
    except OSError:
        try:
            return ImageFont.load_default(size=px)
        except TypeError:        # older Pillow
            return ImageFont.load_default()


def add_watermark(img: Image.Image, text: str, wm) -> Image.Image:
    """Draw `text` on `img`. wm.x / wm.y (0-1) place it: 0,0 = top-left corner,
    1,1 = bottom-right corner, 0.5,0.5 = centered. The text always stays inside the photo."""
    px = max(8, round(min(img.size) * wm.size))
    f = watermark_font(wm.font, px)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    left, top, right, bottom = d.textbbox((0, 0), text, font=f)
    tw, th = right - left, bottom - top
    x = round(wm.x * max(0, img.width - tw)) - left
    y = round(wm.y * max(0, img.height - th)) - top
    d.text((x, y), text, font=f, fill=(*wm.color, round(255 * wm.opacity)))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


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
    rotated = img.height > img.width
    if rotated:                                 # portrait photo -> rotate into landscape slot
        img = img.rotate(90, expand=True)
    if opts.fit:
        img = ImageOps.contain(img, (slot_w, slot_h), Image.LANCZOS)
    else:
        img = ImageOps.fit(img, (slot_w, slot_h), Image.LANCZOS, centering=(0.5, 0.5))
    a = auto_lift(img, opts.auto_target, opts.auto_max) if opts.auto else 0.0
    img = apply_gamma(img, gamma_for_lift(a) * gamma_for_lift(opts.lift))
    img = sharpen(img, opts.sharpen, opts.ppi)

    code = photo_code(path) if opts.enable_watermark else None
    if code:
        # place the watermark relative to the photo as it is viewed (upright),
        # not as it sits rotated on the sheet
        if rotated:
            img = img.transpose(Image.Transpose.ROTATE_270)
        img = add_watermark(img, code, opts.wm)
        if rotated:
            img = img.transpose(Image.Transpose.ROTATE_90)

    if opts.fit:
        canvas = Image.new("RGB", (slot_w, slot_h), "white")
        canvas.paste(img, ((slot_w - img.width) // 2, (slot_h - img.height) // 2))
        return canvas, a
    return img, a


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
    base_opts = argparse.Namespace(**{**vars(opts), "lift": 0.0, "auto": False, "enable_watermark": False})
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


def next_batch_number(out: Path) -> int:
    """1 for an empty folder, otherwise one more than the highest batch_N.pdf there."""
    nums = [int(m.group(1)) for p in out.iterdir() if (m := BATCH_RE.match(p.name))]
    return max(nums, default=0) + 1


def move_to_processed(files, src: Path) -> None:
    """Move photos into SRC/processed, keeping their subfolder layout. Never overwrites:
    a name clash gets a _1, _2, ... suffix."""
    root = src / PROCESSED_DIR
    for f in files:
        dest = root / f.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        k = 1
        while dest.exists():
            dest = dest.with_name(f"{f.stem}_{k}{f.suffix}")
            k += 1
        shutil.move(str(f), str(dest))


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
    ap.add_argument("--enable_watermark", "--enable-watermark", dest="enable_watermark",
                    type=str2bool, nargs="?", const=True, default=False, metavar="true|false",
                    help="stamp each photo's 5-digit file-name code on it; settings come from .env")
    ap.add_argument("--no-move", action="store_true",
                    help=f"leave photos in place instead of moving them to SRC/{PROCESSED_DIR}")
    ap.add_argument("--test-sheet", type=Path, metavar="PHOTO",
                    help="make only a brightness calibration sheet from this photo")
    opts = ap.parse_args()
    if opts.sharpen < 0:
        ap.error("--sharpen must be 0 or higher")
    if opts.batch < 1:
        ap.error("--batch must be 1 or higher")
    opts.wm = load_watermark_settings(ap) if opts.enable_watermark else None
    opts.out.mkdir(parents=True, exist_ok=True)

    letter = (img2pdf.in_to_pt(SHEET_W_IN), img2pdf.in_to_pt(SHEET_H_IN))
    layout = img2pdf.get_layout_fun(letter)

    if opts.test_sheet:
        out = opts.out / "brightness_test.pdf"
        out.write_bytes(img2pdf.convert([jpeg_bytes(make_test_sheet(opts.test_sheet, opts), opts.ppi)],
                                        layout_fun=layout))
        print(f"wrote {out} - print it with your normal photo settings and pick a band")
        return

    src = opts.src.resolve()
    processed = src / PROCESSED_DIR
    # skip hidden files: macOS copies leave a "._name.jpg" metadata file next to every photo
    candidates = sorted(p for p in src.rglob("*")
                        if p.is_file() and not p.name.startswith(".")
                        and p.suffix.lower() in EXTS and processed not in p.parents)

    # skip (and report) anything that isn't a readable image instead of crashing;
    # skipped files are not moved to processed
    files, warnings, unreadable = [], [], []
    for f in candidates:
        try:
            w = low_res_warning(f)
        except Exception as e:
            unreadable.append(f"{f}: {e}")
            continue
        files.append(f)
        if w:
            warnings.append(w)
    if unreadable:
        (opts.out / "unreadable_files.txt").write_text("\n".join(unreadable) + "\n", encoding="utf-8")
        print(f"{len(unreadable)} files could not be opened as images and were skipped "
              f"- see unreadable_files.txt")
    if not files:
        sys.exit(f"No new photos found in {opts.src} (already-printed photos are in {processed})")

    if opts.enable_watermark:
        no_code = [f.name for f in files if not photo_code(f)]
        if no_code:
            print(f"{len(no_code)} photos have no 5-digit code at the start of the name "
                  f"and will not be watermarked, e.g. {no_code[0]}")
    pairs = [files[i:i + 2] for i in range(0, len(files), 2)]
    print(f"{len(files)} photos -> {len(pairs)} sheets at {opts.ppi} ppi"
          + (f", lift +{opts.lift:.2f}" if opts.lift else "") + (", auto-brighten on" if opts.auto else "")
          + (f", sharpen {opts.sharpen:g}" if opts.sharpen else "")
          + (", watermark on" if opts.enable_watermark else ""))

    batch_no = next_batch_number(opts.out)
    index_path = opts.out / "sheet_index.txt"
    for b in range(0, len(pairs), opts.batch):
        chunk = pairs[b:b + opts.batch]
        name = opts.out / f"batch_{batch_no}.pdf"
        pages, index_lines = [], []
        for page, pair in enumerate(chunk, 1):
            sheet, lifts = make_sheet(pair, opts)
            pages.append(jpeg_bytes(sheet, opts.ppi))
            index_lines.append(f"{name.name} page {page}: " + " | ".join(
                p.name + (f" (auto +{a:.2f})" if a > 0.005 else "") for p, a in zip(pair, lifts)))
        name.write_bytes(img2pdf.convert(pages, layout_fun=layout))
        # which photo is on which page (and how much auto-brightening it got),
        # handy if a sheet misfeeds and needs a reprint
        with index_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(index_lines) + "\n")
        batch_photos = [p for pair in chunk for p in pair]
        if not opts.no_move:
            move_to_processed(batch_photos, src)
        print(f"  wrote {name.name}  ({len(chunk)} sheets, {len(batch_photos)} photos"
              + ("" if opts.no_move else f" moved to {PROCESSED_DIR}") + ")")
        batch_no += 1

    if warnings:
        (opts.out / "low_res_warnings.txt").write_text("\n".join(warnings) + "\n", encoding="utf-8")
        print(f"{len(warnings)} photos are low resolution - see low_res_warnings.txt")


if __name__ == "__main__":
    main()
