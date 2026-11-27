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


class PriorityPostage(unittest.TestCase):
    """Tracked 24 (a huge "24" on the label) and 1st class print first; sort_groups.json can switch it off."""

    def setUp(self):
        self.real_here = s.HERE
        s.HERE = Path(__file__).resolve().parent.parent / "defaults"
        s.load_settings()
        self.groups = s.load_groups()

    def tearDown(self):
        s.HERE = self.real_here
        s.load_settings()
        s.load_groups()

    def label_page(self, draw):
        import pdfplumber
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "label.pdf"
            c = canvas.Canvas(str(f), pagesize=(288, 432))
            draw(c)
            c.save()
            with pdfplumber.open(str(f)) as pl:
                pg = pl.pages[0]
                return s.label_priority(pg, pg.extract_text() or "")

    def test_tracked_24_is_priority_tracked_48_is_not(self):
        def tracked(n):
            def draw(c):
                c.setFont("Helvetica-Bold", 49)
                c.drawString(129, 380, n)
                c.setFont("Helvetica", 25)
                c.drawString(20, 340, "Tracked")
            return draw
        self.assertEqual(self.label_page(tracked("24")), "Tracked 24")
        self.assertEqual(self.label_page(tracked("48")), "")

    def test_a_small_24_elsewhere_does_not_count(self):
        def draw(c):
            c.setFont("Helvetica", 25)
            c.drawString(20, 340, "Tracked")
            c.setFont("Helvetica", 9)
            c.drawString(20, 300, "24")
        self.assertEqual(self.label_page(draw), "")

    def test_first_class_wording_from_settings(self):
        def draw(c):
            c.setFont("Helvetica", 12)
            c.drawString(20, 340, "Royal Mail 1st Class")
        self.assertEqual(self.label_page(draw), "1st class")

    def order(self, no, sku, priority=""):
        return {"page": 0, "order": no, "items": [(1, sku, "", False)], "slip": True, "repeat": None, "gift": False, "priority": priority}

    def test_priority_orders_sort_first_then_by_group(self):
        orders = [self.order("1", "4 dip 2cm"), self.order("2", "12 TL", "Tracked 24"),
                  self.order("3", "2 dip 2cm", "1st class"), self.order("4", "6 TL")]
        orders.sort(key=lambda o: s.sort_key(o, self.groups))
        self.assertEqual([o["order"] for o in orders], ["3", "2", "1", "4"])      # priority (by group), then the rest (by group)

    def test_option_in_sort_groups_switches_it_off(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "sort_groups.json").write_text('{"priority_first": false, "groups": [{"name": "A", "match": ["* dip 2cm"]}, {"name": "T", "match": ["* TL"]}]}')
            s.HERE = Path(d)
            groups = s.load_groups()
            self.assertFalse(s.GROUP_OPTS["priority_first"])
            orders = [self.order("1", "4 dip 2cm"), self.order("2", "12 TL", "Tracked 24")]
            orders.sort(key=lambda o: s.sort_key(o, groups))
            self.assertEqual([o["order"] for o in orders], ["1", "2"])            # plain group order again
            (Path(d) / "sort_groups.json").write_text('{"priority_first": "no", "groups": []}')
            s.load_groups()
            self.assertTrue(any("priority_first" in e for e in s.FILE_ERRORS))    # a typo is reported, not silently ignored
            self.assertTrue(s.GROUP_OPTS["priority_first"])

    def test_problem_orders_still_come_before_priority(self):
        bad = {"page": 0, "order": "9", "items": [], "slip": True, "repeat": None, "gift": False, "priority": ""}
        orders = [self.order("2", "12 TL", "Tracked 24"), bad]
        orders.sort(key=lambda o: s.sort_key(o, self.groups))
        self.assertEqual(orders[0]["order"], "9")

    def test_picklist_counts_priority_orders_per_sku(self):
        orders = [self.order("1", "4 dip 2cm", "Tracked 24"), self.order("2", "4 dip 2cm"), self.order("3", "12 TL")]
        rows, _ = s.picklist(orders, self.groups)
        by = {r[0]: r for r in rows}
        self.assertEqual(by["4 dip 2cm"][4], 1)
        self.assertEqual(by["12 TL"][4], 0)


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


class NoteSlips(unittest.TestCase):
    """An order whose slip has a NOTES section keeps its slip behind its label and gets NOTE on the label."""

    def setUp(self):
        s.load_settings()

    def has_note(self, note_lines):
        orders, _ = parse([("4001", [(1, ["12 TL"])], note_lines)])
        return orders[0]["note"]

    def test_which_notes_count(self):
        self.assertTrue(self.has_note(["2 dark green and 2 wine purple candles"]))
        self.assertTrue(self.has_note(["Buyer Note:", "Please leave with the neighbour"]))
        self.assertFalse(self.has_note([]))                                          # empty NOTES section
        self.assertFalse(self.has_note(["Imported from Etsy. Receipt ID: 4236074715"]))          # written by the sync, not a note
        self.assertFalse(self.has_note(["Imported from Etsy. Receipt ID: 42360. Etsy discount: £3.50"]))
        self.assertFalse(self.has_note(["Imported from Etsy. Receipt ID: 42360 GIFT ORDER (Do not show prices on packing slip)"]))
        self.assertTrue(self.has_note(["Imported from Etsy. Receipt ID: 42360", "Leave behind the recycling box"]))   # real note next to it
        self.assertFalse(self.has_note(["GIFT MESSAGE (print from Etsy):", "Hi Mum"]))   # gift message only: it has its own mark
        self.assertTrue(self.has_note(["GIFT MESSAGE (print from Etsy):", "Hi Mum", "Buyer Note:", "Thanks"]))

    def test_slip_page_is_remembered(self):
        orders, _ = parse([("4001", [(1, ["12 TL"])], []), ("4002", [(1, ["60mm"])], ["Please wrap it"])])
        self.assertEqual([o["slip_page"] for o in orders], [1, 3])                   # label 0, slip 1, label 2, slip 3

    def test_end_to_end_slip_kept_and_label_marked(self):
        import subprocess
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "shipping_t.pdf", Path(d) / "out.pdf"
            make_pdf(src, [("5001", [(1, ["12 TL"])], ["2 dark green and 2 wine purple candles"]),
                           ("5002", [(1, ["60mm"])], [])])
            cmd = [sys.executable, str(Path(s.__file__)), str(src), "-o", str(out), "--no-open", "--no-picklist", "--no-sort"]
            run = subprocess.run(cmd, capture_output=True, text=True, cwd=d)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            pages = [p.extract_text() or "" for p in PdfReader(str(out)).pages]
            self.assertEqual(len(pages), 3)                                          # label 5001, its slip, label 5002
            self.assertIn("NOTE", pages[0])
            self.assertIn("2 dark green", pages[1])                                  # the kept slip, right behind its label
            self.assertNotIn("NOTE", pages[2])
            self.assertIn("1 order with a note", run.stdout)
            self.assertIn("1 packing slip with a note", run.stdout)


class LabelCovers(unittest.TestCase):
    """Options to cover "MARKETPLACE SELLER" and "Shopify" on the label, write a replacement, and add the logo."""

    def setUp(self):
        s.load_settings()

    def tearDown(self):
        s.load_settings()

    def regions(self, extra=None):
        import pdfplumber
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "label.pdf"
            c = canvas.Canvas(str(f), pagesize=(288, 432))
            c.setFont("Helvetica", 12)
            c.drawString(20, 400, "Mr Seller")                                  # a customer named Seller: top area, must never match
            c.setFont("Helvetica-Bold", 16)
            c.drawString(21, 432 - 346, "MARKETPLACE")
            c.drawString(21, 432 - 362, "SELLER")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(265, 432 - 395, "Shopify")
            for fn in (extra or []):
                fn(c)
            c.save()
            with pdfplumber.open(str(f)) as pl:
                return s.label_regions(pl.pages[0])

    def test_finds_the_two_areas_in_the_footer_only(self):
        r = self.regions()
        self.assertEqual(set(r), {"marketplace", "shopify"})
        x0, top, x1, bottom, size = r["marketplace"]
        self.assertLess(x0, 25)
        self.assertGreater(x1, 100)
        self.assertGreater(top, 320)                                           # not the "Seller" in the address area

    def test_nothing_found_on_a_label_without_the_wording(self):
        import pdfplumber
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "label.pdf"
            c = canvas.Canvas(str(f), pagesize=(288, 432))
            c.drawString(20, 400, "Mr Seller")
            c.save()
            with pdfplumber.open(str(f)) as pl:
                self.assertEqual(s.label_regions(pl.pages[0]), {})

    def overlay_text(self, regions):
        ov = s.decoration_overlay(288, 432, regions)
        return None if ov is None else (ov.extract_text() or "")

    def test_all_off_draws_nothing(self):
        s.S.update(cover_marketplace_seller=False, cover_shopify=False, logo=False)
        self.assertIsNone(s.decoration_overlay(288, 432, self.regions()))

    def test_replacement_text_only_when_shopify_is_covered(self):
        r = self.regions()
        s.S.update(cover_shopify=True, shopify_replacement="beeminedorset.com")
        self.assertIn("beeminedorset.com", self.overlay_text(r))
        s.S.update(shopify_replacement="")                                     # cover only, no text
        self.assertEqual(self.overlay_text(r), "")
        s.S.update(cover_shopify=False, cover_marketplace_seller=True)
        self.assertEqual(self.overlay_text(r), "")                              # marketplace cover has no text
        self.assertIsNotNone(s.decoration_overlay(288, 432, r))

    def test_logo_is_placed_by_its_own_position_and_needs_no_wording(self):
        s.S.update(logo=True, cover_marketplace_seller=False, cover_shopify=False, sku_to_top=False)
        self.assertIsNotNone(s.decoration_overlay(288, 432, self.regions()))
        self.assertIsNotNone(s.decoration_overlay(288, 432, {}))                # a label without the wording still gets the logo
        s.S["logo"] = False
        self.assertIsNone(s.decoration_overlay(288, 432, {}))

    def test_sku_to_top_covers_the_marketplace_block_and_moves_the_stamp(self):
        r = self.regions()
        s.S.update(sku_to_top=False, logo=False, cover_marketplace_seller=False, cover_shopify=False)
        self.assertEqual(s.stamp_position(r, 40, 378, 11), (40, 378, None, None))            # off: the x / y settings
        self.assertIsNone(s.decoration_overlay(288, 432, r))
        s.S["sku_to_top"] = True
        x, y, max_w, bottom = s.stamp_position(r, 40, 378, 11)
        mk = r["marketplace"]
        self.assertAlmostEqual(x, mk[0])                                                       # left edge of the block
        self.assertAlmostEqual(y, mk[1] + 11 * 0.9)                                            # first line at the top of the block
        self.assertIsNone(max_w)                                                               # no logo: full width
        self.assertEqual(bottom, 408.0)                                                        # no footer wording on this label: default floor
        self.assertIsNotNone(s.decoration_overlay(288, 432, r))                                # the old wording is covered
        self.assertEqual(s.stamp_position({}, 40, 378, 11), (40, 378, None, None))             # no block found: back to x / y

    def test_text_is_kept_clear_of_the_logo(self):
        r = self.regions()
        s.S.update(sku_to_top=True, logo=True, logo_x=100)
        x, y, max_w, bottom = s.stamp_position(r, 40, 378, 11)
        self.assertAlmostEqual(max_w, 100 - x - 4)
        size, cols, ok = s.layout(["2 x 20 dip 2cm *", "5 x 60mm"], 288, 432, x, y, 11, max_w, bottom)
        self.assertLess(size, 11)                                                              # shrunk to fit beside the logo
        self.assertTrue(ok)
        size_full, _, _ = s.layout(["2 x 20 dip 2cm *", "5 x 60mm"], 288, 432, x, y, 11)
        self.assertEqual(size_full, 11)                                                        # without the limit it fits at full size

    def test_logo_files_exist_and_style_picks_the_file(self):
        self.assertTrue((Path(s.__file__).parent / "assets" / "logo_thermal.png").exists())
        self.assertTrue((Path(s.__file__).parent / "assets" / "logo_colour.png").exists())
        s.S["logo_style"] = "thermal"
        self.assertEqual(s.logo_path().name, "logo_thermal.png")
        s.S["logo_style"] = "colour"
        self.assertEqual(s.logo_path().name, "logo_colour.png")


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

    def test_priority_flag_and_count_on_the_pick_list(self):
        import pdfplumber
        from pypdf import PdfWriter
        w = PdfWriter()
        rows = [("2 dip 2cm", 3, 2, "Dipped 2cm", 1), ("6 VN", 1, 1, "Votive natural", 0)]
        for p in s.picklist_pages(rows, [], "Pick list", "4x6", 3, 1):
            w.add_page(p)
        buf = io.BytesIO()
        w.write(buf)
        buf.seek(0)
        with pdfplumber.open(buf) as pl:
            text = pl.pages[0].extract_text()
        self.assertIn("P1", text)                       # beside the SKU that has a priority order
        self.assertIn("PRIORITY orders", text)
        self.assertEqual(text.count("P1"), 1)           # not beside the other SKU
        s.S["picklist_priority_flag"] = False           # the setting turns the flag off
        w = PdfWriter()
        for p in s.picklist_pages(rows, [], "Pick list", "4x6", 3, 1):
            w.add_page(p)
        buf = io.BytesIO()
        w.write(buf)
        buf.seek(0)
        with pdfplumber.open(buf) as pl:
            self.assertNotIn("PRIORITY", pl.pages[0].extract_text())

    def test_group_title_is_in_the_sku_column(self):
        words, _ = self.words([("2 dip 2cm", 1, 1, "Dipped 2cm")], 1)
        title = [w for w in words if w["text"] == "Dipped"][0]
        sku = [w for w in words if w["text"] == "2" and w["top"] > title["top"]][0]
        qty_hdr = [w for w in words if w["text"] == "Qty"][0]
        self.assertAlmostEqual(title["x0"], sku["x0"], delta=1.5)           # same left edge as the SKUs
        self.assertGreater(title["x0"], qty_hdr["x1"])                      # not over the Qty column
