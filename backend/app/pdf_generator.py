from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

ORANGE = colors.HexColor("#f97316")
DARK = colors.HexColor("#111827")
GREY = colors.HexColor("#6b7280")
LIGHT_GREY = colors.HexColor("#f9fafb")
BORDER = colors.HexColor("#e5e7eb")

GENERATED_DIR = Path("/app/generated_quotes")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

LOGO_PATH = Path(__file__).parent / "assets" / "moveango-logo.png"

def money(amount: float) -> str:
    return f"R{amount:,.2f}".replace(",", " ")


def compact_address(address: str) -> str:
    """
    Customer-facing address formatter.

    Search/autocomplete can keep long addresses.
    This function only cleans display for the PDF.

    Goals:
    - Preserve street number if present.
    - Avoid duplicate street-only lines.
    - Display roughly:
      Street number + street + suburb
      City/Town
      Province
    """
    if not address:
        return ""

    parts = [p.strip() for p in address.split(",") if p.strip()]
    cleaned = []
    seen = set()

    for part in parts:
        lower = part.lower()

        if lower in {"south africa", "za"}:
            continue

        if part.isdigit() and len(part) in [4, 5]:
            continue

        if lower in seen:
            continue

        seen.add(lower)
        cleaned.append(part)

    province_candidates = [
        "Eastern Cape", "Western Cape", "Gauteng", "KwaZulu-Natal",
        "Free State", "Limpopo", "Mpumalanga", "North West", "Northern Cape"
    ]
    city_candidates = ["Gqeberha", "Port Elizabeth", "Kariega", "Uitenhage", "Despatch"]

    province = next((p for p in cleaned if p in province_candidates), None)
    city = next((p for p in cleaned if p in city_candidates), None)

    first = cleaned[0] if cleaned else address

    broad_terms = {
        "Nelson Mandela Bay Metropolitan Municipality",
        "Nelson Mandela Bay",
        "Sarah Baartman District Municipality",
    }

    # Pick suburb, but avoid street-only duplicate if first line already contains it.
    suburb = None
    first_lower = first.lower()
    for p in cleaned[1:]:
        if p == city or p == province or p in broad_terms:
            continue
        if p in city_candidates or p in province_candidates:
            continue

        # Avoid duplicate street line:
        # "24 Timothy Avenue Broadwood" + "Timothy Avenue"
        if p.lower() in first_lower:
            continue

        suburb = p
        break

    # If the first line has a street number and suburb is known,
    # combine them on the first line rather than creating duplicate lines.
    first_line = first
    if suburb and suburb.lower() not in first_line.lower():
        # Only append suburb when first line looks like a street address.
        if any(word in first_line.lower() for word in ["street", "road", "avenue", "drive", "crescent", "lane", "close", "way", "place", "st", "rd", "ave", "dr"]):
            first_line = f"{first_line}, {suburb}"
            suburb = None

    lines = []
    for value in [first_line, suburb, city, province]:
        if value and value not in lines:
            lines.append(value)

    if len(lines) < 2:
        lines = cleaned[:4]

    return "<br/>".join(lines[:4])

def generate_quote_pdf(quote: dict) -> str:
    quote_number = quote["quote_number"]
    filename = f"{quote_number}.pdf"
    output_path = GENERATED_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="QuoteTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=DARK,
        alignment=2,
        leading=22,
    ))

    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=DARK,
        spaceBefore=12,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontSize=9.5,
        textColor=DARK,
        leading=13,
    ))

    styles.add(ParagraphStyle(
        name="Muted",
        parent=styles["Normal"],
        fontSize=8,
        textColor=GREY,
        leading=10,
    ))

    styles.add(ParagraphStyle(
        name="Address",
        parent=styles["Normal"],
        fontSize=9,
        textColor=DARK,
        leading=12,
    ))

    story = []

    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=24 * mm, height=24 * mm)
    else:
        logo = Paragraph("<b>Moveango</b>", styles["Body"])

    brand_block = Table([
        [logo, Paragraph("<font size='18'><b>Moveango</b></font><br/><font color='#f97316'><b>Collect. Deliver. Move.</b></font>", styles["Body"])]
    ], colWidths=[28 * mm, 72 * mm])

    brand_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    quote_block = Paragraph(
        f"<b>QUOTATION</b><br/><font size='8' color='#6b7280'>Quote No: {quote_number}<br/>Date: {quote['quote_date']}<br/>Valid Until: {quote['valid_until']}</font>",
        styles["QuoteTitle"]
    )

    header = Table([[brand_block, quote_block]], colWidths=[105 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)

    story.append(Spacer(1, 5))
    orange_bar = Table([[""]], colWidths=[175 * mm], rowHeights=[1.4])
    orange_bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ORANGE)]))
    story.append(orange_bar)
    story.append(Spacer(1, 10))

    customer_rows = [
        ["Customer Name", quote["customer_name"]],
        ["Customer Phone", quote["customer_phone"]],
        ["Service Requested", quote["customer_service_label"]],
    ]

    customer_table = Table(customer_rows, colWidths=[42 * mm, 133 * mm])
    customer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(Paragraph("Customer Details", styles["SectionTitle"]))
    story.append(customer_table)

    pickup = compact_address(quote["pickup"])
    dropoff = compact_address(quote["dropoff"])

    address_table = Table([
        [
            Paragraph("<b>Collection Address</b><br/><br/>" + pickup, styles["Address"]),
            Paragraph("<b>Delivery Address</b><br/><br/>" + dropoff, styles["Address"]),
        ]
    ], colWidths=[86 * mm, 86 * mm])

    address_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("PADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(Paragraph("Collection & Delivery", styles["SectionTitle"]))
    story.append(address_table)

    item_description = quote["customer_service_label"]
    if quote.get("load_type"):
        item_description += f" - {quote['load_type']}"

    quote_rows = [
        ["Description", "Amount"],
        [item_description, money(quote["estimated_quote"])],
    ]

    quote_table = Table(quote_rows, colWidths=[125 * mm, 50 * mm])
    quote_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(Paragraph("Quotation Summary", styles["SectionTitle"]))
    story.append(quote_table)

    total_table = Table([
        ["Total Service Fee", money(quote["estimated_quote"])]
    ], colWidths=[125 * mm, 50 * mm])

    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(total_table)

    if quote.get("notes"):
        story.append(Paragraph("Notes", styles["SectionTitle"]))
        story.append(Paragraph(quote["notes"], styles["Body"]))

    terms = (
        "This quotation is based on the customer specifications provided at the time of quoting. "
        "The final booking remains subject to confirmation of item size, access conditions, timing, "
        "safe loading conditions and availability. This quotation is valid until the date shown above."
    )

    story.append(Paragraph("Terms", styles["SectionTitle"]))
    story.append(Paragraph(terms, styles["Muted"]))

    story.append(Spacer(1, 12))

    footer_table = Table([
        [
            Paragraph("<b>Moveango</b><br/>Smart Local Logistics<br/>Gqeberha & Surrounding Areas", styles["Muted"]),
            Paragraph("<b>Accept Quote</b><br/>WhatsApp: 081 710 8229<br/>Email: quotes@moveango.co.za", styles["Muted"]),
        ]
    ], colWidths=[88 * mm, 87 * mm])

    footer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(footer_table)

    doc.build(story)

    return f"/quotes/{filename}"
