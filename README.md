# label-sku-stamper

Turns the 4x6 shipping PDF you download from Shopify into a print-ready **labels-only PDF** with the SKU(s) and quantities from each packing slip stamped on the label in blue, sorted for packing, with a **pick list** as the last page.

```
Shopify PDF:  label | slip | label | slip | ...        (one pair per order)
                       |
                       v
Output PDF:   label with "3 x kg h" stamped on it | label ... | PICK LIST
```

- [What it does](#what-it-does)
- [Quick start (everyday use)](#quick-start-everyday-use)
- [Reading the results](#reading-the-results)
- [Folders and files](#folders-and-files)
- [Setup on a new PC](#setup-on-a-new-pc)
- [Settings](#settings)
- [Command line options](#command-line-options)
- [Watch mode](#watch-mode)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Privacy](#privacy)
- [Limitations](#limitations)
- [Documentation](#documentation)

## What it does

For every order in the Shopify PDF it:

1. Finds the shipping label and its packing slip (the slip is the page after the label).
2. Reads the items on the slip and works out each SKU and quantity. A quantity above 1 is written as `3 x kg h`; a quantity of 1 is just the SKU.
3. Stamps those lines in blue at the bottom of the label (below the address area, clear of the barcode).
4. Drops the packing slips, so the output contains labels only.
5. Sorts the labels into the **groups** you define in `sort_groups.json` (for example all 2cm dipped candles together, then tealights, with honey and beeswax last), and by number within each group. Orders that need checking come first.
6. Adds a **pick list** page at the end: the total quantity of each SKU in the batch, for collecting stock.
7. Saves one PDF in the `Labels` folder and opens it.

## Quick start (everyday use)

1. In Shopify, download the shipping documents (4x6). A file named like `shipping_documents_4_x_6 (6).pdf` appears in Downloads.
2. Double-click **`run.bat`**.
   - With no file given it uses the **newest** `shipping*.pdf` in your Downloads folder.
   - Or drag a PDF onto `run.bat` to use that file instead.
3. Read the list in the black window (see [Reading the results](#reading-the-results)).
4. The finished PDF opens automatically. Check it, then print the whole thing on the label printer (4x6in). The pick list prints last.
5. Press any key to close the window.

The original download is moved to the `done` folder (only when the app picked it itself from Downloads, or in watch mode), so the next run does not pick it up again. Nothing is ever deleted.

## Reading the results

The window shows one line per order, then a summary.

| Marker | Meaning | What to do |
|---|---|---|
| green `ok` | SKU(s) found | Nothing |
| yellow `~~` | The item has **no SKU** on the slip. The `[bracketed option]` from the title (or the start of the title) was stamped instead | Check the packing slip. Fix the SKU in the Shopify/eBay listing |
| red `!!` | No items could be read from the slip. The label shows a red `?? CHECK SLIP` | Read the slip by hand |

The summary ends with a line such as `32 labels, 2 problems` and lists each problem, including pages without a matching label or slip.

## Folders and files

```
labeltest/
  run.bat                  double-click to run
  watch.bat                leave open to process new downloads automatically
  stamp_sku.py             the program
  requirements.txt         Python packages needed
  settings.json            all options (edit in Notepad)
  sort_groups.json         the label order: which SKUs go together, and in what order
  docs/                    printable user guide
  Labels/                  results: <name>_sku.pdf          (created on first run)
  done/                    originals after processing        (created on first run)
```

`Labels` and `done` are never deleted by the program and are not uploaded to GitHub (they contain customer names and addresses). If a result file already exists, a time is added to the new name; nothing is overwritten.

## Setup on a new PC

1. Install Python 3 from python.org (tick **Add Python to PATH**) or the Microsoft Store.
2. Get the code: `git clone https://github.com/BrunoGent/label-sku-stamper` (or download the ZIP) into e.g. `C:\labeltest`.
3. Open a terminal in that folder and install the packages:

   ```
   py -m pip install -r requirements.txt
   ```

   (Use `python -m pip ...` if `py` is not available.) `py` and `python` can be different installs; `run.bat` automatically uses the first one that has the packages.
4. Double-click `run.bat`.

Packages: pypdf, pdfplumber, reportlab, pypdfium2.

## Settings

All the options live in **`settings.json`**: open it in Notepad, change a value, save, and run again (no restart). Lines starting with `//` (or the end of a line after `//`) are notes and are ignored. The label *order* is in the other file, `sort_groups.json` (below). Both files hold no customer data and are part of the repository.

| Setting | Default | Meaning |
|---|---|---|
| `x`, `y` | 40, 378 | Where the first stamped line starts, in points from the **left** and **top** of the label (4x6in = 288 x 432 points) |
| `size` | 11 | Font size in points. Text shrinks automatically if there are many lines |
| `colour` | `[0, 0, 0.85]` | Stamp colour as red, green, blue (each 0 to 1). `[0, 0, 0]` is black |
| `sort_labels` | true | `false` = keep Shopify's order and ignore `sort_groups.json` |
| `title_fallback` | true | Item has no SKU: `true` stamps part of the title, `false` stamps `?? CHECK SLIP` |
| `title_length` | 28 | Characters of the title to stamp (a `[bracketed option]` is used in full) |
| `picklist` | true | `false` = no pick list page |
| `picklist_size` | `4x6` | `4x6` (label printer) or `a4` |
| `picklist_group_titles` | true | Show each group's name (from `sort_groups.json`) as a bold title with a line under it |
| `picklist_page_per_group` | false | `true` = start every group on a new page |
| `open_after` | true | Open the finished PDF automatically |
| `move_originals` | true | Move the original download to `done\` (when picked from Downloads, or in watch mode) |
| `strip_typed_text` | false | Remove text typed by hand onto the original labels |
| `out_dir`, `done_dir` | `Labels`, `done` | Where results and processed originals go (relative to the program folder, or a full path) |
| `downloads` | `null` | `null` = your Windows Downloads folder, or a path such as `"D:/Downloads"` |
| `pattern` | `shipping*.pdf` | File names picked up from Downloads |
| `watch_seconds` | 2 | Watch mode: how often to look for new downloads |

A typo in a setting name is reported in the window. If the file itself is broken (for example a missing comma) the program says so with the line number and uses its built-in defaults. Command-line options (below) add to or override these for one run.

To tune the position: run with `--preview`, look at the PNG it opens, change `x`, `y` or `size`, and repeat.

## Choosing the label order (sort_groups.json)

Labels are printed in groups, in the order the groups are listed in `sort_groups.json`. Open it in Notepad. Each group has a name and a list of SKU patterns:

```json
{"name": "Dipped 2cm", "match": ["* dip 2cm"]},
{"name": "Tealights",  "match": ["* TL"]},
```

Rules:
- **`*` matches anything.** `* dip 2cm` matches `2 dip 2cm`, `4 dip 2cm`, `12 dip 2cm`. Capitals do not matter.
- **Order = order in the file.** Move a group up or down to print it earlier or later. Put things you want at the end (beeswax, honey, non-candles) in the last group.
- **First match wins.** A SKU goes into the first group, from the top, that matches it. So put specific groups (`* dip 2cm`) above general ones (`* dip *`, which then collects the coloured dipped candles).
- **Inside a group**, labels are ordered by the order of the patterns, then by number (`2 dip 2cm`, `4 dip 2cm`, `12 dip 2cm`).
- **Everything else:** a group whose match list is just `["*"]` collects every SKU not listed anywhere, wherever you put that group. With `"warn": true` the window lists those SKUs each run, so you can add them to a proper group.
- **Orders with several items** go with the *latest* group among their items, so an order that includes honey travels with the honey, at the end.
- The pick list uses the same groups and shows each group's `name` as a bold title above its SKUs (`picklist_group_titles`; `picklist_page_per_group` starts each group on a new page).
- **`name`** is only a label: it is the heading shown in the window and above each group on the pick list. It plays no part in matching, so call it anything.
- **Comments:** a line starting with `//` is ignored, so you can leave notes to yourself in the file. (Put each comment on its own line.)
- **Several types in one batch:** list several patterns in one group, e.g. `"match": ["* VN", "* VJ", "* VL"]`. All the VN come first, then all the VJ, then the VL, each by number. Or make a separate group for each if you want a heading per type on the pick list.
- **Numbers sort as numbers**: `2`, `4`, `6`, `12`, `20` (not `12` before `2`). With one pattern the whole group runs 2s, then 4s and so on. With several patterns, each pattern's batch comes first and the numbers run within it. To mix types so that all the 2s come together whatever the letters, use one pattern that covers them, e.g. `"* V*"` (then 4 VL, 4 VN, 4 VV are together).
- The order is not part of the program: edit and save the file, then run again. No restart needed. If the file has a typo the program says so and falls back to plain SKU order. `--no-sort` ignores it and keeps Shopify's order.

## Command line options

```
py stamp_sku.py                      newest shipping*.pdf in Downloads
py stamp_sku.py a.pdf b.pdf          specific files (one result each)
py stamp_sku.py a.pdf --check        list the SKUs found; write nothing
py stamp_sku.py a.pdf --preview      also open a PNG of the busiest label
py stamp_sku.py a.pdf --x 40 --y 372 --size 11
py stamp_sku.py a.pdf --strip        remove text already typed on the labels by hand
py stamp_sku.py a.pdf --no-sort      keep Shopify's order
py stamp_sku.py a.pdf -o out.pdf     choose the output name (one input only)
py stamp_sku.py a.pdf --move         move the original to done\ afterwards
py stamp_sku.py a.pdf --no-open      do not open the result
py stamp_sku.py a.pdf --no-picklist  leave the pick list page out
py stamp_sku.py --downloads D:\x     look in another folder
py stamp_sku.py --watch              watch mode (below)
```

Files given by name stay where they are unless `--move` is added.

## Watch mode

`watch.bat` (or `--watch`) keeps a window open and checks Downloads every couple of seconds. When a new `shipping*.pdf` finishes downloading it stamps it, opens the result and moves the original to `done`. Files already in Downloads when it starts are ignored. It only runs while the window is open; close the window to stop it. It does not start with Windows.

## How it works

- **Page types.** A page containing "SHIP TO" and "ITEMS" (or "Order #123") is a packing slip. Every other page is a label. A slip belongs to the label before it.
- **Items.** Within a slip the text between "ITEMS" and "NOTES" is split into lines, then into item blocks wherever the vertical gap is bigger than normal line spacing (measured from the font size). A bold "3 x" on the left is the quantity.
- **SKU rule.** The SKU is the last line of an item block, unless the line before it was a wrapped line of the title (meaning the last line is just the rest of the title and the item has no SKU).
- **No SKU.** The `[bracketed option]` from the title is stamped, or the first ~28 characters of the title, and the order is flagged `~~`.
- **Stamping.** The text is drawn onto a transparent page and merged on top of the label. It uses Arial if available, and shrinks or uses two columns if there are many lines.
- **Sort.** Orders to check first, then by group (`sort_groups.json`), then single-item orders by pattern and number (`2 dip` before `12 dip`), then multi-item orders in that group.
- **Output.** Sorted labels, then the pick list pages, written to one PDF.

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| "Missing package (pdfplumber)" | The Python used lacks the packages | `py -m pip install -r requirements.txt` |
| "No shipping*.pdf found" | Nothing downloaded yet, or a different name | Download from Shopify, or drag the PDF onto `run.bat` |
| "no packing slips found" | The file is already stamped (name ends `_sku`) or is not a labels+slips PDF | Use the original (it is in `done`) |
| Wrong SKU, or two items merged | Shopify changed the slip layout | `py stamp_sku.py file.pdf --check`; see `parse_items` in `stamp_sku.py` |
| Stamp overlaps label printing | Different label layout | `--preview`, then adjust `x`, `y`, `size` |
| A SKU is in the wrong place in the order | It matched an earlier group, or no group | Edit `sort_groups.json` (specific patterns above general ones) |
| "original is still locked" (watch mode) | Browser or antivirus is using the download | Harmless: it is left where it is |
| The PDF does not open by itself | No default PDF viewer | Open the newest file in `Labels` |
| Too many SKUs to fit | A very large order | Flagged in the summary; read the slip |

## Privacy

Shipping PDFs contain customers' names and addresses. The repository's `.gitignore` excludes `*.pdf`, `*.csv`, `*.png`, `Labels/`, `done/`. Check `git status` before committing. Do not email or share the PDFs.

## Limitations

- Built around Shopify's 4x6 packing slip and the Royal Mail label layout seen so far (blank area at the bottom of the label). Other layouts need the position re-tuned.
- Items with no SKU are detected from how the title wraps; an unusual title can be misjudged. These cases show up as flagged orders, not as silently wrong SKUs.
- Windows is the supported platform (`.bat` files). The Python program itself also runs elsewhere.

## Documentation

- **User guide (printable):** `docs/Label-Stamper-User-Guide.docx`, for anyone who runs the app.
- The full SOPs (how to use, and a technical manual) live in the Beemine operating manual: SOP-FUL-001 and SOP-TEC-001.
