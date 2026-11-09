# Photo Resizer – 5x7 Print Sheets

`main.py` takes a folder of photos and lays them out **two 5x7 photos per US Letter sheet** (8.5 x 11 in, portrait), stacked one above the other. The sheets are saved as print-ready PDFs. It was set up for an Epson ET-4955, but any printer that prints Letter-size photo paper will work (borderless printing isn't needed).

- Portrait photos are rotated 90° so they fill the landscape 7 x 5 in slot.
- The two photos share one cut line in the middle. Crop marks in the margins show where to trim.
- PDFs are written in batches (default 10 sheets each) named `batch_1.pdf`, `batch_2.pdf`, `batch_3.pdf`, … Print one batch, load more paper, then print the next.
- 500 photos → 250 sheets → 25 PDFs.
- After each batch PDF is written, its photos are **moved to a `processed` subfolder** of the source folder, so the next run only picks up new photos.
- Optional **watermark**: each photo's 5-digit file-name code (e.g. `12345_beach.jpg` → `12345`) can be stamped on it.

---

## Setup (once)

```powershell
cd C:\source\python\photo_resizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # pillow, img2pdf, python-dotenv
copy .env.example .env               # watermark settings (only needed for --enable_watermark)
```

After that, activate the venv (`.\.venv\Scripts\Activate.ps1`) each time you open a new terminal.

---

## Basic usage

```powershell
python .\main.py <SRC> <OUT> [options]
```

| Argument | Meaning |
|---|---|
| `SRC` | Folder with your photos. **Subfolders are included**, except `SRC\processed`. Supported: `.jpg .jpeg .png .tif .tiff .webp` (`.heic` see Troubleshooting). |
| `OUT` | Folder where the PDFs go. It is created if it doesn't exist. |

Photos are placed in **alphabetical order by path**, two per sheet.

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
| `"C:\Users\nirma\Downloads"` | Writes `batch_N.pdf` files and `sheet_index.txt` into your Downloads folder. Printed photos move to `Downloads\photo\processed`. |
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
| `--no-move` | off | Leave photos where they are instead of moving them to `SRC\processed`. Handy for a trial run. |

### Watermark

| Option | Default | Description |
|---|---|---|
| `--enable_watermark true` | `false` | Stamp each photo with the 5-digit code at the start of its file name. `--enable_watermark` on its own, or `--enable-watermark`, also works. `false` turns it off. |

The file name must **start with exactly 5 digits followed by an underscore**: `12345_beach.jpg` gets `12345`. Photos without a code (e.g. `IMG_0001.jpg`) are printed without a watermark, and the script tells you how many there were.

Position, opacity and look come from the **`.env`** file next to `main.py` (copy `.env.example` to start):

| Setting | Default | Meaning |
|---|---|---|
| `WATERMARK_X` | `0.95` | Horizontal position, 0 to 1. `0` = left edge, `1` = right edge, `0.5` = centered. |
| `WATERMARK_Y` | `0.95` | Vertical position, 0 to 1. `0` = top edge, `1` = bottom edge. (0,0 is the top-left corner.) |
| `WATERMARK_OPACITY` | `0.5` | `0` = invisible, `1` = fully solid. |
| `WATERMARK_SIZE` | `0.06` | Text height as a fraction of the photo's short side (0.06 ≈ 0.3 in on a 5x7). |
| `WATERMARK_COLOR` | `white` | A color name or hex like `#FFFFFF`. |
| `WATERMARK_FONT` | `arial.ttf` | TrueType font name or full path. |

Positions are measured on each photo **as you view it upright**, even when a portrait photo is turned sideways on the sheet, and the text always stays fully inside the photo. With `--fit`, the watermark goes on the photo, not the white bars. Values outside 0–1 stop the script with an error.

Example `.env` for a faint code in the top-left corner:

```ini
WATERMARK_X=0.03
WATERMARK_Y=0.03
WATERMARK_OPACITY=0.3
```

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
| `batch_1.pdf`, `batch_2.pdf`, … | The printable sheets, `--batch` sheets per file. |
| `sheet_index.txt` | Which photos are on which page of which batch (e.g. `batch_3.pdf page 2: 12345_a.jpg \| 12346_b.jpg`), and how much `--auto` brightened each one. Use it to reprint a sheet that misfed. |
| `low_res_warnings.txt` | Only if needed: photos smaller than 1500 x 2100 px (300 ppi at 5x7), which may print soft. Replaced on each run that finds some. |
| `unreadable_files.txt` | Only if needed: files with a photo extension that couldn't be opened (corrupt or not really images). They are skipped and left in SRC. |
| `brightness_test.pdf` | Only with `--test-sheet`. |

Running again into the same OUT folder **continues the numbering**: if `batch_1.pdf`–`batch_4.pdf` are already there, the next run starts at `batch_5.pdf`. New lines are added to the end of `sheet_index.txt`. Nothing is overwritten.

### The `processed` folder

Each photo is moved to `SRC\processed` right after its batch PDF is written. Subfolders are kept (`SRC\trip\a.jpg` → `SRC\processed\trip\a.jpg`). If a file with the same name is already there, the moved one gets `_1`, `_2`, … added instead of overwriting it.

- If a run stops partway, the batches already written have their photos moved, so just run it again to carry on.
- To **reprint** photos, move them from `processed` back into SRC (or point SRC at the `processed` folder with `--no-move`).
- `--test-sheet` never moves anything.

---

## More examples

```powershell
# Default quality, no adjustments
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints"

# Keep the whole photo (white bars), no crop marks
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --fit --no-marks

# Auto-fix dark photos plus a small overall lift
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --auto --lift 0.15

# Your command plus the file-name code watermark
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads" --lift .2 --sharpen 0.5 --ppi 720 --enable_watermark true

# Trial run: make PDFs but don't move any photos
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --no-move

# Brighter auto target, 5 sheets per PDF
python .\main.py "C:\Users\nirma\Downloads\photo" "C:\Users\nirma\Downloads\prints" --auto --auto-target 0.5 --batch 5
```

Tip: writing output to its own folder (like `Downloads\prints`) keeps the PDFs from mixing with your other downloads.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No new photos found in ...` | Every photo has already been printed and is in `SRC\processed`. Add new photos, or move some back to reprint them. Also check the SRC path and file extensions. |
| Files starting with `._` (e.g. `._41229_x.jpg`) | Hidden macOS metadata files, not photos. They are skipped automatically and can be deleted. |
| `... could not be opened as images and were skipped` | See `unreadable_files.txt` in OUT. Re-copy or re-export those files. |
| Some photos have no watermark | Their file names don't start with 5 digits and an underscore (e.g. `12345_`). |
| Watermark hard to see | Raise `WATERMARK_OPACITY` or `WATERMARK_SIZE` in `.env`, or change `WATERMARK_COLOR` (white disappears on bright skies). |
| `.env` changes ignored | `.env` must be in the same folder as `main.py`, and the watermark only runs with `--enable_watermark true`. |
| Error opening `.heic` files | Pillow can't read HEIC by itself. Convert them to JPG first, or move them out of the folder. |
| Prints are not exactly 5x7 | Print at **Actual size / 100%**, not "Fit to page". |
| Prints still too dark | Raise `--lift` (or re-run `--test-sheet`), or add `--auto`. |
| Prints look washed out / grey | Lower `--lift`, or lower `--auto-max`. |
| Halos around edges | Lower `--sharpen` (try 0.3) or set it to 0. |
| Very slow / huge PDFs | Use `--ppi 360` (default) unless photos are ≥ 3600 x 5040 px. |
| An odd number of photos | The last sheet just has one photo on top; the bottom half stays blank. |
