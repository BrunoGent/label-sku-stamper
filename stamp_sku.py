#!/usr/bin/env python3
"""
Shopify 4x6 shipping PDF  ->  labels only, with the SKU(s) from the packing
slip stamped onto each label in blue (e.g. "3 x kg h", "4 VV").

Everyday use (Windows):
    run.bat                      double-click: takes the newest shipping*.pdf in Downloads
    drag a PDF onto run.bat      stamps that file
    watch.bat                    leave open: stamps new Shopify PDFs as they are downloaded

Command line:
    py stamp_sku.py                       # newest shipping*.pdf in Downloads
    py stamp_sku.py a.pdf b.pdf           # specific files
    py stamp_sku.py a.pdf --check         # list what was found, write nothing
    py stamp_sku.py a.pdf --preview       # also save/open a PNG of the busiest label
    py stamp_sku.py --watch               # keep running, process new downloads
    py stamp_sku.py a.pdf --x 40 --y 372 --size 11 --strip

Outputs go to the Labels\\ folder next to this script:
    <name>_sku.pdf         labels only, sorted into the groups in sort_groups.json, SKUs stamped in blue, with a pick list page
                           (totals per SKU, 4x6in) as the LAST page. It opens automatically.

All options are in settings.json (edit in Notepad); the label order is in sort_groups.json.
Needs: pypdf, pdfplumber, reportlab, pypdfium2  (pip install -r requirements.txt)
"""
import argparse, io, json, logging, os, re, shutil, statistics, sys, time
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
except ImportError as e:
    sys.exit(f"Missing package ({e.name}). Run:  py -m pip install -r requirements.txt")

logging.getLogger("pdfminer").setLevel(logging.ERROR)   # silence "FontBBox" noise

HERE = Path(__file__).resolve().parent
os.system("")   # lets Windows 10+ consoles show ANSI colours

GREEN, YELLOW, RED, BOLD, DIM, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[2m", "\033[0m"
CHECK_TEXT = "?? CHECK SLIP"
SLIP_COLUMN_EDGE = 260.0   # right edge (points) of the item text on Shopify's 4x6 slip: titles wrap close to here

DEFAULTS = {
    "x": 40.0, "y": 378.0, "size": 11.0, "colour": [0, 0, 0.85],
    "sort_labels": True,
    "title_fallback": True, "title_length": 28,
    "picklist": True, "picklist_size": "4x6", "picklist_columns": ["qty", "sku", "orders"], "picklist_group_titles": True, "picklist_page_per_group": False,
    "picklist_priority_flag": True, "priority_words": ["1st class", "first class", "special delivery"],
    "repeat_star": True, "repeat_double_star_from": 15,
    "gift_mark": True, "gift_text": "GIFT MESSAGE",
    "note_mark": True, "note_text": "NOTE", "keep_note_slips": True,
    "cover_marketplace_seller": False, "cover_shopify": False, "shopify_replacement": "beeminedorset.com",
    "logo": False, "logo_style": "thermal", "logo_height": 46, "logo_x": 100, "logo_y": 347, "sku_to_top": False,
    "layout_alarm_percent": 25, "open_after": True, "move_originals": True, "strip_typed_text": False,
    "out_dir": "Labels", "done_dir": "done", "downloads": None, "pattern": "shipping*.pdf", "watch_seconds": 2,
}
FILE_ERRORS = []     # problems found while reading settings.json / sort_groups.json (shown again in the summary)
GROUP_OPTS = {"priority_first": True}   # options from the top of sort_groups.json; set by load_groups()
S = dict(DEFAULTS)     # the live settings (settings.json merged over DEFAULTS); set by load_settings()


# --------------------------------------------------------------------------- settings

def downloads_folder():
    """The user's real Downloads folder (follows a relocated Downloads on Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                            ("d", ctypes.c_ubyte * 8)]
            # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
            g = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(buf)) == 0:
                p = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return p
        except Exception:
            pass
    return Path.home() / "Downloads"


def read_json(path):
    """JSON file where // starts a comment (a whole line, or the end of a line). // inside "quotes" is kept."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        in_str, esc, cut = False, False, None
        for i, ch in enumerate(line):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "/" and line[i:i + 2] == "//":
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return json.loads(chr(10).join(out))


def load_settings():
    """Merge settings.json over the defaults. Unknown names are reported (usually a typo)."""
    S.clear()
    S.update(DEFAULTS)
    FILE_ERRORS[:] = [e for e in FILE_ERRORS if not e.startswith("settings.json")]
    f = HERE / "settings.json"
    if f.exists():
        try:
            for k, v in read_json(f).items():
                if k.startswith("_"):
                    continue
                if k in DEFAULTS:
                    S[k] = v
                else:
                    print(f"{YELLOW}settings.json: unknown setting '{k}' ignored (typo?){OFF}")
        except Exception as e:
            print(f"{RED}settings.json ignored (fix the file): {e}{OFF}")
            FILE_ERRORS.append(f"settings.json is broken ({e}) - default settings used")
    bad = [c_ for c_ in (S["picklist_columns"] if isinstance(S["picklist_columns"], list) else ["?"])
           if str(c_).strip().lower() not in ("qty", "sku", "orders")]
    if bad or not isinstance(S["picklist_columns"], list):
        print(f"{YELLOW}settings.json: picklist_columns may only contain \"qty\", \"sku\", \"orders\" (got {bad or S['picklist_columns']}){OFF}")
        FILE_ERRORS.append("settings.json: picklist_columns has an unknown column name - it was ignored")
    if str(S["logo_style"]).lower() not in ("thermal", "colour"):
        FILE_ERRORS.append('settings.json: "logo_style" must be "thermal" or "colour" - "thermal" used')
        S["logo_style"] = "thermal"
    for key, floor in (("logo_height", 1), ("logo_x", 0), ("logo_y", 0)):
        try:
            if float(S[key]) < floor:
                raise ValueError
        except (TypeError, ValueError):
            FILE_ERRORS.append(f'settings.json: "{key}" must be a number (points, at least {floor}) - the built-in value {DEFAULTS[key]} was used')
            S[key] = DEFAULTS[key]
    if S["logo"] and not logo_path().exists():
        FILE_ERRORS.append(f"settings.json: logo is on but {logo_path().name} is missing from the assets folder (run py make_logo.py) - no logo drawn")
    return S


def resolve_dir(value, base=HERE):
    p = Path(value)
    return p if p.is_absolute() else base / p


# --------------------------------------------------------------------------- fonts

_FONT = None


def font_name():
    """Arial (Unicode-ish) when available, else built-in Helvetica."""
    global _FONT
    if _FONT is None:
        _FONT = "Helvetica"
        for cand in (r"C:\Windows\Fonts\arial.ttf", "/Library/Fonts/Arial.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if Path(cand).exists():
                try:
                    pdfmetrics.registerFont(TTFont("LabelFont", cand))
                    _FONT = "LabelFont"
                    break
                except Exception:
                    pass
    return _FONT


_BOLD = None


def font_bold():
    global _BOLD
    if _BOLD is None:
        _BOLD = "Helvetica-Bold"
        if font_name() == "LabelFont":
            for cand in (r"C:\Windows\Fontsrialbd.ttf", "/Library/Fonts/Arial Bold.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
                if Path(cand).exists():
                    try:
                        pdfmetrics.registerFont(TTFont("LabelFontBold", cand))
                        _BOLD = "LabelFontBold"
                        break
                    except Exception:
                        pass
    return _BOLD


def safe_text(t):
    """Drop characters the font can't draw (only matters for the Helvetica fallback)."""
    if font_name() == "Helvetica":
        return t.encode("latin-1", "replace").decode("latin-1")
    return t


# --------------------------------------------------------------------------- parsing

QTY_RE = re.compile(r"^(\d+)$")


def is_slip(text):
    return ("SHIP TO" in text and "ITEMS" in text) or bool(re.search(r"Order\s+#?\d+", text))


REPEAT_RE = re.compile(r"REPEAT\s+CUSTOMER(?:\s*\(\s*Order\s*#?\s*(\d+)\s*\))?", re.I)


PRIORITY_BIG_NUMBER = 30   # points: Shopify's Royal Mail labels print the service as a huge "24" or "48" beside "Tracked"


def label_priority(page, text):
    """The postage service that must go first, read from a LABEL page: 'Tracked 24', or the matching phrase from
    settings.json priority_words ("1st class", ...). '' = ordinary postage (Tracked 48, standard...)."""
    low = text.lower()
    if "tracked" in low:
        for w in page.extract_words(extra_attrs=["size"]):
            if w["text"] == "24" and w["size"] >= PRIORITY_BIG_NUMBER:
                return "Tracked 24"
    words = S["priority_words"] if isinstance(S["priority_words"], list) else []
    for word in words:
        if str(word).strip() and str(word).strip().lower() in low:
            return str(word).strip()
    return ""


def decorations_on():
    return bool(S["cover_marketplace_seller"] or S["cover_shopify"] or S["logo"] or S["sku_to_top"])


def label_regions(page):
    """Where Shopify's Royal Mail label prints "MARKETPLACE SELLER" and the word "Shopify" (in points from the top left):
    {"marketplace": (x0, top, x1, bottom, size), "shopify": (...)}, only the ones found. Only the footer of the label
    (below 70% of its height) is searched, so a customer named Seller can never be covered."""
    out = {}
    low = page.height * 0.7
    words = [w for w in page.extract_words(extra_attrs=["size"]) if w["top"] > low]
    mk = [w for w in words if w["text"].lower() in ("marketplace", "seller") and w["size"] >= 10]
    if {w["text"].lower() for w in mk} == {"marketplace", "seller"}:
        out["marketplace"] = (min(w["x0"] for w in mk), min(w["top"] for w in mk),
                              max(w["x1"] for w in mk), max(w["bottom"] for w in mk), max(w["size"] for w in mk))
    sh = [w for w in words if w["text"].lower() == "shopify"]
    if sh:
        w = max(sh, key=lambda w: w["top"])
        out["shopify"] = (w["x0"], w["top"], w["x1"], w["bottom"], w["size"])
    ft = [w for w in words if w["text"].lower() in ("footprint", "carbon") and w["size"] <= 8]
    if ft:                                                            # Royal Mail's small print along the bottom: keep SKUs clear of it
        out["footer"] = (min(w["x0"] for w in ft), min(w["top"] for w in ft), max(w["x1"] for w in ft), max(w["bottom"] for w in ft), 6)
    return out


def stamp_position(regions, x, y, size):
    """Where the SKU stamp goes: (x, y of the first baseline, max width or None, lowest point or None).
    sku_to_top: starts at the top-left of the block where "MARKETPLACE SELLER" is printed (that wording is covered) and
    stops above Royal Mail's small print. With a logo to the right of the text, the text is kept clear of it."""
    max_w = bottom = None
    mk = regions.get("marketplace")
    if S["sku_to_top"] and mk:
        x, y = mk[0], mk[1] + size * 0.9
        ft = regions.get("footer")
        bottom = (ft[1] - 3) if ft else 408.0
    if S["logo"] and logo_path().exists() and float(S["logo_x"]) > x:
        max_w = float(S["logo_x"]) - x - 4
    return x, y, max_w, bottom


ASSETS = Path(__file__).resolve().parent / "assets"      # the logo files; always next to the program (HERE can be pointed elsewhere in tests)


def logo_path():
    return ASSETS / ("logo_colour.png" if str(S["logo_style"]).lower() == "colour" else "logo_thermal.png")


def decoration_overlay(w, h, regions):
    """A transparent page with white boxes over the wording to hide, the replacement text and the logo. -> pypdf page,
    or None when there is nothing to draw on this label. Merged UNDER the SKU stamp."""
    pad = 1.5
    mk, sh = regions.get("marketplace"), regions.get("shopify")
    hide_mk = bool(mk and (S["cover_marketplace_seller"] or S["sku_to_top"]))   # sku_to_top writes the SKUs where it was
    hide_sh = bool(sh and S["cover_shopify"])
    show_logo = bool(S["logo"] and logo_path().exists())
    if not (hide_mk or hide_sh or show_logo):
        return None
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFillColorRGB(1, 1, 1)
    for hide, r in ((hide_mk, mk), (hide_sh, sh)):
        if hide:
            c.rect(r[0] - pad, h - r[3] - pad, (r[2] - r[0]) + 2 * pad, (r[3] - r[1]) + 2 * pad, stroke=0, fill=1)
    if hide_sh and str(S["shopify_replacement"]).strip():             # the replacement text, right-aligned where "Shopify" ended
        text, fs = safe_text(str(S["shopify_replacement"]).strip()), float(sh[4])
        while fs > 5 and pdfmetrics.stringWidth(text, font_bold(), fs) > sh[2] - 150:
            fs -= 0.5
        c.setFillColorRGB(0, 0, 0)
        c.setFont(font_bold(), fs)
        c.drawRightString(sh[2], h - sh[3] + 0.22 * fs, text)
    if show_logo:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(str(logo_path()))
        iw, ih = img.getSize()
        lx, ly, lh = float(S["logo_x"]), float(S["logo_y"]), float(S["logo_height"])
        lw = lh * iw / ih
        if lx + lw > w - 10:                                          # never run off the right edge of the label
            lw = max(10.0, w - 10 - lx)
            lh = lw * ih / iw
        c.drawImage(img, lx, h - ly - lh, lw, lh, mask="auto")        # logo_x / logo_y = its top-left corner, from the label's top-left
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def order_no(text):
    m = re.search(r"Order\s+#?(\d+)", REPEAT_RE.sub("", text))   # not the "(Order #2)" of the repeat-customer line
    return m.group(1) if m else "?"


def repeat_of(text):
    """The slip says "REPEAT CUSTOMER (Order #4)": -> 4. Says repeat without a number: -> 0. Not a repeat: -> None."""
    m = REPEAT_RE.search(text)
    return None if not m else int(m.group(1) or 0)


def repeat_mark(n):
    """What to stamp after the first SKU: '' (not a repeat, or switched off), '*', or '**' from repeat_double_star_from orders."""
    if n is None or not S["repeat_star"]:
        return ""
    big = S["repeat_double_star_from"]
    return "**" if (big and n >= big) else "*"


def body_lines(page):
    """Text lines of the ITEMS section (qty markers removed) + {top: qty} markers."""
    words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
    items_top = next((w["top"] for w in words if w["text"] == "ITEMS"), None)
    if items_top is None:
        return [], []
    notes_top = next((w["top"] for w in words if w["text"] == "NOTES" and w["top"] > items_top), page.height)
    body = [w for w in words if items_top + 3 < w["top"] < notes_top - 2]

    qty_marks, text = [], []
    skip = set()
    for i, w in enumerate(body):
        nxt = body[i + 1] if i + 1 < len(body) else None
        if ("Bold" in w["fontname"] and QTY_RE.match(w["text"]) and nxt and nxt["text"].lower() == "x"
                and abs(nxt["top"] - w["top"]) < 2):
            qty_marks.append((w["top"], int(w["text"])))
            skip.add(i + 1)
        elif i not in skip:
            text.append(w)

    lines = []
    for w in sorted(text, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) < 2:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "bottom": w["bottom"], "words": [w]})
    for l in lines:
        ws = sorted(l["words"], key=lambda w: w["x0"])
        l["text"] = " ".join(w["text"] for w in ws)
        l["x0"], l["x1"] = ws[0]["x0"], max(w["x1"] for w in ws)
        l["first_w"] = ws[0]["x1"] - ws[0]["x0"]
        l["size"] = statistics.median(w["size"] for w in ws)
    return lines, qty_marks


def parse_items(lines, qty_marks, colmax):
    """[(qty, sku_or_None, title)] for one packing slip.

    Items are blocks of lines (title [wrapped], optional variant, SKU), separated by a gap
    bigger than normal line spacing (measured from the font size, so single-line items work).
    The SKU is the last line of a block - unless the line before it is a *wrapped* title
    line (the last line just continues the title), meaning the item has no SKU at all.
    """
    if not lines:
        return []
    step = 1.5 * statistics.median(l["size"] for l in lines)      # normal line pitch
    blocks, cur = [], [lines[0]]
    for prev, nxt in zip(lines, lines[1:]):
        if nxt["top"] - prev["top"] > step * 1.3:
            blocks.append(cur)
            cur = []
        cur.append(nxt)
    blocks.append(cur)

    out = []
    for b in blocks:
        top, bottom = b[0]["top"], b[-1]["bottom"]
        qty = next((q for t, q in qty_marks if top - 8 <= t <= bottom + 2), 1)
        title = " ".join(l["text"] for l in b)
        sku = None
        if len(b) >= 2:
            prev, last = b[-2], b[-1]
            wrapped = prev["x1"] + last["first_w"] + 1.5 > colmax + 0.5   # next word wouldn't fit -> title continues
            if not wrapped:
                sku = last["text"]
        shown = title_guess(title, S["title_length"]) if S["title_fallback"] else CHECK_TEXT
        out.append((qty, sku or shown, title, sku is None))   # last item: True = no SKU on the slip
    return out


def title_guess(title, limit=28):
    """No SKU on the slip: use the option in [brackets] if there is one, else the start of the title."""
    opts = re.findall(r"\[[^\]]+\]", title)
    if opts:
        return opts[-1]
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return (cut or title[:limit]) + ".."


def fmt(qty, sku):
    s = sku if sku else CHECK_TEXT
    return f"{qty} x {s}" if qty > 1 else s


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


GIFT_RE = re.compile(r"^\W*GIFT\s+MESSAGE", re.I | re.M)


def has_gift_message(text):
    """True when the slip's NOTES section carries a gift message line. The Etsy-Shopify sync writes
    "GIFT MESSAGE (print from Etsy):" (older orders: "Gift Message:"). Only the text after the NOTES
    heading is searched, so an item title can never trigger it. A gift order WITHOUT a message does not count."""
    _, found, notes = text.partition("NOTES")
    return bool(found and GIFT_RE.search(notes))


# Text the Etsy-Shopify sync (or an older version of it) writes into the note by itself. It is not a note to read.
SYSTEM_NOTE_RE = re.compile(
    r"Imported\s+from\s+Etsy\.?\s*Receipt\s+ID:?\s*\d+\.?"
    r"|Etsy\s+discount:\s*£?[\d.,]+\.?"
    r"|(?:🎁\s*)?GIFT\s+ORDER(?:\s*\(\s*Do\s+not\s+show\s+prices\s+on\s+packing\s+slip\s*\))?", re.I)


def slip_note(text):
    """The note to read on a packing slip ('' = none). Shopify only prints the NOTES heading when there is a note.
    Not counted: text the sync writes by itself ("Imported from Etsy. Receipt ID: ...", "Etsy discount: ...",
    "GIFT ORDER ..."), and a note that is only the Etsy gift message (it has its own GIFT MESSAGE mark; a
    "Buyer Note:" next to it does count)."""
    _, found, notes = text.partition("NOTES")
    if not found:
        return ""
    if has_gift_message(text) and "buyer note" not in notes.lower():
        return ""
    rest = SYSTEM_NOTE_RE.sub(" ", notes)
    return " ".join(rest.split()) if re.search(r"\w", rest) else ""


def parse_pdf(src):
    """-> (orders, notes). orders: [{page, order, items}]; notes: warnings about the file."""
    notes, orders, slips = [], [], []
    with pdfplumber.open(str(src)) as pl:
        for i, pg in enumerate(pl.pages):
            t = pg.extract_text() or ""
            if is_slip(t):
                if not orders:
                    notes.append(f"page {i + 1}: packing slip with no label before it - ignored")
                    continue
                slips.append((len(orders) - 1, order_no(t), *body_lines(pg), repeat_of(t), has_gift_message(t), i, bool(slip_note(t))))
            else:
                orders.append({"page": i, "order": "?", "items": [], "slip": False, "repeat": None, "gift": False,
                               "priority": label_priority(pg, t), "note": False, "slip_page": None,
                               "regions": label_regions(pg) if decorations_on() else {}})
        lines_all = [l for s in slips for l in s[2]]
        colmax = max([l["x1"] for l in lines_all] + [SLIP_COLUMN_EDGE])   # floor: a batch with no wrapped title still needs a sane edge
        for oi, num, lines, marks, rep_n, gift, slip_page, has_note in slips:
            o = orders[oi]
            o["order"] = num
            o["repeat"] = rep_n
            o["gift"] = gift
            o["note"] = has_note
            o["slip_page"] = slip_page
            o["slip"] = True
            o["items"] += parse_items(lines, marks, colmax)
    for o in orders:
        if not o["slip"]:
            notes.append(f"label on page {o['page'] + 1} has no packing slip")
    return orders, notes


# --------------------------------------------------------------------------- stamping

def layout(lines, w, h, x, y, size, max_w=None, bottom=None):
    """Choose (size, columns) so the text fits the space left under the stamp position.
    max_w: width available (default: to the right edge); bottom: lowest point of the text from the top (default: 12 pt above the edge)."""
    avail_w = max_w if max_w else w - x - 10
    avail_h = max(24.0, (bottom if bottom else h - 12) - y)
    for cols in (1, 2):
        per_col = -(-len(lines) // cols)
        col_w = avail_w / cols
        s = size
        while s >= 6:
            fits_h = per_col * (s + 1.5) <= avail_h
            fits_w = max(pdfmetrics.stringWidth(safe_text(t), font_name(), s) for t in lines) <= col_w - 4
            if fits_h and fits_w:
                return s, cols, True
            s -= 0.5
    return 6, 2, False


def overlay(w, h, lines, x, y, size, max_w=None, bottom=None):
    """-> (pdf page, fitted_ok)."""
    s, cols, ok = layout(lines, w, h, x, y, size, max_w, bottom)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    per_col = -(-len(lines) // cols)
    col_w = (max_w if max_w else w - x - 10) / cols
    for n, t in enumerate(lines):
        col, row = divmod(n, per_col)
        c.setFillColorRGB(*((0.85, 0, 0) if CHECK_TEXT in t else tuple(S["colour"])))
        c.setFont(font_name(), s)
        c.drawString(x + col * col_w, h - y - row * (s + 1.5), safe_text(t))
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0], ok


def glob_to_regex(pattern):
    """A sort_groups.json pattern -> regex. `*` = any text (or none), `_` = exactly one character
    (not a space), the same symbol as in the Candle Batch Summary app. The old `?` still works."""
    parts = [".*" if ch == "*" else r"\S" if ch in "_?" else re.escape(ch) for ch in pattern]
    return re.compile("^" + "".join(parts) + "$")


def load_groups():
    """Sort groups from sort_groups.json (next to the script). First group listed = printed first.
    A SKU belongs to the FIRST group (top to bottom) with a matching pattern; `*` is any text, `_` one character.
    A group whose match list is just "*" is the 'everything else' group, wherever it sits in the list."""
    f = HERE / "sort_groups.json"
    FILE_ERRORS[:] = [e for e in FILE_ERRORS if not e.startswith("sort_groups.json")]
    GROUP_OPTS["priority_first"] = True
    if not f.exists():
        return []
    try:
        data = read_json(f)
    except Exception as e:
        print(f"{RED}sort_groups.json ignored (fix the file): {e}{OFF}")
        FILE_ERRORS.append(f"sort_groups.json is broken ({e}) - labels sorted by plain SKU order instead")
        return []
    GROUP_OPTS["priority_first"] = True
    pf = data.get("priority_first", True)
    if isinstance(pf, bool):
        GROUP_OPTS["priority_first"] = pf
    else:
        FILE_ERRORS.append('sort_groups.json: "priority_first" must be true or false (without quotes) - left on')
    groups = []
    for g in data.get("groups", []):
        raw = [str(m).strip().lower() for m in g.get("match", [])]
        pats = [glob_to_regex(m) for m in raw if m != "*"]
        groups.append({"name": g.get("name", "?"), "pats": pats, "warn": bool(g.get("warn")), "catch": "*" in raw})
    return groups


def group_of(sku, groups):
    """-> (group index, pattern index). Unmatched SKUs get index len(groups) (sorted last)."""
    k = sku.lower().strip()
    for gi, g in enumerate(groups):
        for pi, pat in enumerate(g["pats"]):
            if pat.match(k):
                return gi, pi
    for gi, g in enumerate(groups):
        if g["catch"]:
            return gi, 0
    return len(groups), 0


def group_name(gi, groups):
    return groups[gi]["name"] if gi < len(groups) else "Not in any group"


def order_group(o, groups):
    """An order sits in the LATEST group of any of its items, so an order containing an
    'at the end' item (honey, beeswax...) goes with the end items."""
    return max((group_of(s, groups)[0] for _, s, _, _ in o["items"]), default=len(groups))


def goes_first(o):
    """True for a priority-postage order (Tracked 24, 1st class...) while "priority_first" is on in sort_groups.json."""
    return bool(GROUP_OPTS["priority_first"] and o.get("priority"))


def sort_key(o, groups):
    """Orders to check first, then priority postage (if switched on), then by group (order of sort_groups.json),
    then single-item orders by pattern order and SKU, then multi-item orders."""
    items = [(group_of(s, groups)[1], natural(s)) for _, s, _, _ in o["items"]]
    bad = (not o["items"]) or any(g for _, _, _, g in o["items"])
    return (0 if bad else 1, 0 if goes_first(o) else 1, order_group(o, groups), 0 if len(items) <= 1 else 1, items, natural(o["order"]))


# --------------------------------------------------------------------------- pick list

def picklist(orders, groups):
    """-> (rows [(sku, total_qty, n_orders, group_name, n_priority_orders)] in group order, unknown [(qty, title, order)])"""
    tot, cnt, pri, unknown = {}, {}, {}, []
    for o in orders:
        if not o["items"]:
            unknown.append((0, "no items found on the slip", o["order"]))
        for q, s, title, guessed in o["items"]:
            key = (s, guessed)
            tot[key] = tot.get(key, 0) + q
            cnt[key] = cnt.get(key, 0) + 1
            if o.get("priority"):
                pri[key] = pri.get(key, 0) + 1
    def k(key):
        gi, pi = group_of(key[0], groups)
        return (gi, pi, natural(key[0]))
    rows = [((s + ("  (from title)" if S["title_fallback"] else "  (no SKU)") if g else s), tot[(s, g)], cnt[(s, g)], group_name(group_of(s, groups)[0], groups), pri.get((s, g), 0))
            for (s, g) in sorted(tot, key=k)]
    return rows, unknown


def pick_columns():
    """Pick list columns from settings: order = left to right, leave one out to hide it. SKU always shows."""
    cols = []
    for c_ in S["picklist_columns"] if isinstance(S["picklist_columns"], list) else []:
        c_ = str(c_).strip().lower()
        if c_ in ("qty", "sku", "orders") and c_ not in cols:
            cols.append(c_)
    if "sku" not in cols:
        cols.append("sku")
    return cols


def picklist_pages(rows, unknown, title, size="4x6", total_orders=None, priority_orders=0):
    """Pick list as PDF page(s) (4x6in so it prints on the label printer) -> list of pypdf pages.
    total_orders: how many orders (labels) are in the batch; shown bold at the end, under the Orders column.
    priority_orders: how many of them are priority postage; a red P<n> beside a SKU says n of its orders are."""
    a4 = str(size).lower() == "a4"
    W, H = (595.0, 842.0) if a4 else (288.0, 432.0)
    m = 40 if a4 else 18                       # side margin
    big, mid, small = (12, 10, 9) if a4 else (9, 7.5, 7)
    pitch = 18 if a4 else 12.5
    ox = W - m                                   # right edge of the table
    cols = pick_columns()
    widths = {"qty": 55 if a4 else 30, "orders": 60 if a4 else 38}
    widths["sku"] = (ox - m) - sum(widths[c_] for c_ in cols if c_ != "sku")
    left, x0 = {}, m
    for c_ in cols:                              # columns run left to right in the order of picklist_columns
        left[c_] = x0
        x0 += widths[c_]
    sku_x = left["sku"] + 4
    max_chars = int((widths["sku"] - 8) / (big * 0.5))
    bottom = 40 if a4 else 26
    fn = font_name()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    y = 0

    def head(page):
        nonlocal y
        c.setFillColorRGB(0, 0, 0)
        c.setFont(fn, 14 if a4 else 10)
        c.drawString(m, H - (40 if a4 else 24), safe_text(title)[:60 if a4 else 38])
        c.setFont(fn, small)
        c.drawString(m, H - (54 if a4 else 35), datetime.now().strftime("%d %b %Y %H:%M") + f"   page {page}")
        y = H - (80 if a4 else 54)
        c.setFont(fn, mid)
        for c_ in cols:
            if c_ == "sku":
                c.drawString(sku_x, y, "SKU")
            else:
                c.drawRightString(left[c_] + widths[c_] - 4, y, "Qty" if c_ == "qty" else "Orders")
        c.line(m, y - 4, ox, y - 4)
        y -= 4 + pitch

    page = 1
    head(page)

    cur = [None]    # group whose rows are being drawn (so a page break can say "(continued)")

    def room(n=1):
        nonlocal y, page
        if y - n * pitch < bottom:
            c.showPage()
            page += 1
            head(page)
            if cur[0] is not None:
                c.setFillColorRGB(0, 0, 0)
                c.setFont(font_bold(), mid + 1.5)
                c.drawString(sku_x, y, safe_text(cur[0] + " (continued)")[:int((ox - sku_x) / ((mid + 1.5) * 0.55))])
                c.setLineWidth(0.7)
                c.line(m, y - 3, ox, y - 3)
                c.setLineWidth(1)
                y -= pitch

    last_group = None
    flag_on = bool(S["picklist_priority_flag"])
    for row in rows:
        sku, q, n, gname = row[:4]
        pr = row[4] if len(row) > 4 else 0
        if gname != last_group:
            cur[0] = None
            if last_group is not None:
                if S["picklist_page_per_group"]:
                    c.showPage()
                    page += 1
                    head(page)
                else:
                    y -= pitch * 0.6
            if S["picklist_group_titles"]:
                room(2)
                c.setFillColorRGB(0, 0, 0)
                c.setFont(font_bold(), mid + 1.5)
                c.drawString(sku_x, y, safe_text(gname)[:int((ox - sku_x) / ((mid + 1.5) * 0.55))])   # in the SKU column, so the Qty column reads straight down
                c.setLineWidth(0.7)
                c.line(m, y - 3, ox, y - 3)
                c.setLineWidth(1)
                y -= pitch
                cur[0] = gname
            last_group = gname
        room()
        c.setFillColorRGB(0, 0, 0)
        c.setFont(fn, big)
        flagged = flag_on and bool(pr)
        c.drawString(sku_x, y, safe_text(sku)[:max_chars - (4 if flagged else 0)])
        if flagged:                                  # red P<n>: n of this SKU's orders are priority postage
            c.setFillColorRGB(0.85, 0, 0)
            c.setFont(font_bold(), mid)
            c.drawRightString(left["sku"] + widths["sku"] - 4, y, f"P{pr}")
            c.setFillColorRGB(0, 0, 0)
            c.setFont(fn, big)
        if "qty" in cols:
            c.drawRightString(left["qty"] + widths["qty"] - 4, y, str(q))
        if "orders" in cols:
            c.setFont(fn, mid)
            c.drawRightString(left["orders"] + widths["orders"] - 4, y, str(n))
        y -= pitch
    y -= pitch * 0.4
    room(2)
    c.line(m, y + pitch - 4, ox, y + pitch - 4)
    # Total ORDERS (the number that matters), bold and a little larger: the number sits under the Orders
    # column, the words just to its left with a small gap. (Not an items total.)
    total = total_orders if total_orders is not None else sum(r[2] for r in rows)   # fallback only if the caller did not say
    bold, tot = font_bold(), big + 2
    num_right = (left["orders"] + widths["orders"] - 4) if "orders" in cols else ox
    gap = 14 if a4 else 10
    label_x = num_right - pdfmetrics.stringWidth(str(total), bold, tot) - gap - pdfmetrics.stringWidth("Total orders", bold, tot)
    y -= 3                                           # a little air under the rule: this row's text is larger than the rows above
    c.setFillColorRGB(0, 0, 0)
    c.setFont(bold, tot)
    c.drawString(label_x, y, "Total orders")
    c.drawRightString(num_right, y, str(total))
    if priority_orders and flag_on:
        room(3)
        y -= pitch * 1.2
        c.setFillColorRGB(0.85, 0, 0)
        c.setFont(bold, tot)
        c.drawString(num_right - pdfmetrics.stringWidth(str(priority_orders), bold, tot) - gap
                     - pdfmetrics.stringWidth("PRIORITY orders", bold, tot), y, "PRIORITY orders")
        c.drawRightString(num_right, y, str(priority_orders))
        y -= pitch * 0.9
        c.setFont(fn, small)
        c.drawRightString(ox, y, "P2 beside a SKU = 2 of its orders are priority postage")
        c.setFillColorRGB(0, 0, 0)
    y -= pitch * 1.5
    if unknown:
        room(2)
        c.setFillColorRGB(0.85, 0, 0)
        c.setFont(fn, mid)
        c.drawString(m, y, "NO SKU - check the packing slip:")
        y -= pitch
        c.setFont(fn, small)
        for q, t, o in unknown:
            room()
            c.setFillColorRGB(0.85, 0, 0)
            c.setFont(fn, small)
            c.drawString(m, y, safe_text(f"Order {o}: {q} x {t}")[:int((ox - m) / (small * 0.5))])
            y -= pitch
    c.save()
    buf.seek(0)
    return list(PdfReader(buf).pages)


# --------------------------------------------------------------------------- safety checks and helpers

def layout_alarms(orders):
    """Warnings that Shopify may have changed the packing-slip layout (so SKUs could be wrong in bulk)."""
    alarms = []
    n = len(orders)
    flagged = sum(1 for o in orders if (not o["items"]) or any(g for _, _, _, g in o["items"]))
    pct = S["layout_alarm_percent"]
    if pct and n >= 4 and flagged * 100 >= pct * n:
        alarms.append(f"{flagged} of {n} orders have no SKU - the packing slip layout may have changed")
    long_ = [sku for o in orders for _, sku, _, g in o["items"] if not g and len(sku) > 40]
    if long_:
        alarms.append(f"{len(long_)} SKU(s) are unusually long (e.g. '{long_[0][:40]}...') - the slip layout may have changed")
    return alarms


def suggest_patterns(skus):
    """-> {pattern: [skus]}: a sort_groups.json pattern for each kind of SKU ('4 VL' -> '* VL', '40mm' -> '*mm')."""
    pats = {}
    for sku in skus:
        m = re.match(r"^\d+(?:\.\d+)?\s+(.+)$", sku)
        m2 = re.match(r"^\d+(?:\.\d+)?(\D.*)$", sku)
        pat = "* " + m.group(1) if m else ("*" + m2.group(1) if m2 else sku)
        pats.setdefault(pat, []).append(sku)
    return pats


def suggestion_text(skus):
    lines = []
    for pat, found in sorted(suggest_patterns(skus).items(), key=lambda kv: natural(kv[0])):
        name = pat.replace("*", "").strip() or pat
        lines.append(f"    // matches: {', '.join(found)}")
        lines.append(f'    {{"name": "{name}", "match": ["{pat}"]}},')
    return chr(10).join(lines)


# --------------------------------------------------------------------------- main work

def unique_path(p):
    if not p.exists():
        return p
    return p.with_name(f"{p.stem}_{datetime.now():%H%M%S}{p.suffix}")


def preview_png(pdf_path, page_idx, out_png):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print(f"{YELLOW}--preview needs pypdfium2 (pip install pypdfium2){OFF}")
        return None
    doc = pdfium.PdfDocument(str(pdf_path))
    doc[page_idx].render(scale=2.5).to_pil().save(out_png)
    doc.close()
    return out_png


def process(src, a, cfg):
    """Returns the output PDF path, or None."""
    print(f"\n{BOLD}{src.name}{OFF}")
    if re.search(r"_sku(_\d+)?$", src.stem):
        print(f"  {YELLOW}skipped: looks like an already-stamped file (name ends in _sku){OFF}")
        return None
    orders, notes = parse_pdf(src)
    if not any(o["slip"] for o in orders):
        print(f"  {RED}no packing slips found - is this a Shopify labels+slips PDF? (already processed?){OFF}")
        return None

    groups = load_groups()
    if a.sort:
        orders.sort(key=lambda o: sort_key(o, groups))
    reader = PdfReader(str(src))
    writer = PdfWriter()
    problems, titled, overflow, busiest = [], [], [], (0, 0)
    kept_slips = not_decorated = 0
    last_group = None
    for n, o in enumerate(orders):
        text = [fmt(q, s) for q, s, _, _ in o["items"]]
        bad = not text
        guessed = any(g for _, _, _, g in o["items"])
        if bad:
            problems.append(o["order"])
        elif guessed:
            titled.append(o["order"])
        mark = f"{RED}!!{OFF}" if bad else (f"{YELLOW}~~{OFF}" if guessed else f"{GREEN}ok{OFF}")
        if a.sort and not bad:
            gn = ("PRIORITY POSTAGE (Tracked 24 / 1st class), then by group" if goes_first(o)
                  else (group_name(order_group(o, groups), groups) if groups else None))
            if gn and gn != last_group:
                print(f"  {DIM}--- {gn} ---{OFF}")
                last_group = gn
        star = repeat_mark(o["repeat"])
        if star and text:
            text[0] += " " + star                          # same habit as writing * by hand
        gift = bool(o.get("gift")) and bool(S["gift_mark"])
        note = bool(o.get("note")) and bool(S["note_mark"])
        keep_slip = bool(o.get("note")) and bool(S["keep_note_slips"]) and o.get("slip_page") is not None
        print(f"  {mark} Order {o['order']:>11}: {' | '.join(text) or '-'}" + (f"  {YELLOW}{BOLD}[{S['gift_text']}]{OFF}" if gift else "")
              + (f"  {YELLOW}{BOLD}[{S['note_text']}]{OFF}" if note else "")
              + (f"  {RED}{BOLD}[PRIORITY: {o['priority']}]{OFF}" if o.get("priority") else ""))
        label = writer.add_page(reader.pages[o["page"]])   # attach first, then edit (newer pypdf requires this)
        page_no = len(writer.pages) - 1                     # where this label sits in the output (slips kept before it shift the count)
        if a.strip and "/Annots" in label:
            del label["/Annots"]                            # remove text typed by hand
        if not text:
            text = [CHECK_TEXT]
        if note:
            text = text + [S["note_text"]]                  # own line after the SKUs: the order has a note to read
        if gift:
            text = text + [S["gift_text"]]                  # own line, last: the gift card comes from Etsy
        w, h = float(label.mediabox.width), float(label.mediabox.height)
        if decorations_on():
            deco = decoration_overlay(w, h, o.get("regions") or {})
            if deco is not None:
                label.merge_page(deco)                      # white boxes / replacement text / logo first, the SKU stamp on top
            else:
                not_decorated += 1
        sx, sy, smax, sbottom = stamp_position(o.get("regions") or {}, a.x, a.y, a.size)
        ov, ok = overlay(w, h, text, sx, sy, a.size, smax, sbottom)
        label.merge_page(ov)
        if keep_slip:
            writer.add_page(reader.pages[o["slip_page"]])    # the packing slip with the note stays right behind its label
            kept_slips += 1
        if not ok:
            overflow.append(o["order"])
        if len(text) > busiest[0]:
            busiest = (len(text), page_no)

    rows, unknown = picklist(orders, groups)
    stray = sorted({s for o in orders for _, s, _, g in o['items']
                    if not g and (group_of(s, groups)[0] >= len(groups) or groups[group_of(s, groups)[0]]['warn'])},
                   key=natural) if groups else []

    # ---- summary
    alarms = layout_alarms(orders)
    total = len(orders)
    repeats = sum(1 for o in orders if repeat_mark(o["repeat"]))
    print(f"\n  {BOLD}Summary{OFF}: {total} labels, {sum(r[1] for r in rows)} items, {len(rows)} different SKUs")
    if repeats:
        print(f"  {repeats} repeat customer{'s' if repeats != 1 else ''} (marked with * on the label)")
    n_priority = sum(1 for o in orders if o.get("priority"))
    if n_priority:
        kinds = ", ".join(sorted({o["priority"] for o in orders if o.get("priority")}))
        where = ("printed first" if GROUP_OPTS["priority_first"] and a.sort
                 else 'not moved: "priority_first" is off in sort_groups.json (or sorting is off)')
        print(f"  {RED}{BOLD}{n_priority} priority postage order{'s' if n_priority != 1 else ''} ({kinds}){OFF}: {where}")
    if not_decorated:
        print(f"  {YELLOW}{not_decorated} label{'s' if not_decorated != 1 else ''} had none of the wording the cover / logo options look for "
              f"(MARKETPLACE SELLER, Shopify): left as printed. Check them if that is not expected.{OFF}")
    noted = [o["order"] for o in orders if o.get("note")] if (S["note_mark"] or S["keep_note_slips"]) else []
    if noted:
        what = ((f"labels say {S['note_text']}" if S["note_mark"] else "") + (", " if S["note_mark"] and S["keep_note_slips"] else "")
                + ("the packing slip is kept behind the label" if S["keep_note_slips"] else ""))
        print(f"  {YELLOW}{BOLD}{len(noted)} order{'s' if len(noted) != 1 else ''} with a note{OFF}{YELLOW} ({what}): {', '.join(noted)}{OFF}")
    gifts = [o["order"] for o in orders if o.get("gift")] if S["gift_mark"] else []
    if gifts:
        print(f"  {YELLOW}{BOLD}{len(gifts)} order{'s' if len(gifts) != 1 else ''} with a gift message{OFF}{YELLOW}: print "
              f"{'them' if len(gifts) != 1 else 'it'} from Etsy (labels say {S['gift_text']}): {', '.join(gifts)}{OFF}")
    colour = GREEN if not (problems or notes or overflow or titled or FILE_ERRORS or alarms) else RED
    n_issues = len(problems) + len(notes) + len(overflow) + len(titled) + len(FILE_ERRORS) + len(alarms)
    print(f"  {colour}{BOLD}{total} labels, {n_issues} problem{'s' if n_issues != 1 else ''}{OFF}")
    for o in problems:
        print(f"  {RED}- order {o}: no items found on the slip - label says '{CHECK_TEXT}'{OFF}")
    for o in titled:
        print(f"  {YELLOW}- order {o}: no SKU on slip - stamped {'part of the title' if S['title_fallback'] else CHECK_TEXT} instead (~~){OFF}")
    for o in overflow:
        print(f"  {YELLOW}- order {o}: too many SKUs to fit neatly - check the label{OFF}")
    for n in notes:
        print(f"  {YELLOW}- {n}{OFF}")
    for al in alarms:
        print(f"  {RED}{BOLD}!! WARNING: {al}. Check the labels carefully before printing.{OFF}")
    for e in FILE_ERRORS:
        print(f"  {RED}- {e}. The mistake is usually on, or just above, the line number given (often a missing comma). To reset, copy the file from the defaults folder.{OFF}")
    if stray:
        print(f"  {YELLOW}- SKUs not in a named sort group (add them to sort_groups.json): {', '.join(stray)}. Run with --suggest for ready-to-paste lines.{OFF}")
    if a.suggest:
        if stray:
            text = suggestion_text(stray)
            print()
            print(f"  {BOLD}Suggested lines for sort_groups.json{OFF} (paste them ABOVE the 'Other' line, then put them in the order you want):")
            print()
            print(text)
            print()
            print(f"  {DIM}Check each pattern: '*mm' would also match any other SKU ending in mm. Make a pattern more exact if needed.{OFF}")
            try:
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(["clip"], input=text.encode("ascii", "replace"), check=True)
                    print(f"  {GREEN}(copied to the clipboard){OFF}")
            except Exception:
                pass
        else:
            print(f"  {GREEN}Every SKU is already in a named sort group - nothing to suggest.{OFF}")
    if a.check or a.suggest:
        return None

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else unique_path(out_dir / f"{src.stem}_sku.pdf")
    if a.picklist:
        for pg in picklist_pages(rows, unknown, "Pick list", cfg["picklist_size"], total, n_priority):
            writer.add_page(pg)                  # pick list = last page(s) of the same PDF
    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out}  ({total} labels" + (f" + {kept_slips} packing slip{'s' if kept_slips != 1 else ''} with a note" if kept_slips else "")
          + (" + pick list as the last page)" if a.picklist else ")"))
    if a.preview:
        png = preview_png(out, busiest[1], out.with_suffix(".png"))
        if png:
            print(f"  -> {png}  (busiest label - tweak --x/--y/--size and re-run)")
            open_file(png)
    return out


def open_file(p):
    try:
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            os.system(f'open "{p}"')
        else:
            os.system(f'xdg-open "{p}" >/dev/null 2>&1 &')
    except Exception:
        pass


def matching(folder, pattern):
    return [p for p in folder.glob(pattern)
            if p.is_file() and not re.search(r"_sku(_\d+)?$", p.stem) and "_picklist" not in p.stem]


def archive(src, done_dir):
    """Move the original to the done folder. Browsers/antivirus often keep a download locked for a few
    seconds after it finishes, so retry; never crash if it still can't be moved."""
    done_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(done_dir / src.name)
    for attempt in range(15):
        try:
            shutil.move(str(src), str(dest))
            print(f"  original moved to {dest}")
            return True
        except PermissionError:
            time.sleep(2)
        except OSError as e:
            print(f"  {YELLOW}couldn't move original: {e}{OFF}")
            return False
    print(f"  {YELLOW}original is still locked by another program - left in place: {src}{OFF}")
    return False


def stable(p, last_seen):
    """True once a file's size has stopped changing between two polls (download finished)."""
    try:
        sig = (p.stat().st_size, p.stat().st_mtime)
    except OSError:
        return False
    ok = last_seen.get(p) == sig and sig[0] > 0
    last_seen[p] = sig
    return ok


def watch(a, cfg, folder, done_dir):
    print(f"{BOLD}Watching {folder}{OFF} for new {cfg['pattern']}  (Ctrl+C or close this window to stop)")
    ignore = set(matching(folder, cfg["pattern"]))          # files already there are left alone
    if ignore:
        print(f"{DIM}ignoring {len(ignore)} existing file(s); only new downloads are processed{OFF}")
    last_seen = {}
    try:
        while True:
            for p in matching(folder, cfg["pattern"]):
                if p in ignore or not stable(p, last_seen):
                    continue
                ignore.add(p)
                try:
                    out = process(p, a, cfg)
                except Exception as e:
                    print(f"  {RED}failed: {e}{OFF}")
                    continue
                if out:
                    if not a.no_open:
                        open_file(out)
                    if cfg["move_originals"]:
                        archive(p, done_dir)   # stays in `ignore` either way, so it is never processed twice
                    print(f"\n{BOLD}Watching again...{OFF}")
            time.sleep(max(1, float(cfg["watch_seconds"])))
    except KeyboardInterrupt:
        print("\nstopped")


def main():
    cfg = load_settings()
    ap = argparse.ArgumentParser(description="Stamp packing-slip SKUs onto Shopify shipping labels.")
    ap.add_argument("pdf", nargs="*", help="PDF(s); with none, the newest shipping*.pdf in Downloads is used")
    ap.add_argument("-o", "--out", help="output file name (single input only)")
    ap.add_argument("--x", type=float, default=cfg["x"], help="points from left")
    ap.add_argument("--y", type=float, default=cfg["y"], help="points from top (first line baseline)")
    ap.add_argument("--size", type=float, default=cfg["size"])
    ap.add_argument("--strip", action="store_true", help="remove text/annotations already typed on the labels")
    ap.add_argument("--check", action="store_true", help="list SKUs found, write nothing")
    ap.add_argument("--no-sort", dest="sort", action="store_false", help="keep Shopify's label order")
    ap.add_argument("--preview", action="store_true", help="save + open a PNG of the busiest label")
    ap.add_argument("--watch", action="store_true", help="keep running and process new downloads")
    ap.add_argument("--move", action="store_true", help="move processed originals to done\\ (automatic for Downloads/watch)")
    ap.add_argument("--no-open", action="store_true", help="don't open the result")
    ap.add_argument("--suggest", action="store_true", help="print ready-to-paste sort_groups.json lines for SKUs not in a group (writes no PDF)")
    ap.add_argument("--validate", action="store_true", help="check settings.json and sort_groups.json for mistakes, then stop")
    ap.add_argument("--no-picklist", action="store_true", help="leave the pick list page out")
    ap.add_argument("--downloads", help="folder to look in (default: your Downloads)")
    a = ap.parse_args()
    if a.validate:
        groups = load_groups()
        if FILE_ERRORS:
            sys.exit(f"{RED}Problem found:{OFF} " + "; ".join(FILE_ERRORS))
        print(f"{GREEN}settings.json and sort_groups.json are fine{OFF} ({len(groups)} sort groups).")
        return
    a.strip = a.strip or bool(cfg["strip_typed_text"])        # command-line flags add to settings.json
    a.sort = a.sort and bool(cfg["sort_labels"])
    a.no_open = a.no_open or not cfg["open_after"]
    a.picklist = cfg["picklist"] and not a.no_picklist
    a.out_dir = resolve_dir(cfg["out_dir"])
    folder = Path(a.downloads or cfg["downloads"] or downloads_folder())
    done_dir = resolve_dir(cfg["done_dir"])

    if a.watch:
        return watch(a, cfg, folder, done_dir)

    auto = not a.pdf
    if auto:
        found = sorted(matching(folder, cfg["pattern"]), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            sys.exit(f"No {cfg['pattern']} found in {folder}.\nDownload the labels from Shopify first, "
                     f"or drag a PDF onto run.bat.")
        files = [found[0]]
        print(f"Using newest file in {folder}")
    else:
        files = [Path(f) for f in a.pdf]
    if a.out and len(files) > 1:
        sys.exit("-o/--out only works with a single input file")

    last = None
    for f in files:
        if not f.exists():
            print(f"{RED}{f}: not found{OFF}")
            continue
        try:
            out = process(f, a, cfg)
        except Exception as e:
            print(f"  {RED}failed: {e}{OFF}")
            continue
        if out:
            last = out
            if ((auto and cfg["move_originals"]) or a.move) and not a.check:
                archive(f, done_dir)
    if last and not a.no_open:
        open_file(last)


if __name__ == "__main__":
    main()
