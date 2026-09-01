"""A signed RFP bid, rendered as a Musanga-branded PDF.

The on-page confirmation is the record while the browser tab is open; this
is the record once it isn't. A transporter who signs on their phone at a
loading point wants something they can forward to their own accounts team
or keep on file - not a link that only means something inside Musanga's
platform.

reportlab is the only renderer that fits the deployment: pure Python, no
headless browser, no system library Vercel's Python runtime would need to
have installed. The look is the same restraint as the web pages - black,
white, no colour, generous margins - because a contract should look like
one.
"""

import io
import time

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, KeepTogether,
)

from . import agreements

PAGE_SIZE = A4
MARGIN = 22 * mm

_styles = getSampleStyleSheet()

BODY = ParagraphStyle(
    "musanga-body", parent=_styles["BodyText"],
    fontName="Helvetica", fontSize=9.5, leading=14, spaceAfter=6,
)
H1 = ParagraphStyle(
    "musanga-h1", parent=_styles["Title"],
    fontName="Helvetica-Bold", fontSize=18, leading=22,
    alignment=0, textColor=colors.black, spaceAfter=4,
)
H2 = ParagraphStyle(
    "musanga-h2", parent=_styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=11, leading=14,
    textColor=colors.black, spaceBefore=14, spaceAfter=6,
)
LABEL = ParagraphStyle(
    "musanga-label", parent=BODY,
    fontName="Helvetica-Bold", fontSize=8, leading=11,
    textColor=colors.HexColor("#666666"),
)
KICKER = ParagraphStyle(
    "musanga-kicker", parent=BODY,
    fontName="Helvetica", fontSize=9, leading=12,
    textColor=colors.HexColor("#666666"), spaceAfter=0,
)
KICKER_RIGHT = ParagraphStyle("musanga-kicker-right", parent=KICKER, alignment=TA_RIGHT)
CLAUSE = ParagraphStyle(
    "musanga-clause", parent=BODY, fontSize=8.6, leading=12.5, spaceAfter=5,
)
CLAUSE_HEAD = ParagraphStyle(
    "musanga-clause-head", parent=BODY,
    fontName="Helvetica-Bold", fontSize=9.5, leading=13,
    spaceBefore=8, spaceAfter=3,
)


def _header_footer(canvas, doc):
    canvas.saveState()
    # A solid black bar with the wordmark reversed out of it - the same
    # black-on-white mark the web pages use, just printed instead of screened.
    bar_h = 16 * mm
    canvas.setFillColor(colors.black)
    canvas.rect(0, PAGE_SIZE[1] - bar_h, PAGE_SIZE[0], bar_h, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(MARGIN, PAGE_SIZE[1] - bar_h + 5 * mm, "MUSANGA")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_SIZE[0] - MARGIN, PAGE_SIZE[1] - bar_h + 6.3 * mm,
                            "Request for prices and capacity")

    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, 12 * mm,
                       "%s · %s" % (agreements.COMPANY["name"], agreements.COMPANY["reg"]))
    canvas.drawRightString(PAGE_SIZE[0] - MARGIN, 12 * mm, "Page %d" % canvas.getPageNumber())
    canvas.restoreState()


def _doc():
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=26 * mm, bottomMargin=20 * mm,
        title="Musanga bid confirmation",
    )
    frame = Frame(MARGIN, 20 * mm, PAGE_SIZE[0] - 2 * MARGIN,
                   PAGE_SIZE[1] - 26 * mm - 20 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="musanga", frames=[frame], onPage=_header_footer)])
    return buf, doc


def _kv_table(rows):
    data = [[Paragraph(k, LABEL), Paragraph(v if v else "—", BODY)] for k, v in rows]
    t = Table(data, colWidths=[42 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e5e5")),
    ]))
    return t


def _terms_flowables(terms_body):
    out = []
    for block in terms_body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            out.append(Paragraph(block[3:].strip(), CLAUSE_HEAD))
            continue
        text = " ".join(line.strip() for line in block.splitlines()).strip()
        out.append(Paragraph(text.replace("&", "&amp;"), CLAUSE))
    return out


def render_bid_receipt(rfp, bid, invite):
    """PDF bytes for one signed bid. `rfp`, `bid`, `invite` are the same
    JSON-shaped dicts the API already returns to the ops and public pages -
    this reads them, it doesn't touch the database."""
    buf, doc = _doc()
    flow = []

    flow.append(Paragraph("Bid confirmation", H1))
    flow.append(Paragraph(
        "%s &nbsp;·&nbsp; %s" % (rfp["ref"], time.strftime(
            "%d %B %Y, %H:%M", time.gmtime(bid["created_at"]))), KICKER))
    flow.append(Spacer(1, 10 * mm))

    flow.append(Paragraph(
        "%s &rarr; %s" % (rfp["from_place"], rfp["to_place"]), H2))
    flow.append(_kv_table([
        ("Transporter", invite["carrier_name"]),
        ("Commodity", rfp["commodity"]),
        ("Equipment asked for", rfp["equipment"]),
        ("Loading window", " → ".join(
            filter(None, [rfp.get("loading_from"), rfp.get("loading_to")])) or "—"),
    ]))

    flow.append(Paragraph("What was bid", H2))
    flow.append(_kv_table([
        ("Rate", "%s / t" % bid["rate"]),
        ("Trucks committed", str(bid["trucks_offered"])),
        ("Tonnage", "%s t" % bid["capacity_tonnes"]),
        ("Vehicle type", bid.get("vehicle_type") or "—"),
        ("Available", " → ".join(
            filter(None, [bid.get("available_from"), bid.get("available_to")])) or "—"),
        ("Notes", bid.get("notes") or "—"),
    ]))

    plates = [t.get("plate") for t in (bid.get("trucks") or []) if t.get("plate")]
    if plates:
        flow.append(Paragraph("Plates on this bid", H2))
        flow.append(Paragraph(", ".join(plates), BODY))

    flow.append(Paragraph("Signature", H2))
    flow.append(_kv_table([
        ("Signed by", bid["signer_name"] + (", " + bid["signer_title"] if bid.get("signer_title") else "")),
        ("Email", bid.get("signer_email") or "—"),
        ("Signed", time.strftime("%d %B %Y, %H:%M UTC", time.gmtime(bid["created_at"]))),
        ("Terms hash", bid["terms_hash"]),
    ]))
    flow.append(Paragraph(
        "Submitting this bid on the Musanga platform is an electronic "
        "signature to the terms below, binding as a wet signature would be.",
        ParagraphStyle("note", parent=BODY, textColor=colors.HexColor("#666666"), fontSize=8.3)))

    flow.append(Spacer(1, 6 * mm))
    flow.append(KeepTogether([Paragraph("Terms this bid was signed against", H2)]))
    flow.extend(_terms_flowables(rfp["terms_body"]))

    doc.build(flow)
    return buf.getvalue()
