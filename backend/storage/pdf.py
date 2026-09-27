"""Small government-style PDF generator for contracts and certificates."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def render_pdf(title, lines, subtitle=""):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def header():
        c.setFillColorRGB(1, 0.6, 0.2)
        c.rect(0, height - 4 * mm, width, 1.4 * mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, height - 5.6 * mm, width, 1.6 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0.075, 0.345, 0.03)
        c.rect(0, height - 7 * mm, width, 1.4 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0.043, 0.122, 0.227)
        c.rect(0, height - 28 * mm, width, 21 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0.788, 0.635, 0.153)
        c.setFont("Times-Bold", 11)
        c.drawString(18 * mm, height - 16 * mm, "PRAVAH")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Times-Bold", 13)
        c.drawString(42 * mm, height - 16 * mm, title[:90])
        c.setFont("Times-Roman", 8)
        c.setFillColorRGB(0.9, 0.86, 0.7)
        c.drawString(42 * mm, height - 21 * mm, (subtitle or "Innovation Procurement Cell  ·  Decision-support prototype")[:110])

    header()
    y = height - 38 * mm
    c.setFillColorRGB(0.1, 0.12, 0.16)
    c.setFont("Times-Roman", 10)
    for raw in lines:
        text = str(raw)
        if text.startswith("# "):
            y -= 4 * mm
            c.setFont("Times-Bold", 12)
            c.setFillColorRGB(0.043, 0.122, 0.227)
            c.drawString(18 * mm, y, text[2:][:100])
            y -= 2 * mm
            c.setStrokeColorRGB(0.788, 0.635, 0.153)
            c.setLineWidth(0.6)
            c.line(18 * mm, y, width - 18 * mm, y)
            y -= 6 * mm
            c.setFont("Times-Roman", 10)
            c.setFillColorRGB(0.1, 0.12, 0.16)
            continue
        if not text.strip():
            y -= 3 * mm
            continue
        while text:
            if y < 20 * mm:
                c.showPage()
                header()
                y = height - 38 * mm
                c.setFillColorRGB(0.1, 0.12, 0.16)
                c.setFont("Times-Roman", 10)
            chunk = text[:95]
            if len(text) > 95:
                cut = chunk.rfind(" ")
                if cut > 40:
                    chunk = text[:cut]
            c.drawString(18 * mm, y, chunk)
            text = text[len(chunk) :].lstrip()
            y -= 5 * mm
    c.setFont("Times-Italic", 8)
    c.setFillColorRGB(0.35, 0.4, 0.45)
    c.drawString(18 * mm, 12 * mm, "Final award rests with the competent government authority. AI outputs are decision-support only.")
    c.save()
    return buf.getvalue()
