// Builds docs/Label-Stamper-User-Guide.docx (printable guide for the people who run the app).
// Needs the "docx" npm package:   npm install docx   then:   node docs/build-user-guide.js
// Keep this in step with the SOP (SOP-FUL-001) and README.md whenever the app's behaviour changes.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, LevelFormat, HeadingLevel, Footer, PageNumber,
} = require("docx");

const FONT = "Arial";
const W = 9638; // A4 with 2cm margins, in DXA

const t = (text, o = {}) => new TextRun({ text, font: FONT, ...o });
const p = (children, o = {}) =>
  new Paragraph({ spacing: { after: 120 }, ...o, children: Array.isArray(children) ? children : [t(children)] });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [t(text)] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [t(text)] });
const step = (children) =>
  new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 100 }, children: Array.isArray(children) ? children : [t(children)] });
const bullet = (children) =>
  new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 80 }, children: Array.isArray(children) ? children : [t(children)] });

const border = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
const borders = { top: border, bottom: border, left: border, right: border };

function table(cols, header, rows) {
  const cell = (content, i, head) =>
    new TableCell({
      borders,
      width: { size: cols[i], type: WidthType.DXA },
      shading: head ? { fill: "E8EEF7", type: ShadingType.CLEAR, color: "auto" } : undefined,
      margins: { top: 70, bottom: 70, left: 110, right: 110 },
      children: [new Paragraph({ children: Array.isArray(content) ? content : [t(content, { bold: head, size: 20 })] })],
    });
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((c, i) => cell(c, i, true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) })),
    ],
  });
}

const b = (s) => t(s, { bold: true });

const doc = new Document({
  creator: "Beemine",
  title: "Printing shipping labels with SKUs - user guide",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { font: FONT, size: 40, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 0, after: 80 } } },
      { id: "Heading1", name: "heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] },
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: {
      default: new Footer({
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
          t("Beemine - label stamper user guide - page ", { size: 18, color: "666666" }),
          new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: "666666" }),
        ] })],
      }),
    },
    children: [
      new Paragraph({ heading: HeadingLevel.TITLE, children: [t("Printing shipping labels with SKUs")] }),
      p([t("User guide for anyone who packs orders", { color: "666666" })], { spacing: { after: 240 } }),

      h1("What this does"),
      p("Shopify gives us one PDF with a shipping label followed by a packing slip for every order. The label stamper turns it into a PDF of labels only. Each label has the SKU and quantity of what is in the parcel stamped on it in blue, for example “3 x kg h”. The last page of the PDF is a pick list: the total of each SKU in the batch, for collecting stock from the shelves."),
      p("You do not need to know anything about computers beyond double-clicking."),

      h1("Printing a batch of labels"),
      step([b("Download from Shopify. "), t("Download the shipping documents for the batch (4x6 size). The file goes into your Downloads folder, with a name starting “shipping”.")]),
      step([b("Open the label-sku-stamper folder "), t("(C:\\beemine-automations\\label-sku-stamper) and double-click "), b("run.bat"), t(". A black window opens and lists every order with its SKU(s). It uses the newest shipping file in Downloads by itself. To use a different file, drag that PDF onto run.bat instead.")]),
      step([b("Read the list in the window. "), t("The next section explains the colours. A yellow line at the end listing “SKUs not in a named sort group” just means some new SKUs need adding to the label order; tell Bruno.")]),
      step([b("The finished PDF opens by itself. "), t("Look through it. Each label should show a blue SKU at the bottom, clear of the barcode and the address. The last page is the pick list; its bold Total orders line says how many orders are in the batch.")]),
      step([b("Print the whole PDF "), t("on the label printer (4x6in). Labels come out sorted so identical orders are together, priority postage (Tracked 24 or 1st class) comes first after anything that needs checking. The pick list comes out last. To print only the pick list, print only the last page.")]),
      step([b("Press any key "), t("to close the black window. Your download is moved to the “done” folder, so the next run will not use it again. Nothing is deleted.")]),

      h1("What the colours in the window mean"),
      table([1900, 4200, 3538], ["In the window", "Meaning", "What to do"], [
        ["Green ok", "SKU found. All is well.", "Nothing."],
        ["Yellow ~~", "That item has no SKU in Shopify. Part of the product title was stamped instead.", "Check the packing slip. The SKU should be added to the listing."],
        ["Red !! (and a red “?? CHECK SLIP” on the label)", "Nothing could be read from that slip.", "Read the packing slip by hand."],
        ["Bold red “WARNING … layout may have changed”", "Many orders in this batch have no SKU, which may mean Shopify changed the packing slip.", "Do not print yet. Compare a few labels with their slips and tell Bruno."],
      ]),
      p("", { spacing: { after: 60 } }),
      p("The last lines say, for example, “32 labels, 2 problems”, and list each problem. A message about a label with no slip (or a slip with no label) means the PDF is incomplete: download it from Shopify again."),

      h1("If something goes wrong"),
      table([3300, 6338], ["What you see", "What to do"], [
        ["“No shipping*.pdf found”", "The file has not been downloaded yet. Download it from Shopify, or drag the PDF onto run.bat."],
        ["“no packing slips found”", "You picked a file that was already stamped (its name ends in _sku). Use the original download, which is in the “done” folder."],
        ["“Missing package” or “No Python with the required packages”", "The computer’s setup is incomplete. Tell Bruno."],
        ["The blue text overlaps the label’s printing", "The label layout has changed. Tell Bruno; the position can be adjusted."],
        ["The PDF did not open by itself", "Open the newest file in the “Labels” folder yourself."],
        ["Anything else, or the window closes straight away", "Do not print. Tell Bruno what the window said."],
      ]),

      h1("Printing the same labels again"),
      p("Open the “done” folder, and drag the original PDF onto run.bat. A new file is made in the “Labels” folder; the earlier one is not replaced."),

      h1("Good to know"),
      bullet("The labels come out in groups, for example all 2cm dipped candles together, then tealights, with honey and beeswax last. Bruno can change the order in a small file called sort_groups.json."),
      bullet("Parcels posted Tracked 24 or 1st class (priority postage) come out FIRST, so they can be packed and posted first. In the window each one ends with a red [PRIORITY: …], and on the pick list (last page) a red P1, P2 … beside a SKU says how many of its orders are priority, with a red PRIORITY orders count under Total orders. Bruno can switch this off in sort_groups.json."),
      bullet("A small * after the SKU on a label means a repeat customer (two ** means a very frequent one). It comes from the packing slip, so it is stamped automatically."),
      bullet("A line NOTE under the SKUs on a label means the customer left a note. That order’s packing slip is kept: it comes out as the page right behind its label, with the note on it. Read the note and pack as it says (for example the colours of a mixed set). The window lists those orders in yellow."),
      bullet("A last line GIFT MESSAGE on a label means the order has a gift message. Print it from Etsy and put it in the parcel. The window also lists those orders in yellow. A gift order with no message gets nothing."),
      bullet("Labels and downloads are kept in the “Labels” and “done” folders. Keep them; there is no need to delete anything."),
      bullet("The PDFs contain customers’ names and addresses. Do not email or share them, or put them online."),
      bullet("Optional: watch.bat can be left open all day. It stamps each new Shopify download by itself. It stops when you close its window."),
      bullet("Questions or problems: ask Bruno."),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Label-Stamper-User-Guide.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out);
});
