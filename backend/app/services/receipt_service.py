"""Generate a printable PDF for a completed Shoply order."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#102522")
MUTED = colors.HexColor("#586b63")
GOLD = colors.HexColor("#b78b54")
PAPER = colors.HexColor("#f8f5ef")


def _money(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f} EGP"


def _date(value) -> str:
    if not value:
        return "-"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Africa/Cairo")).strftime("%d %b %Y")


def render_receipt(order: dict, customer_name: str | None = None) -> bytes:
    """Use the order's saved price snapshot, never the current product price."""
    output = BytesIO()
    page_width, _ = A4
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=21 * mm, bottomMargin=22 * mm,
        title=f"Shoply receipt {order['id'][-8:]}", author="Shoply",
    )
    content_width = page_width - 40 * mm
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=14, textColor=INK)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=12, textColor=MUTED)
    brand = ParagraphStyle("brand", fontName="Times-Bold", fontSize=27, leading=31, textColor=INK)
    heading = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=INK)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    right_small = ParagraphStyle("right-small", parent=small, alignment=TA_RIGHT)

    story = []
    masthead = Table([[
        Paragraph("Shoply", brand),
        Paragraph("PAYMENT RECEIPT<br/><font color='#586b63'>Delivered order</font>", right),
    ]], colWidths=[content_width * .54, content_width * .46])
    masthead.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, GOLD),
    ]))
    story.extend([masthead, Spacer(1, 17)])

    info = Table([
        [Paragraph("ORDER NUMBER", heading), Paragraph("CUSTOMER", heading), Paragraph("DELIVERED", heading)],
        [Paragraph(escape(order["id"][-12:].upper()), body),
         Paragraph(escape(customer_name or "Shoply customer"), body),
         Paragraph(_date(order.get("delivered_at") or order.get("updated_at")), body)],
    ], colWidths=[content_width * .31, content_width * .39, content_width * .30])
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("TOPPADDING", (0, 0), (-1, 0), 12),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([info, Spacer(1, 24), Paragraph("Items purchased", brand), Spacer(1, 12)])

    rows = [["ITEM", "QTY", "UNIT PRICE", "AMOUNT"]]
    for item in order.get("items", []):
        quantity = int(item.get("qty", 0))
        unit_price = Decimal(str(item.get("unit_price", 0)))
        rows.append([
            Paragraph(escape(str(item.get("name") or "Product")), body),
            str(quantity), _money(unit_price), _money(unit_price * quantity),
        ])
    items = LongTable(
        rows, colWidths=[content_width * .46, content_width * .10, content_width * .21, content_width * .23],
        repeatRows=1, hAlign="LEFT",
    )
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 11),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 11),
        ("TOPPADDING", (0, 1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
        ("LINEBELOW", (0, 1), (-1, -1), .35, colors.HexColor("#d9dfd9")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.extend([items, Spacer(1, 18)])

    total_rows = [[Paragraph("Subtotal", small), Paragraph(_money(order.get("subtotal")), right_small)]]
    if Decimal(str(order.get("tax") or 0)):
        total_rows.append([Paragraph("Tax", small), Paragraph(_money(order["tax"]), right_small)])
    if Decimal(str(order.get("shipping_cost") or 0)):
        total_rows.append([Paragraph("Delivery", small), Paragraph(_money(order["shipping_cost"]), right_small)])
    total_rows.append([Paragraph("Total paid", heading), Paragraph(_money(order.get("total")), right)])
    totals = Table(total_rows, colWidths=[content_width * .75, content_width * .25], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -2), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 5),
        ("TOPPADDING", (0, -1), (-1, -1), 11),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("LINEABOVE", (0, -1), (-1, -1), 1, GOLD),
    ]))
    payment_method = "InstaPay" if order.get("payment_method") == "instapay" else "Confirmed payment"
    story.extend([totals, Spacer(1, 24), Paragraph(f"Payment: {payment_method} - confirmed by Shoply", body),
                  Spacer(1, 4), Paragraph("Thank you for shopping with us.", small)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d9dfd9"))
        canvas.line(20 * mm, 17 * mm, page_width - 20 * mm, 17 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 12 * mm, "SHOPLY  |  ORDER VIA WHATSAPP")
        canvas.drawRightString(page_width - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
