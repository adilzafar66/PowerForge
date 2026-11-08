"""Draw synthetic documents and label their printed occurrences from the authoring coordinates.

Requires the repository's PyMuPDF and Pillow. Run only when authoring a corpus version.
The committed bytes and annotations are the evaluation inputs.
"""

import hashlib
import json
import random
import re
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
EVALS = ROOT.parents[1]


def rectangle(box, width, height):
    return [round(value / (width if i % 2 == 0 else height), 6) for i, value in enumerate(box)]


class Design:
    def __init__(self, name, page=None, *, size=(1200, 600), rotated=False):
        self.page = page
        self.width, self.height = size
        self.rotated = rotated
        self.image = Image.new("RGB", size, "white") if page is None else None
        self.draw = ImageDraw.Draw(self.image) if self.image else None
        self.gold = dict(id=name, words=[], lines=[], tables=[], claims=[])

    def box(self, box):
        return rectangle(box, self.width, self.height)

    def label(self, name, text, x, y, *, size=14, basis=None, printed=True, paint=True):
        if not text:
            return name
        basis = basis or ("NATIVE_PDF" if self.page is not None else "OCR")
        font = ImageFont.load_default(size=size) if self.draw else None
        words = []
        for index, match in enumerate(re.finditer(r"\S+", text)):
            word = match[0]
            prefix = text[: match.start()]
            if font:
                start = x + font.getlength(prefix)
                bounds = self.draw.textbbox((start, y), word, font=font)
            else:
                start = x + pymupdf.get_text_length(prefix, fontsize=size)
                width = pymupdf.get_text_length(word, fontsize=size)
                bounds = (start, y - size * 0.98, start + width, y + size * 0.25)
            categories = []
            if re.fullmatch(r"[A-Z]+-\d+", word):
                categories.append("tag")
            if re.fullmatch(r"[+-]?\d[\d.,]*(?:[A-Za-z²%]+)?", word):
                categories.append("value")
            if word.strip("()") in {"kV", "V", "A", "AF", "AT", "kA", "kVA", "m", "mm²", "%"}:
                categories.append("unit")
            if any(char in word for char in ".,±²%/"):
                categories.append("punctuation")
            item = dict(
                id=f"{name}.{index}",
                text=word,
                box=self.box(bounds),
                basis=basis,
                categories=categories,
            )
            if not printed:
                item["printed"] = False
            self.gold["words"].append(item)
            words.append(item)
        self.gold["lines"].append(dict(id=name, words=[w["id"] for w in words]))
        if paint and self.draw:
            self.draw.text((x, y), text, font=font, fill="black")
        elif paint:
            origin = (y, self.width - x) if self.rotated else (x, y)
            self.page.insert_text(
                origin,
                text,
                fontsize=size,
                rotate=90 if self.rotated else 0,
                render_mode=0 if printed else 3,
            )
        return name

    def segment(self, a, b):
        if self.draw:
            self.draw.line((a, b), fill="black", width=2)
        else:
            self.page.draw_line(a, b, width=0.7)

    def claim(
        self,
        name,
        line,
        equipment,
        *,
        tag=None,
        attribute=None,
        value=None,
        unit=None,
        status="MAPPED",
        owner=None,
        category="NUMBER",
    ):
        self.gold["claims"].append(
            dict(
                id=name,
                line=line,
                kind="ATTRIBUTE_VALUE" if attribute else "EQUIPMENT_MENTION",
                equipment_type=equipment,
                tag=tag,
                attribute=attribute,
                value=value,
                unit=unit,
                status=status,
                owner=owner,
                value_type=category if value is not None else None,
            )
        )

    def table(self, name, rows, xs, ys, *, ruled=False, factors=(), size=14, offsets=None):
        cells = []
        if ruled:
            for y in ys:
                self.segment((xs[0], y), (xs[-1], y))
            for x in xs:
                self.segment((x, ys[0]), (x, ys[-1]))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                ref = f"{name}-{r}-{c}"
                displacement = (offsets or {}).get((r, c), (0, 0))
                x = xs[c] + (12 if self.draw else 7) + displacement[0]
                y = ys[r] + (22 if self.draw else 21) + displacement[1]
                if text:
                    self.label(ref, text, x, y, size=size)
                cells.append(
                    dict(
                        position=[r, c],
                        span=[1, 1],
                        line=ref if text else None,
                        headers=[[0, c]] if r else [],
                    )
                )
        self.gold["tables"].append(
            dict(
                id=name,
                box=self.box((xs[0], ys[0], xs[-1], ys[-1])),
                rows=len(rows),
                columns=len(xs) - 1,
                cells=cells,
                factors=list(factors),
            )
        )

    def data(self, path, page=1, *, ocr=False, force=False, note="", **extra):
        return dict(
            **self.gold, source=path, page=page, ocr_gold=ocr, force_ocr=force, note=note, **extra
        )


def png(image):
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def transformer_claims(design, name, voltages, *, first_row=1):
    for row, (tag, normalized) in enumerate(voltages, first_row):
        design.claim(f"eq{row}", f"{name}-{row}-0", "TWO_WINDING_TRANSFORMER", tag=tag)
        design.claim(
            f"v{row}",
            f"{name}-{row}-1",
            "TWO_WINDING_TRANSFORMER",
            attribute="secondary_voltage",
            value=normalized,
            unit="kV",
            owner=f"eq{row}",
        )


def nameplate(design, label, tag, field, raw, equipment, attribute, value, unit, *, size=48):
    design.label("name", f"{label} {tag}", 60, 60, size=size)
    design.label("value", f"{field}: {raw}", 60, 200, size=size)
    design.claim("eq", "name", equipment, tag=tag)
    design.claim("v", "value", equipment, attribute=attribute, value=value, unit=unit, owner="eq")


def positioned():
    # Read the printed cells and grid from the frozen 6D fixture, rendered at 72 dpi.
    d = Design("positioned-6d", size=(500, 240))
    d.page = object()
    d.draw = None
    d.label("title", "2-Winding Transformer Schedule", 25, 35, size=16, paint=False)
    cells = []
    for row, column, text in [
        (0, 0, "Equipment"),
        (0, 1, "Secondary (V)"),
        (1, 0, "TX-1"),
        (1, 1, "600"),
    ]:
        ref = f"grid-{row}-{column}"
        d.label(ref, text, 25 + column * 220, 85 + row * 45, size=12, paint=False)
        cells.append(
            dict(
                position=[row, column], span=[1, 1], line=ref, headers=[[0, column]] if row else []
            )
        )
    d.gold["tables"].append(
        dict(
            id="grid",
            box=d.box((20, 62, 460, 152)),
            rows=2,
            columns=2,
            cells=cells,
            factors=["ruled"],
        )
    )
    transformer_claims(d, "grid", [("TX-1", "0.6")])
    return d.data(
        "tables/v1/sources/positioned_schedule.pdf",
        baseline="table-pdf",
        note="The original 6D positioned PDF with the same two claim meanings.",
    )


def authored_book():
    doc = pymupdf.open()
    source = "spatial/v1/sources/electrical-fixtures.pdf"
    cases = []
    tx = "TWO_WINDING_TRANSFORMER"

    def page(name, *, rotated=False):
        authored = doc.new_page(width=400 if rotated else 600, height=600 if rotated else 400)
        if rotated:
            authored.set_rotation(90)
        return Design(name, authored, size=(600, 400), rotated=rotated)

    d = page("regular-borderless")
    d.label("title", "2-Winding Transformer Schedule", 30, 27)
    d.table(
        "grid",
        [("Equipment", "Secondary (V)"), ("TX-1", "600"), ("TX-2", "600"), ("TX-3", "690")],
        [25, 250, 560],
        [44, 78, 112, 146, 180],
    )
    transformer_claims(d, "grid", [("TX-1", "0.6"), ("TX-2", "0.6"), ("TX-3", "0.69")])
    cases.append(d.data(source, 1, note="Repeated values have distinct equipment and occurrences."))

    d = page("irregular-cable")
    d.label("title", "Cable Schedule", 30, 27)
    d.table(
        "grid",
        [
            ("Cable", "Length (m)", "Conductor Size", "Material"),
            ("CBL-1", "30", "240 mm²", "Copper"),
            ("CBL-2", "", "300 mm²", "Aluminum"),
            ("CBL-3", "47", "120 mm²", ""),
        ],
        [25, 144, 265, 410, 575],
        [50, 83, 171, 208, 250],
        factors=["irregular_gaps", "sparse", "four_columns"],
        offsets={(2, 2): (45, 9), (3, 1): (34, 3)},
    )
    for row, length, size, material in (
        (1, "30", "240 mm²", "COPPER"),
        (2, None, "300 mm²", "ALUMINUM"),
        (3, "47", "120 mm²", None),
    ):
        owner = f"eq{row}"
        d.claim(owner, f"grid-{row}-0", "CABLE", tag=f"CBL-{row}")
        if length:
            d.claim(
                f"length{row}",
                f"grid-{row}-1",
                "CABLE",
                attribute="length",
                value=length,
                unit="m",
                owner=owner,
            )
        d.claim(
            f"size{row}",
            f"grid-{row}-2",
            "CABLE",
            attribute="conductor_size",
            value=size,
            owner=owner,
            category="TEXT",
        )
        if material:
            d.claim(
                f"material{row}",
                f"grid-{row}-3",
                "CABLE",
                attribute="conductor_material",
                value=material,
                owner=owner,
                category="ENUM",
            )
    cases.append(
        d.data(source, 2, note="The blank slots and irregular row gaps are authored gold.")
    )

    d = page("merged-header")
    d.label("title", "2-Winding Transformer Schedule", 35, 28)
    for y in (52, 135, 178, 221):
        d.segment((30, y), (570, y))
    d.segment((200, 91), (570, 91))
    for x in (30, 200, 570):
        d.segment((x, 52), (x, 221))
    d.segment((390, 91), (390, 221))
    cells = []
    for r, c, rs, cs, x, y, raw, headers in (
        (0, 0, 2, 1, 38, 76, "Equipment", []),
        (0, 1, 1, 2, 210, 76, "Voltage", []),
        (1, 1, 1, 1, 210, 116, "Primary (V)", [(0, 1)]),
        (1, 2, 1, 1, 399, 116, "Secondary (V)", [(0, 1)]),
        (2, 0, 1, 1, 38, 156, "TX-4", [(0, 0)]),
        (2, 1, 1, 1, 210, 156, "12470", [(0, 1), (1, 1)]),
        (2, 2, 1, 1, 399, 156, "690", [(0, 1), (1, 2)]),
        (3, 0, 1, 1, 38, 200, "TX-5", [(0, 0)]),
        (3, 1, 1, 1, 210, 200, "25000", [(0, 1), (1, 1)]),
        (3, 2, 1, 1, 399, 200, "690", [(0, 1), (1, 2)]),
    ):
        ref = f"merged-{r}-{c}"
        d.label(ref, raw, x, y, size=12)
        cells.append(dict(position=[r, c], span=[rs, cs], line=ref, headers=headers))
    d.gold["tables"].append(
        dict(
            id="merged",
            box=d.box((30, 52, 570, 221)),
            rows=4,
            columns=3,
            cells=cells,
            factors=["ruled", "hierarchical", "merged"],
        )
    )
    for row, tag, primary in ((2, "TX-4", "12.47"), (3, "TX-5", "25")):
        owner = f"eq{row}"
        d.claim(owner, f"merged-{row}-0", tx, tag=tag)
        d.claim(
            f"primary{row}",
            f"merged-{row}-1",
            tx,
            attribute="primary_voltage",
            value=primary,
            unit="kV",
            owner=owner,
        )
        d.claim(
            f"secondary{row}",
            f"merged-{row}-2",
            tx,
            attribute="secondary_voltage",
            value="0.69",
            unit="kV",
            owner=owner,
        )
    cases.append(d.data(source, 3, note="Merged voltage band and equipment rowspan."))

    d = page("two-column-spec")
    d.label("name", "2-Winding Transformer TX-8", 35, 50)
    d.label("value", "Secondary Voltage: 690 V", 35, 76)
    d.label("invalid", "Primary Voltage: 480 furlong", 35, 102)
    d.label("name2", "LV Breaker CB-8", 340, 50)
    d.label("value2", "Normally Closed: Yes", 340, 76)
    d.claim("eq", "name", tx, tag="TX-8")
    d.claim("v", "value", tx, attribute="secondary_voltage", value="0.69", unit="kV", owner="eq")
    d.claim("invalid", "invalid", tx, attribute="primary_voltage", status="INVALID", owner="eq")
    d.claim("br", "name2", "LV_BREAKER", tag="CB-8")
    d.claim(
        "closed",
        "value2",
        "LV_BREAKER",
        attribute="normally_closed",
        value=True,
        owner="br",
        category="BOOLEAN",
    )
    cases.append(d.data(source, 4, note="Separate equipment blocks share the same baselines."))

    d = page("mixed-orientation")
    d.label("title", "2-Winding Transformer Schedule", 35, 28)
    d.table(
        "grid",
        [("Equipment", "Secondary (V)"), ("TX-6", "480"), ("TX-7", "600")],
        [28, 250, 535],
        [44, 80, 116, 152],
        factors=["mixed_orientation"],
    )
    # A vertical engineering note sits close to the schedule, outside the grid.
    d.page.insert_text((560, 150), "FIELD VERIFY", fontsize=13, rotate=90)
    for i, word in enumerate(("FIELD", "VERIFY")):
        offset = pymupdf.get_text_length("FIELD ", fontsize=13) if i else 0
        length = pymupdf.get_text_length(word, fontsize=13)
        d.gold["words"].append(
            dict(
                id=f"side.{i}",
                text=word,
                box=d.box((547, 150 - offset - length, 563, 150 - offset)),
                basis="NATIVE_PDF",
                categories=[],
            )
        )
    d.gold["lines"].append(dict(id="side", words=["side.0", "side.1"], order=False))
    transformer_claims(d, "grid", [("TX-6", "0.48"), ("TX-7", "0.6")])
    cases.append(d.data(source, 5, note="Horizontal grid beside a vertical instruction."))

    d = page("qualified-utility")
    d.label("title", "Utility Source Schedule", 30, 28)
    d.table(
        "grid",
        [
            ("Equipment", "3-Phase Fault Current (kA) (estimate)"),
            ("Utility Source UT-1", "22"),
            ("Utility Source UT-2", "25"),
        ],
        [25, 267, 570],
        [48, 84, 120, 156],
        factors=["qualified_header"],
    )
    for row in (1, 2):
        owner = f"eq{row}"
        d.claim(owner, f"grid-{row}-0", "UTILITY_SOURCE", tag=f"UT-{row}")
        d.claim(
            f"fault{row}",
            f"grid-{row}-1",
            "UTILITY_SOURCE",
            attribute="three_phase_fault_current",
            status="UNMAPPED",
            owner=owner,
        )
    cases.append(d.data(source, 6, note="An estimate qualifier is part of the printed header."))

    d = page("rotated-native", rotated=True)
    d.label("name", "2-Winding Transformer TX-9", 40, 65)
    d.label("value", "Secondary Voltage: 480 V", 40, 95)
    d.claim("eq", "name", tx, tag="TX-9")
    d.claim("v", "value", tx, attribute="secondary_voltage", value="0.48", unit="kV", owner="eq")
    cases.append(
        d.data(
            source,
            7,
            baseline="prose-native",
            note="Page rotation metadata turns authored vertical PDF text upright.",
        )
    )

    d = Design("scanned-schedule", size=(2000, 700))
    d.label("title", "2-Winding Transformer Schedule", 60, 30, size=52)
    d.table(
        "grid",
        [("Equipment", "Secondary (V)"), ("TX-1", "690"), ("TX-2", "480")],
        [48, 988, 1560],
        [118, 288, 458, 620],
        size=52,
    )
    transformer_claims(d, "grid", [("TX-1", "0.69"), ("TX-2", "0.48")])
    scan = doc.new_page(width=720, height=252)
    scan.insert_image(scan.rect, stream=png(d.image))
    cases.append(d.data(source, 8, ocr=True, note="Raster-only PDF with three aligned rows."))

    d = Design("hybrid-forced", size=(1200, 600))
    d.label("tag", "TX-3", 85, 270, size=42)
    d.label("reading", "690 V", 385, 270, size=42)
    mixed = doc.new_page(width=600, height=300)
    mixed.insert_image(mixed.rect, stream=png(d.image))
    d.page, d.draw = mixed, None
    d.width, d.height = 600, 300
    d.label("title", "Transformer inspection notes", 42, 53, size=18)
    # The invisible native text layer intentionally disagrees with the printed scan.
    d.label("hidden", "600 V", 192.5, 158, size=21, printed=False)
    cases.append(
        d.data(
            source,
            9,
            ocr=True,
            force=True,
            conflicts=[["hidden.0", "reading.0"]],
            note="Native annotation and disagreeing hidden OCR layer over embedded scan.",
        )
    )
    cases.append(
        dict(
            cases[-1],
            id="hybrid-auto",
            force_ocr=False,
            note="The same hybrid page with default OCR eligibility.",
        )
    )

    d = page("drawing-negative")
    d.segment((45, 90), (515, 90))
    d.segment((215, 90), (215, 215))
    d.segment((215, 215), (485, 215))
    d.label("title", "Single Line Diagram", 45, 40)
    d.label("label1", "Drawing revision B", 45, 69)
    d.label("label2", "Do not scale", 238, 170)
    cases.append(d.data(source, 10, note="Open drawing lines and notes do not form a table."))

    (EVALS / source).write_bytes(doc.tobytes(garbage=4, deflate=True, no_new_id=True))
    doc.close()
    return cases


def images():
    d = Design("transformer-nameplate", size=(1100, 480))
    nameplate(
        d,
        "2-Winding Transformer",
        "TX-12",
        "Secondary Voltage",
        "600 V",
        "TWO_WINDING_TRANSFORMER",
        "secondary_voltage",
        "0.6",
        "kV",
    )
    p = "spatial/v1/sources/transformer.png"
    (EVALS / p).write_bytes(png(d.image))
    yield d.data(p, ocr=True, baseline="prose-image", note="Clean image-only nameplate.")

    d = Design("breaker-degraded", size=(1100, 480))
    nameplate(
        d,
        "LV Breaker",
        "CB-12",
        "Interrupting Rating",
        "10.5 kA",
        "LV_BREAKER",
        "interrupting_rating",
        "10.5",
        "kA",
    )
    d.label("notation", "400 AF / 250 AT  35 mm²  ±5%", 60, 330, size=38)
    degraded = d.image.resize((330, 144), Image.Resampling.LANCZOS).convert("L")
    rng = random.Random(61)
    degraded.putdata(
        [max(0, min(255, 150 + gray // 3 + rng.randrange(-18, 19))) for gray in degraded.getdata()]
    )
    p = "spatial/v1/sources/breaker-degraded.png"
    (EVALS / p).write_bytes(png(degraded))
    yield d.data(
        p, ocr=True, note="Deterministic low-resolution noise challenges punctuation and units."
    )

    d = Design("oriented-tiff", size=(950, 400))
    nameplate(
        d,
        "2-Winding Transformer",
        "TX-15",
        "Secondary Voltage",
        "480 V",
        "TWO_WINDING_TRANSFORMER",
        "secondary_voltage",
        "0.48",
        "kV",
        size=38,
    )
    p = "spatial/v1/sources/oriented-nameplate.tiff"
    exif = Image.Exif()
    exif[274] = 6
    d.image.transpose(Image.Transpose.ROTATE_90).save(
        EVALS / p, compression="tiff_deflate", exif=exif
    )
    yield d.data(p, ocr=True, note="Physical raster is sideways and TIFF orientation is explicit.")


def main():
    cases = [positioned(), *authored_book(), *images()]
    for case in cases:
        data = (EVALS / case["source"]).read_bytes()
        case.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    corpus = dict(
        version="spatial-extraction-corpus-v1", provenance="SYNTHETIC_AUTHORED", cases=cases
    )
    (ROOT / "corpus.json").write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
