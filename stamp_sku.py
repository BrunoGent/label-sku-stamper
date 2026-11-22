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

Defaults can be changed in settings.json (see settings.example.json).
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
BLUE = (0, 0, 0.85)
CHECK_TEXT = "?? CHECK SLIP"

DEFAULTS = {"x": 40.0, "y": 378.0, "size": 11.0, "out_dir": "Labels", "done_dir": "done",
            "downloads": None, "pattern": "shipping*.pdf", "picklist_size": "4x6"}


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


def load_settings():
    s = dict(DEFAULTS)
    f = HERE / "settings.json"
    if f.exists():
        try:
            s.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in DEFAULTS})
        except Exception as e:
            print(f"{YELLOW}settings.json ignored: {e}{OFF}")
    return s


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


def safe_text(t):
    """Drop characters the font can't draw (only matters for the Helvetica fallback)."""
    if font_name() == "Helvetica":
        return t.encode("latin-1", "replace").decode("latin-1")
    return t


# --------------------------------------------------------------------------- parsing

QTY_RE = re.compile(r"^(\d+)$")


def is_slip(text):
    return ("SHIP TO" in text and "ITEMS" in text) or bool(re.search(r"Order\s+#?\d+", text))


def order_no(text):
    m = re.search(r"Order\s+#?(\d+)", text)
    return m.group(1) if m else "?"


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
        out.append((qty, sku or title_guess(title), title, sku is None))   # last item: True = SKU was guessed from the title
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
                slips.append((len(orders) - 1, order_no(t), *body_lines(pg)))
            else:
                orders.append({"page": i, "order": "?", "items": [], "slip": False})
        lines_all = [l for s in slips for l in s[2]]
        colmax = max((l["x1"] for l in lines_all), default=0)
        for oi, num, lines, marks in slips:
            o = orders[oi]
            o["order"] = num
            o["slip"] = True
            o["items"] += parse_items(lines, marks, colmax)
    for o in orders:
        if not o["slip"]:
            notes.append(f"label on page {o['page'] + 1} has no packing slip")
    return orders, notes


# --------------------------------------------------------------------------- stamping

def layout(lines, w, h, x, y, size):
    """Choose (size, columns) so the text fits the space left under the stamp position."""
    avail_w = w - x - 10
    avail_h = max(24.0, h - y - 12)
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


def overlay(w, h, lines, x, y, size):
    """-> (pdf page, fitted_ok)."""
    s, cols, ok = layout(lines, w, h, x, y, size)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    per_col = -(-len(lines) // cols)
    col_w = (w - x - 10) / cols
    for n, t in enumerate(lines):
        col, row = divmod(n, per_col)
        c.setFillColorRGB(*((0.85, 0, 0) if CHECK_TEXT in t else BLUE))
        c.setFont(font_name(), s)
        c.drawString(x + col * col_w, h - y - row * (s + 1.5), safe_text(t))
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0], ok


def load_groups():
    """Sort groups from sort_groups.json (next to the script). First group listed = printed first.
    A SKU belongs to the FIRST group (top to bottom) with a matching pattern; `*` is a wildcard.
    A group whose match list is just "*" is the 'everything else' group, wherever it sits in the list."""
    f = HERE / "sort_groups.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{YELLOW}sort_groups.json ignored (fix the file): {e}{OFF}")
        return []
    groups = []
    for g in data.get("groups", []):
        raw = [str(m).strip().lower() for m in g.get("match", [])]
        pats = [re.compile("^" + ".*".join(re.escape(x) for x in m.split("*")) + "$") for m in raw if m != "*"]
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


def sort_key(o, groups):
    """Orders to check first, then by group (order of sort_groups.json), then single-item orders
    by pattern order and SKU, then multi-item orders."""
    items = [(group_of(s, groups)[1], natural(s)) for _, s, _, _ in o["items"]]
    bad = (not o["items"]) or any(g for _, _, _, g in o["items"])
    return (0 if bad else 1, order_group(o, groups), 0 if len(items) <= 1 else 1, items, natural(o["order"]))


# --------------------------------------------------------------------------- pick list

def picklist(orders, groups):
    """-> (rows [(sku, total_qty, n_orders, group_name)] in group order, unknown [(qty, title, order)])"""
    tot, cnt, unknown = {}, {}, []
    for o in orders:
        if not o["items"]:
            unknown.append((0, "no items found on the slip", o["order"]))
        for q, s, title, guessed in o["items"]:
            key = (s, guessed)
            tot[key] = tot.get(key, 0) + q
            cnt[key] = cnt.get(key, 0) + 1
    def k(key):
        gi, pi = group_of(key[0], groups)
        return (gi, pi, natural(key[0]))
    rows = [((s + "  (from title)" if g else s), tot[(s, g)], cnt[(s, g)], group_name(group_of(s, groups)[0], groups))
            for (s, g) in sorted(tot, key=k)]
    return rows, unknown


def picklist_pages(rows, unknown, title, size="4x6"):
    """Pick list as PDF page(s) (4x6in so it prints on the label printer) -> list of pypdf pages."""
    a4 = str(size).lower() == "a4"
    W, H = (595.0, 842.0) if a4 else (288.0, 432.0)
    m = 40 if a4 else 18                       # side margin
    big, mid, small = (12, 10, 9) if a4 else (9, 7.5, 7)
    pitch = 18 if a4 else 12.5
    qx, ox = W - m - (80 if a4 else 46), W - m  # right edges of the Qty and Orders columns
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
        c.drawString(m, y, "SKU")
        c.drawRightString(qx, y, "Qty")
        c.drawRightString(ox, y, "Orders")
        c.line(m, y - 4, ox, y - 4)
        y -= 4 + pitch

    page = 1
    head(page)

    def room(n=1):
        nonlocal y, page
        if y - n * pitch < bottom:
            c.showPage()
            page += 1
            head(page)

    max_chars = int((qx - m - 20) / (big * 0.5))
    last_group = None
    for sku, q, n, gname in rows:
        if gname != last_group:
            if last_group is not None:
                y -= pitch * 0.3
            room(2)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.setFont(fn, small)
            c.drawString(m, y, safe_text(gname).upper()[:int((ox - m) / (small * 0.55))])
            y -= pitch * 0.85
            last_group = gname
        room()
        c.setFillColorRGB(0, 0, 0)
        c.setFont(fn, big)
        c.drawString(m + 4, y, safe_text(sku)[:max_chars])
        c.drawRightString(qx, y, str(q))
        c.setFont(fn, mid)
        c.drawRightString(ox, y, str(n))
        y -= pitch
    y -= pitch * 0.4
    room(2)
    c.line(m, y + pitch - 4, ox, y + pitch - 4)
    c.setFont(fn, big)
    c.drawString(m, y, "Total items")
    c.drawRightString(qx, y, str(sum(r[1] for r in rows)))
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
        if groups and a.sort and not bad:
            gn = group_name(order_group(o, groups), groups)
            if gn != last_group:
                print(f"  {DIM}--- {gn} ---{OFF}")
                last_group = gn
        print(f"  {mark} Order {o['order']:>11}: {' | '.join(text) or '-'}")
        label = writer.add_page(reader.pages[o["page"]])   # attach first, then edit (newer pypdf requires this)
        if a.strip and "/Annots" in label:
            del label["/Annots"]                            # remove text typed by hand
        if not text:
            text = [CHECK_TEXT]
        w, h = float(label.mediabox.width), float(label.mediabox.height)
        ov, ok = overlay(w, h, text, a.x, a.y, a.size)
        label.merge_page(ov)
        if not ok:
            overflow.append(o["order"])
        if len(text) > busiest[0]:
            busiest = (len(text), n)

    rows, unknown = picklist(orders, groups)
    stray = sorted({s for o in orders for _, s, _, g in o['items']
                    if not g and (group_of(s, groups)[0] >= len(groups) or groups[group_of(s, groups)[0]]['warn'])},
                   key=natural) if groups else []

    # ---- summary
    total = len(orders)
    print(f"\n  {BOLD}Summary{OFF}: {total} labels, {sum(r[1] for r in rows)} items, {len(rows)} different SKUs")
    colour = GREEN if not (problems or notes or overflow or titled) else RED
    n_issues = len(problems) + len(notes) + len(overflow) + len(titled)
    print(f"  {colour}{BOLD}{total} labels, {n_issues} problem{'s' if n_issues != 1 else ''}{OFF}")
    for o in problems:
        print(f"  {RED}- order {o}: no items found on the slip - label says '{CHECK_TEXT}'{OFF}")
    for o in titled:
        print(f"  {YELLOW}- order {o}: no SKU on slip - stamped part of the title instead (~~){OFF}")
    for o in overflow:
        print(f"  {YELLOW}- order {o}: too many SKUs to fit neatly - check the label{OFF}")
    for n in notes:
        print(f"  {YELLOW}- {n}{OFF}")
    if stray:
        print(f"  {YELLOW}- SKUs not in a named sort group (add them to sort_groups.json): {', '.join(stray)}{OFF}")
    if a.check:
        return None

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else unique_path(out_dir / f"{src.stem}_sku.pdf")
    for pg in picklist_pages(rows, unknown, "Pick list", cfg["picklist_size"]):
        writer.add_page(pg)                      # pick list = last page(s) of the same PDF
    with open(out, "wb") as f:
        writer.write(f)
    print(f"  -> {out}  ({total} labels + pick list as the last page)")
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
                    archive(p, done_dir)   # stays in `ignore` either way, so it is never processed twice
                    print(f"\n{BOLD}Watching again...{OFF}")
            time.sleep(2)
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
    ap.add_argument("--downloads", help="folder to look in (default: your Downloads)")
    a = ap.parse_args()
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
            if (auto or a.move) and not a.check:
                archive(f, done_dir)
    if last and not a.no_open:
        open_file(last)


if __name__ == "__main__":
    main()
