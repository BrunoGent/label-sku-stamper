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
    """orders: list of (order_no, [item]); item = (qty, [text lines]). Layout mimics the Shopify 4x6 slip."""
    c = canvas.Canvas(str(path), pagesize=(288, 432))
    for number, items in orders:
        c.setFont("Helvetica", 10)
        c.drawString(20, 400, "Royal Mail tracked label")           # the label page
        c.showPage()
        c.setFont("Helvetica", 5.2)
        c.drawString(20, 400, f"Order #{number}")
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
