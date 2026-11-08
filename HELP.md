# Photo Resizer – 5x7 Print Sheets

`main.py` takes a folder of photos and lays them out **two 5x7 photos per US Letter sheet** (8.5 x 11 in, portrait), stacked one above the other. The sheets are saved as print-ready PDFs. It was set up for an Epson ET-4955, but any printer that prints Letter-size photo paper will work (borderless printing isn't needed).

- Portrait photos are rotated 90° so they fill the landscape 7 x 5 in slot.
- The two photos share one cut line in the middle. Crop marks in the margins show where to trim.
- PDFs are written in batches (default 10 sheets each). Print one batch, load more paper, then print the next.
- 500 photos → 250 sheets → 25 PDFs.

---

## Setup (once)

```powershell
cd C:\source\python\photo_resizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # pillow, img2pdf
```

After that, activate the venv (`.\.venv\Scripts\Activate.ps1`) each time you open a new terminal.

---

## Basic usage

```powershell
python .\main.py <SRC> <OUT> [options]
```

| Argument | Meaning |
|---|---|
| `SRC` | Folder with your photos. **Subfolders are included.** Supported: `.jpg .jpeg .png .tif .tiff .webp` (`.heic` see Troubleshooting). |
| `OUT` | Folder where the PDFs go. It is created if it doesn't exist. |

Photos are placed in **alphabetical filename order**, two per sheet.

Show the built-in help at any time:

```powershell
python .\main.py --help
```

---

## Your command, explained

```powershell
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads" --lift .2 --sharpen 0.5 --ppi 720
```

| Part | What it does |
|---|---|
| `"C:\Users\nirma\Downloads\photo"` | Reads every photo in this folder (and its subfolders). |
| `"C:\Users\nirma\Downloads"` | Writes the PDFs and text files into your Downloads folder. |
| `--lift .2` | Brightens **every** photo by 0.20 – a noticeable lift. Shadows and mid-tones come up; whites don't blow out. Makes up for prints looking darker than a backlit screen. |
| `--sharpen 0.5` | Subtle sharpening, applied at the final print size. |
| `--ppi 720` | Builds sheets at 720 pixels per inch (Epson's high-quality native resolution). Only worth it if your photos are at least **3600 x 5040 px**; otherwise it's slower and bigger with no visible gain – use the default 360. |

Quotes around the paths are needed only if a path has spaces, but they never hurt.

---

## All options

### Layout and output

| Option | Default | Description |
|---|---|---|
| `--ppi {300,360,720}` | `360` | Sheet resolution. Epson drivers work natively at 360 and 720. 720 needs photos ≥ 3600 x 5040 px to benefit and makes much larger PDFs. |
| `--batch N` | `10` | Number of sheets per PDF. Use a smaller number if your tray holds less paper. |
| `--fit` | off | Show the **whole** photo with white bars instead of cropping it to fill 5x7. (Default crops from the center.) |
| `--no-marks` | off | Leave out the crop marks in the margins. |

### Brightness

Prints usually look darker than the screen. There are two separate fixes, and you can use both together (auto runs first, then lift).

| Option | Default | Description |
|---|---|---|
| `--lift X` | `0.0` | Same brightening for every photo, to make up for your printer/paper. `0.10` = slight, `0.15` = moderate, `0.20` = noticeable, `0.30` = strong. Find the right value with `--test-sheet`. |
| `--auto` | off | Per photo: dark or underexposed photos get brightened toward a normal exposure. Photos that are already bright are left alone. |
| `--auto-target T` | `0.45` | Average brightness (0–1) that `--auto` aims for. Higher = brighter results. |
| `--auto-max M` | `0.35` | The most `--auto` may brighten any single photo. Stops night shots from turning grey. |
| `--test-sheet PHOTO` | – | Makes **only** a calibration sheet (`brightness_test.pdf`) from one photo, showing it in 10 bands from `+0.00` to `+0.50`. No other sheets are made. |

### Sharpening

| Option | Default | Description |
|---|---|---|
| `--sharpen FACTOR` | `0` | `0` = off, `0.5` = subtle, `0.8` = medium, `1` = strong. Must be 0 or higher. The effect is scaled to the ppi, so a given value looks about the same on paper at any resolution. |

---

## Recommended workflow

**1. Find your brightness lift (do this once per paper type).**

```powershell
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads" --test-sheet "C:\Users\nirma\Downloads\photo\IMG_0123.jpg" --ppi 720
```

Print `brightness_test.pdf` with your normal photo settings, on the paper you'll really use. Pick the band that looks most like a professional print and note its number (for example `+0.20`).

**2. Make all the sheets with that value.**

```powershell
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads" --lift .2 --sharpen 0.5 --ppi 720
```

Add `--auto` if some photos are much darker than others.

**3. Print each PDF**, reload paper, print the next.

---

## Printing settings (important)

In the print dialog:

- Paper size: **Letter**
- Scale: **Actual size / 100%** – *not* "Fit to page", or the photos won't be exactly 5x7.
- Paper type: the photo paper you loaded (e.g. Epson Premium Photo Paper Glossy)
- Quality: **High / Best Photo**
- Turn off any printer "auto-fix" or "enhance" options – the script has already done the brightening.

Then cut along the crop marks: one cut across the middle, then trim the sides and the top/bottom.

---

## What gets created in OUT

| File | Contents |
|---|---|
| `sheets_001-010.pdf`, `sheets_011-020.pdf`, … | The printable sheets, `--batch` sheets per file. |
| `sheet_index.txt` | Which photos are on which sheet, and how much `--auto` brightened each one. Use it to reprint a sheet that misfed. |
| `low_res_warnings.txt` | Only if needed: photos smaller than 1500 x 2100 px (300 ppi at 5x7), which may print soft. |
| `brightness_test.pdf` | Only with `--test-sheet`. |

Running again into the same folder **overwrites** these files.

---

## More examples

```powershell
# Default quality, no adjustments
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints"

# Keep the whole photo (white bars), no crop marks
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --fit --no-marks

# Auto-fix dark photos plus a small overall lift
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --auto --lift 0.15

# Brighter auto target, 5 sheets per PDF
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --auto --auto-target 0.5 --batch 5
```

Tip: writing output to its own folder (like `Downloads\prints`) keeps the PDFs from mixing with your other downloads.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No photos found in ...` | Check the SRC path and that the files have a supported extension. |
| Error opening `.heic` files | Pillow can't read HEIC by itself. Convert them to JPG first, or move them out of the folder. |
| Prints are not exactly 5x7 | Print at **Actual size / 100%**, not "Fit to page". |
| Prints still too dark | Raise `--lift` (or re-run `--test-sheet`), or add `--auto`. |
| Prints look washed out / grey | Lower `--lift`, or lower `--auto-max`. |
| Halos around edges | Lower `--sharpen` (try 0.3) or set it to 0. |
| Very slow / huge PDFs | Use `--ppi 360` (default) unless photos are ≥ 3600 x 5040 px. |
| An odd number of photos | The last sheet just has one photo on top; the bottom half stays blank. |
