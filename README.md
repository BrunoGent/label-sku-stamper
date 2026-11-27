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
3. Stamps those lines in blue at the bottom of the label (below the address area, clear of the barcode). If the slip says **REPEAT CUSTOMER**, a `*` is added after the first SKU (`**` for very frequent customers, see [Settings](#settings)).
4. Drops the packing slips, so the output contains labels only. **Exception:** an order whose slip has a **note** (for example "2 dark green and 2 wine purple candles") keeps its slip right behind its label, and its label gets a blue `NOTE` line under the SKUs (see [Settings](#settings)).
5. Sorts the labels into the **groups** you define in `sort_groups.json` (for example all 2cm dipped candles together, then tealights, with honey and beeswax last), and by number within each group. Orders that need checking come first, then **priority postage** (a **Tracked 24** or **1st class** label) before everything else, unless you switch that off (see [Priority postage](#priority-postage-tracked-24-and-1st-class-first)).
6. Adds a **pick list** page at the end: the total quantity of each SKU in the batch, for collecting stock. Group titles sit in the SKU column, and the last line is a bold **Total orders** (the number of orders, i.e. labels, in the batch) with its number under the Orders column. Priority orders are flagged in red (a `P1` beside a SKU, and a **PRIORITY orders** count under the total).
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

**Layout alarm.** If a quarter or more of the orders in a batch have no SKU (or a SKU is suspiciously long), a bold red `!! WARNING ... the packing slip layout may have changed` line appears. It means Shopify may have changed the slip and the SKUs could be wrong in bulk: check the labels against the slips before printing. The threshold is `layout_alarm_percent` in `settings.json` (0 turns it off).

## Folders and files

```
label-sku-stamper/
  run.bat                  double-click to run
  watch.bat                leave open to process new downloads automatically
  stamp_sku.py             the program
  requirements.txt         Python packages needed
  settings.json            all options (edit in Notepad)
  sort_groups.json         the label order: which SKUs go together, and in what order
  assets/                  the logo files (logo_thermal.png, logo_colour.png) for the optional logo
  make_logo.py             rebuilds the two logo files from assets/logo_colour_source.png
  docs/                    printable user guide
  Labels/                  results: <name>_sku.pdf          (created on first run)
  done/                    originals after processing        (created on first run)
```

`Labels` and `done` are never deleted by the program and are not uploaded to GitHub (they contain customer names and addresses). If a result file already exists, a time is added to the new name; nothing is overwritten.

## Setup on a new PC

1. Install Python 3 from python.org (tick **Add Python to PATH**) or the Microsoft Store.
2. Get the code: `git clone https://github.com/BrunoGent/label-sku-stamper` (or download the ZIP) into e.g. `C:\beemine-automations\label-sku-stamper`.
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
| `picklist_columns` | `["qty", "sku", "orders"]` | Pick list columns **left to right**; leave a name out to hide that column. Names: `"qty"`, `"sku"`, `"orders"` (SKU always shows). `["sku", "qty"]` puts the SKU first and hides Orders |
| `repeat_star` | true | Slip says "REPEAT CUSTOMER": add `*` after the first SKU on the label. `false` = off |
| `repeat_double_star_from` | 15 | From this many orders (the number in "Order #N" on the slip) use `**` instead. `0` = never |
| `gift_mark` | true | Slip's NOTES say `GIFT MESSAGE`: add that text as a last line on the label and list the order in the summary. `false` = off |
| `gift_text` | `GIFT MESSAGE` | The words stamped on a gift-message label |
| `note_mark` | true | The order's slip has a note: add a `NOTE` line under the SKUs on the label and list the order in the summary. `false` = off |
| `note_text` | `NOTE` | The word stamped on such a label |
| `keep_note_slips` | true | Keep the 4x6 packing slip of an order with a note right behind its label, so the note can be read. `false` = drop it like the other slips |
| `cover_marketplace_seller` | false | White box over "MARKETPLACE SELLER" on the label (see [Covering wording and the logo](#covering-wording-and-adding-the-logo-optional)) |
| `cover_shopify` | false | White box over the word "Shopify" at the bottom right |
| `shopify_replacement` | `beeminedorset.com` | Text written where "Shopify" was (only when `cover_shopify` is true). `""` = leave it blank |
| `logo` | false | The logo replaces "MARKETPLACE SELLER" (that wording is covered too) |
| `logo_style` | `thermal` | `thermal` = black and white for the thermal label printer, `colour` = full colour |
| `logo_height` | 34 | Logo height in points (the block it replaces is about 33 tall; taller runs into the SKU lines) |
| `picklist_group_titles` | true | Show each group's name (from `sort_groups.json`) as a bold title with a line under it |
| `picklist_page_per_group` | false | `true` = start every group on a new page |
| `picklist_priority_flag` | true | Pick list: a red `P<n>` beside a SKU when `n` of its orders are priority postage, and a red **PRIORITY orders** count under Total orders. `false` = off |
| `priority_words` | `["1st class", "first class", "special delivery"]` | A label whose text contains one of these phrases is priority postage. (Tracked 24 is not in this list: it is found from the big `24` on the label.) |
| `layout_alarm_percent` | 25 | Warn loudly if this percentage (or more) of the orders have no SKU: Shopify may have changed the slip layout. `0` = off |
| `open_after` | true | Open the finished PDF automatically |
| `move_originals` | true | Move the original download to `done\` (when picked from Downloads, or in watch mode) |
| `strip_typed_text` | false | Remove text typed by hand onto the original labels |
| `out_dir`, `done_dir` | `Labels`, `done` | Where results and processed originals go (relative to the program folder, or a full path) |
| `downloads` | `null` | `null` = your Windows Downloads folder, or a path such as `"D:/Downloads"` |
| `pattern` | `shipping*.pdf` | File names picked up from Downloads |
| `watch_seconds` | 2 | Watch mode: how often to look for new downloads |

**Repeat customers.** The program does not know who is a repeat customer; it reads the packing slip. Shopify prints "★ REPEAT CUSTOMER (Order #2) ★" on the slip for web and eBay orders. Etsy orders show it only if the Etsy-Shopify sync tags them and the packing slip template has the repeat-customer line (the template is in the `shopify-packing-slip` project). Slip says repeat, label gets `*`; no repeat text, no star.

**Gift messages.** Etsy makes the A4 gift message page; the sync cannot print it. So the program only reminds you. The Etsy-Shopify sync writes `GIFT MESSAGE (print from Etsy):` into the order note when (and only when) the buyer included a gift message, Shopify prints the note on the slip, and the program reads it from there (only the text after the NOTES heading is searched). The label gets a last line `GIFT MESSAGE` and the summary lists those orders in yellow. A gift order with no message gets nothing.

**Notes.** Shopify only prints the **NOTES** heading on a slip when the order has a note, so that is what the program looks for. Text the Etsy-Shopify sync writes by itself does **not** count: `Imported from Etsy. Receipt ID: ...` and `Etsy discount: ...` (older orders), `GIFT ORDER ...`, and a note that is only the Etsy gift message (that order already gets the `GIFT MESSAGE` line; a `Buyer Note:` next to it does count). An order with a real note shows a yellow `[NOTE]` in the window, the summary lists those orders, and the output PDF has its slip as the page after its label (the window says how many slips were added). The slip is printed on the label printer like any 4x6 page, so it uses one label sheet; set `keep_note_slips` to `false` if you would rather only see the `NOTE` marker.

A typo in a setting name is reported in the window. If the file itself is broken (for example a missing comma) the program says so with the line number and uses its built-in defaults. Command-line options (below) add to or override these for one run.

To tune the position: run with `--preview`, look at the PNG it opens, change `x`, `y` or `size`, and repeat.

## Covering wording and adding the logo (optional)

Shopify's Royal Mail label prints **MARKETPLACE SELLER** at the bottom left and **Shopify** at the bottom right ("Paid and printed from Shopify"). Three options in `settings.json` (all **off** by default) change that:

| Option | What it does |
|---|---|
| `cover_marketplace_seller` | White box over "MARKETPLACE SELLER" |
| `cover_shopify` + `shopify_replacement` | White box over "Shopify", with `beeminedorset.com` (or your own text, or nothing) written in its place. The words "Paid and printed from" stay, so the line reads "Paid and printed from beeminedorset.com" |
| `logo`, `logo_style`, `logo_height` | The logo replaces "MARKETPLACE SELLER" (covering it too). `thermal` = the black and white version for the thermal printer, `colour` = full colour |

- **Where.** The program finds the wording by reading the label's own text, only in the bottom 30% of the label, so it follows the label if it shifts a little and can never cover a customer named Seller. A label that has none of the wording is left as printed, and the window says how many.
- **Order of drawing.** The white boxes, replacement text and logo go on first, then the SKU stamp on top.
- **The thermal logo** is made by `make_logo.py` from `assets/logo_colour_source.png`. Thermal printers print only black dots, so pale colours (the yellow of the bee, the teal shadow) would turn into speckle. The thermal version keeps just the dark parts (the lettering, the outlines and the stripe) as solid black on white, which prints crisply. To change it: replace the source file and run `py make_logo.py` (add a number, e.g. `py make_logo.py 130`, to make it bolder or lighter; default 110).
- **Never covered:** the barcodes, the routing code, the service banner, the Royal Mail logo, the address and the "Post by" date.
- **Check first.** This alters a label that Shopify generated to Royal Mail's format. Make sure Royal Mail and Shopify are happy for it to be changed before relying on it, and print one test label first.

## Priority postage (Tracked 24 and 1st class first)

Orders posted **Tracked 24** or **1st class** print **first**, ahead of every group, so they can be packed and posted first. Inside that block they keep the normal group order. Orders that need checking (`!!`) still come before even these.

- **How the program knows.** Shopify's Royal Mail label prints the service as a huge number beside the word *Tracked*: a big `24` means Tracked 24 (priority), a big `48` means Tracked 48 (normal). For 1st class (and similar) it looks for the phrases in `priority_words` in `settings.json` (`1st class`, `first class`, `special delivery`). Edit that list if your labels say something else.
- **Switch it off or on:** the line `"priority_first": true,` at the top of `sort_groups.json`. `false` = priority orders sit in their normal group, as before. Writing it as text (`"false"`) is reported as a mistake.
- **In the window:** each priority order ends with a red `[PRIORITY: Tracked 24]`, the block has its own heading, and the summary counts them (it also says when the option is off, so a count with "not moved" is not a mistake).
- **On the pick list (last page):** a red `P<n>` beside each SKU that has `n` priority orders, and **PRIORITY orders** with the count under **Total orders**. Switch off with `"picklist_priority_flag": false` in `settings.json`; that setting only affects the pick list, not the order of the labels.
- **Check it works for 1st class:** no 1st class label has been checked yet. After the first one, confirm the window shows `[PRIORITY: 1st class]` for it; if not, add the wording that is printed on that label to `priority_words`.

## Choosing the label order (sort_groups.json)

Labels are printed in groups, in the order the groups are listed in `sort_groups.json`. Open it in Notepad. Each group has a name and a list of SKU patterns:

```json
{"name": "Dipped 2cm", "match": ["* dip 2cm"]},
{"name": "Tealights",  "match": ["* TL"]},
```

Rules:
- **`*` matches anything.** `* dip 2cm` matches `2 dip 2cm`, `4 dip 2cm`, `12 dip 2cm`. Capitals do not matter.
- **`_` matches exactly one character** (not a space). `* V_` matches `6 VL`, `6 VN`, `12 VC` (any one letter after the V) but not `6 V` or `6 Vase`. One pattern can therefore cover a whole family of SKUs: `{"name": "V scents", "match": ["* V_"]}`. This is the same symbol as in the Candle Batch Summary app. (Older files used `?` for this; it still works, but write `_`.)
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

## Adding new SKUs to the label order (--suggest)

When the summary shows a yellow `SKUs not in a named sort group` line, run:

```
py stamp_sku.py --suggest
```
(add a file name to use a specific PDF; the default is the newest download). It writes no PDF. For each unlisted SKU it works out a pattern (`4 VL` and `6 VL` become `* VL`; `40mm` becomes `*mm`), and prints ready-to-paste lines such as:

```
    // matches: 6 VN, 10 VN
    {"name": "VN", "match": ["* VN"]},
```
The lines are also copied to the clipboard. Paste them into `sort_groups.json` **above the "Other" line**, put them in the position you want in the printing order, check the patterns (`*mm` matches anything ending in `mm`; make it more exact if needed), save, and run `--validate`.

## If a settings file breaks, and how to check your edits

Both files are plain text, so a typo is possible: the usual one is a missing or extra comma between lines.

- **What happens:** the program does not stop. It prints a red message with the line number, uses safe defaults (broken `settings.json`: built-in settings; broken `sort_groups.json`: labels sorted by plain SKU order) and repeats the problem in the summary, which then counts it as a problem. The mistake is usually on, or just above, the line number given.
- **Check before you print:** `py stamp_sku.py --validate` checks both files and says "fine" or shows the problem.
- **Reset:** the `defaults\` folder holds known-good copies of both files. Copy the one you need over the broken one in the main folder. (Your own version is also in the git history if you want it back.)

## Testing with an old batch

Use a PDF you downloaded earlier; the originals are in the `done\` folder. Nothing is changed or moved, and a new file is made each time, so it is safe to experiment (for example after editing `sort_groups.json`).

```
py stamp_sku.py "done\shipping_documents_4_x_6 (6).pdf" --check
```
lists every order with its SKU and group in the window and writes nothing. Drop `--check` to also make the PDF in `Labels\` (add `--no-open` to stop it opening). Or drag the old PDF onto `run.bat`. A file named on the command line, or dragged, is left where it is.

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
py stamp_sku.py a.pdf --suggest      print ready-to-paste sort_groups.json lines for SKUs not in a group
py stamp_sku.py --validate           check settings.json and sort_groups.json for mistakes
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
- **Sort.** Orders to check first, then priority postage (`priority_first`), then by group (`sort_groups.json`), then single-item orders by pattern and number (`2 dip` before `12 dip`), then multi-item orders in that group.
- **Notes.** `slip_note` reads the text after the NOTES heading of each slip, removes the sync's own wording (`SYSTEM_NOTE_RE`) and a gift-message-only note, and what is left is the note. The slip's page number is kept so the slip can be copied to the output behind its label.
- **Priority.** Read from the label page (not the slip): a word `24` at least 30 points tall on a page containing "Tracked", or a phrase from `priority_words`.
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

## Tests

`py -m unittest discover -s tests -v` runs the automated checks. They build small synthetic slips (no customer data) and test the SKU reading, grouping, suggestions and the layout alarm. Run them after any change to `stamp_sku.py`, and add a case whenever a real slip is read wrongly.

## Limitations

- Built around Shopify's 4x6 packing slip and the Royal Mail label layout seen so far (blank area at the bottom of the label). Other layouts need the position re-tuned.
- Priority postage is read from Royal Mail's label layout (the big `24` beside "Tracked") and from the phrases in `priority_words`. If Shopify or Royal Mail change the label, the program silently treats orders as normal, so glance at the window's priority count against what you bought.
- Items with no SKU are detected from how the title wraps; an unusual title can be misjudged. These cases show up as flagged orders, not as silently wrong SKUs.
- Windows is the supported platform (`.bat` files). The Python program itself also runs elsewhere.

## Documentation

- **User guide (printable):** `docs/Label-Stamper-User-Guide.docx`, for anyone who runs the app.
- The full SOPs (how to use, and a technical manual) live in the Beemine operating manual: SOP-FUL-001 and SOP-TEC-001.
