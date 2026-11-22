"""Regression tests. Run from the label-sku-stamper folder:   py -m unittest discover -s tests -v

They build small synthetic Shopify-style PDFs (label page + packing-slip page) - no customer data -
and check the SKU reading, grouping, suggestions and the layout alarm. Run them after any change to
stamp_sku.py, and add a case whenever a real slip is read wrongly.
"""
import io, sys, tempfile, unittest, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.getLogger("pdfminer").setLevel(logging.ERROR)
import stamp_sku as s
from reportlab.pdfgen import canvas

LONG = "Handcrafted Coloured Beeswax Taper Candles | Locally Sourced &"   # a full-width (wrapped) title line


def make_pdf(path, orders):
    """orders: list of (order_no, [item]), (order_no, [item], note_lines) or (order_no, [item], note_lines, repeat_text);
    item = (qty, [text lines]). Layout mimics the Shopify 4x6 slip; note_lines are printed under the NOTES heading;
    repeat_text, e.g. REPEAT CUSTOMER (Order #4), is printed under the order number like the real slip."""
    c = canvas.Canvas(str(path), pagesize=(288, 432))
    for entry in orders:
        number, items = entry[0], entry[1]
        note_lines = entry[2] if len(entry) > 2 else []
        repeat_text = entry[3] if len(entry) > 3 else None
        c.setFont("Helvetica", 10)
        c.drawString(20, 400, "Royal Mail tracked label")           # the label page
        c.showPage()
        c.setFont("Helvetica", 5.2)
        c.drawString(20, 400, f"Order #{number}")
        if repeat_text:
            c.drawString(20, 392, repeat_text)
        c.setFont("Helvetica-Bold", 4.4)
        c.drawString(23, 380, "SHIP TO")
        c.drawString(23, 312, "ITEMS")
        top = 432 - 135                                             # first item line (pdf y grows upwards)
        for qty, lines in items:
            for i, text in enumerate(lines):
                c.setFont("Helvetica", 6.2)
                c.drawString(61.7, top - i * 9.3, text)
            if qty > 1:
                c.setFont("Helvetica-Bold", 8.3)
                c.drawString(27, top - 9.3, f"{qty} x")
            top -= (len(lines) - 1) * 9.3 + 16.5
        c.setFont("Helvetica-Bold", 4.4)
        c.drawString(23.4, 150, "NOTES")
        c.setFont("Helvetica", 6.2)
        for i, text in enumerate(note_lines):
            c.drawString(23.4, 140 - i * 9.3, text)
        c.showPage()
    c.save()


def parse(orders):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "shipping_test.pdf"
        make_pdf(f, orders)
        return s.parse_pdf(f)


class Reading(unittest.TestCase):
    def setUp(self):
        s.load_settings()

    def items(self, orders):
        o, notes = parse(orders)
        return [x["items"] for x in o], notes

    def test_plain_sku_and_quantity(self):
        got, notes = self.items([
            ("1001", [(1, ["Hand Dipped Candles | Dripless", "Standard (2 cm) / 4", "4 dip 2cm"])]),
            ("1002", [(3, ["Local honey 1kg", "unpasteurized", "kg h"])]),
        ])
        self.assertEqual([(q, sku, g) for q, sku, _, g in got[0]], [(1, "4 dip 2cm", False)])
        self.assertEqual([(q, sku, g) for q, sku, _, g in got[1]], [(3, "kg h", False)])
        self.assertEqual(notes, [])

    def test_two_items_on_one_slip(self):
        got, _ = self.items([("1003", [(1, ["Tealights pack", "12 TL"]), (2, ["Pillar candle", "60mm"])])])
        self.assertEqual([(q, sku) for q, sku, _, _ in got[0]], [(1, "12 TL"), (2, "60mm")])

    def test_wrapped_title_means_no_sku(self):
        got, _ = self.items([
            ("1004", [(1, [LONG, "Eco-Friendly[Green,2]"])]),
            ("1005", [(1, ["4 dipped candles 2cm"])]),                # one-line title only
        ])
        self.assertTrue(got[0][0][3])                                # flagged: no SKU on slip
        self.assertEqual(got[0][0][1], "[Green,2]")                  # bracketed option used
        self.assertTrue(got[1][0][3])
        self.assertEqual(got[1][0][1], "4 dipped candles 2cm")

    def test_label_without_slip_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.pdf"
            c = canvas.Canvas(str(f), pagesize=(288, 432))
            c.drawString(20, 400, "label only")
            c.showPage()
            c.save()
            orders, notes = s.parse_pdf(f)
        self.assertTrue(any("no packing slip" in n for n in notes))


class Grouping(unittest.TestCase):
    def setUp(self):
        s.HERE = Path(__file__).resolve().parent.parent / "defaults"     # the known-good starter groups
        self.groups = s.load_groups()

    def name(self, sku):
        return s.group_name(s.group_of(sku, self.groups)[0], self.groups)

    def test_first_match_wins_and_specific_before_general(self):
        self.assertEqual(self.name("4 dip 2cm"), "Dipped 2cm")
        self.assertEqual(self.name("2 dip pink"), "Coloured dipped")
        self.assertEqual(self.name("12 TL"), "Tealights")

    def test_unlisted_goes_to_catch_all_and_end_group_is_last(self):
        self.assertEqual(self.name("something new"), "Other (not yet in a group)")
        self.assertEqual(self.name("kg h"), "Beeswax and honey (at the end)")
        order = [self.name(x) for x in ("kg h", "12 TL", "mystery", "4 dip 2cm")]
        ranked = sorted(order, key=lambda n: [g["name"] for g in self.groups].index(n))
        self.assertEqual(ranked[0], "Dipped 2cm")
        self.assertEqual(ranked[-1], "Beeswax and honey (at the end)")

    def test_numbers_sort_as_numbers(self):
        self.assertLess(s.natural("2 dip 2cm"), s.natural("12 dip 2cm"))

    def test_underscore_is_exactly_one_character(self):
        # "_" as in the Candle Batch Summary app; the old "?" still works the same.
        for pattern in ("* v_", "* v?"):
            pat = s.glob_to_regex(pattern)
            for ok in ("6 VL", "6 vn", "12 VC"):
                self.assertTrue(pat.match(ok.lower()), (pattern, ok))
            for bad in ("6 V", "6 VAN", "6 vase", "6 VL x", "6 V "):
                self.assertFalse(pat.match(bad.lower()), (pattern, bad))
        self.assertTrue(s.glob_to_regex("*dip*").match("4 dip 2cm"))      # * still means any text
        self.assertFalse(s.glob_to_regex("a.c").match("abc"))              # other characters stay literal


class Helpers(unittest.TestCase):
    def setUp(self):
        s.load_settings()

    def test_suggestions(self):
        p = s.suggest_patterns(["4 VL", "6 VN", "10 VN", "40mm", "HoneyJar"])
        self.assertEqual(p["* VN"], ["6 VN", "10 VN"])
        self.assertEqual(p["*mm"], ["40mm"])
        self.assertEqual(p["HoneyJar"], ["HoneyJar"])

    def test_layout_alarm(self):
        ok = [{"items": [(1, "4 dip 2cm", "t", False)]} for _ in range(8)]
        self.assertEqual(s.layout_alarms(ok), [])
        bad = ok[:4] + [{"items": [(1, "title", "title", True)]} for _ in range(4)]      # half have no SKU
        self.assertTrue(s.layout_alarms(bad))
        long_sku = ok[:3] + [{"items": [(1, "x" * 60, "t", False)]}]
        self.assertTrue(s.layout_alarms(long_sku))


if __name__ == "__main__":
    unittest.main()


class GiftMessages(unittest.TestCase):
    """Only a gift MESSAGE (in the slip's NOTES) marks a label; a gift order without one needs nothing."""

    def setUp(self):
        s.load_settings()

    def gifts(self, note_lines, item_lines=("12 TL",)):
        orders, _ = parse([("2001", [(1, list(item_lines))], note_lines)])
        return orders[0]["gift"]

    def test_new_and_old_wording_are_found(self):
        self.assertTrue(self.gifts(["GIFT MESSAGE (print from Etsy):", "Happy Birthday Mum!"]))
        self.assertTrue(self.gifts(["Gift Message:", "Happy Birthday Mum!"]))

    def test_no_note_or_other_notes_do_not_count(self):
        self.assertFalse(self.gifts([]))
        self.assertFalse(self.gifts(["Buyer Note:", "Please leave with the neighbour"]))
        self.assertFalse(self.gifts(["GIFT ORDER"]))                      # old wording for a gift with no message

    def test_item_title_cannot_trigger_it(self):
        self.assertFalse(self.gifts([], item_lines=("Candle with gift message card", "12 TL")))

    def test_gift_message_followed_by_buyer_note(self):
        self.assertTrue(self.gifts(["GIFT MESSAGE (print from Etsy):", "Love Sam", "Buyer Note:", "Thanks"]))

    def test_end_to_end_label_text(self):
        import subprocess
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "shipping_t.pdf", Path(d) / "out.pdf"
            make_pdf(src, [("3001", [(1, ["12 TL"])], ["GIFT MESSAGE (print from Etsy):", "Hi"]),
                           ("3002", [(1, ["60mm"])], [])])
            run = subprocess.run([sys.executable, str(Path(s.__file__)), str(src), "-o", str(out), "--no-open", "--no-picklist", "--no-sort"],
                                 capture_output=True, text=True, cwd=d)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            pages = [p.extract_text() or "" for p in PdfReader(str(out)).pages]
            self.assertIn("GIFT MESSAGE", pages[0])
            self.assertNotIn("GIFT MESSAGE", pages[1])
            self.assertIn("1 order with a gift message", run.stdout)
            self.assertIn("3001", run.stdout)


class RepeatCustomers(unittest.TestCase):
    """The packing slip template prints "REPEAT CUSTOMER (Order #N)"; the label gets * (or ** from
    repeat_double_star_from orders). If the template wording changes these tests are the early warning."""

    def setUp(self):
        s.load_settings()

    def repeat(self, text, number="4001"):
        orders, _ = parse([(number, [(1, ["12 TL"])], [], text)])
        return orders[0]

    def test_number_is_read_and_is_not_taken_as_the_order_number(self):
        o = self.repeat("REPEAT CUSTOMER (Order #4)")
        self.assertEqual(o["repeat"], 4)
        self.assertEqual(o["order"], "4001")            # not "4" from "(Order #4)"

    def test_star_glyphs_and_capitals_do_not_matter(self):
        self.assertEqual(self.repeat("* REPEAT CUSTOMER (Order #12) *")["repeat"], 12)
        self.assertEqual(self.repeat("Repeat Customer (Order #3)")["repeat"], 3)

    def test_not_a_repeat(self):
        self.assertIsNone(self.repeat(None)["repeat"])
        self.assertEqual(s.repeat_mark(None), "")

    def test_repeat_without_a_number_still_counts(self):
        self.assertEqual(self.repeat("REPEAT CUSTOMER")["repeat"], 0)
        self.assertEqual(s.repeat_mark(0), "*")

    def test_stars_and_settings(self):
        self.assertEqual(s.repeat_mark(2), "*")
        self.assertEqual(s.repeat_mark(14), "*")
        self.assertEqual(s.repeat_mark(15), "**")
        old = dict(s.S)
        try:
            s.S["repeat_double_star_from"] = 0
            self.assertEqual(s.repeat_mark(99), "*")
            s.S["repeat_star"] = False
            self.assertEqual(s.repeat_mark(5), "")
        finally:
            s.S.clear(); s.S.update(old)

    def test_end_to_end_label_text(self):
        import subprocess
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "shipping_t.pdf", Path(d) / "out.pdf"
            make_pdf(src, [("5001", [(1, ["12 TL"])], [], "REPEAT CUSTOMER (Order #4)"),
                           ("5002", [(1, ["60mm"])], []),
                           ("5003", [(2, ["4 2cm"])], [], "REPEAT CUSTOMER (Order #15)")])
            run = subprocess.run([sys.executable, str(Path(s.__file__)), str(src), "-o", str(out), "--no-open", "--no-picklist", "--no-sort"],
                                 capture_output=True, text=True, cwd=d)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            pages = [p.extract_text() or "" for p in PdfReader(str(out)).pages]
            self.assertIn("12 TL *", pages[0])
            self.assertNotIn("*", pages[1])
            self.assertIn("**", pages[2])
            self.assertIn("2 repeat customers", run.stdout)


class PickListLayout(unittest.TestCase):
    """The pick list ends with a bold TOTAL ORDERS under the Orders column, and group titles sit in the SKU column."""

    def setUp(self):
        s.load_settings()

    def words(self, rows, total, size="4x6"):
        import pdfplumber
        from pypdf import PdfWriter
        w = PdfWriter()
        for p in s.picklist_pages(rows, [], "Pick list", size, total):
            w.add_page(p)
        buf = io.BytesIO()
        w.write(buf)
        buf.seek(0)
        with pdfplumber.open(buf) as pl:
            return pl.pages[0].extract_words(extra_attrs=["fontname", "size"]), float(pl.pages[0].width)

    def test_total_orders_replaces_total_items(self):
        rows = [("2 dip 2cm", 3, 2, "Dipped 2cm"), ("6 VN", 1, 1, "Votive natural")]
        words, _ = self.words(rows, 7)
        text = " ".join(w["text"] for w in words)
        self.assertIn("Total orders", text)
        self.assertNotIn("Total items", text)
        total = [w for w in words if w["text"] == "7"][0]
        label = [w for w in words if w["text"] == "Total"][0]
        self.assertIn("Bold", total["fontname"])
        self.assertIn("Bold", label["fontname"])
        self.assertGreater(total["size"], 9)                       # a little larger than the 9pt SKU rows
        orders_hdr = [w for w in words if w["text"] == "Orders" and w["top"] < 80][0]
        self.assertAlmostEqual(total["x1"], orders_hdr["x1"], delta=2)      # number sits under the Orders column
        self.assertGreater(total["x0"] - [w for w in words if w["text"] == "orders" and w["top"] > 80][-1]["x1"], 5)   # gap after the words

    def test_group_title_is_in_the_sku_column(self):
        words, _ = self.words([("2 dip 2cm", 1, 1, "Dipped 2cm")], 1)
        title = [w for w in words if w["text"] == "Dipped"][0]
        sku = [w for w in words if w["text"] == "2" and w["top"] > title["top"]][0]
        qty_hdr = [w for w in words if w["text"] == "Qty"][0]
        self.assertAlmostEqual(title["x0"], sku["x0"], delta=1.5)           # same left edge as the SKUs
        self.assertGreater(title["x0"], qty_hdr["x1"])                      # not over the Qty column
