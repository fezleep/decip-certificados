from __future__ import annotations

import io
import re
from collections import deque
from datetime import date
from decimal import Decimal
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from reportlab.lib.utils import ImageReader

from ..config import BASE_DIR
from ..validation import clean

PAGE = landscape(A4)
GREEN = colors.HexColor("#00594F")
ORANGE = colors.HexColor("#FF5A0A")
TEXT = colors.HexColor("#444444")
WAVE = colors.HexColor("#ECF1F0")
REFERENCE = BASE_DIR / "assets" / "institutional" / "modelo-decip-referencia.jpeg"
MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def safe_filename(name: str) -> str:
    value = re.sub(r"[^\w\-. ]+", "", clean(name), flags=re.UNICODE).strip().replace(" ", "_")
    return value[:80] or "participante"


def br_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return parsed.strftime("%d/%m/%Y")


def long_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day:02d} de {MONTHS[parsed.month - 1]} de {parsed.year}"


def fmt_hours(value) -> str:
    number = Decimal(str(value).replace(",", "."))
    return f"{number.normalize():f}".replace(".", ",")


def _crop_reference(box: tuple[int, int, int, int], remove: str = "") -> io.BytesIO:
    image = Image.open(REFERENCE).convert("RGBA").crop(box)
    pixels = image.load()
    def background(r, g, b):
        if remove == "light": return min(r, g, b) > 175 and max(r, g, b) - min(r, g, b) < 45
        return r < 55 and 35 < g < 135 and b < 125
    # Remove só o fundo conectado às bordas. Assim branco/verde internos da
    # própria marca continuam intactos, mesmo com a compressão JPEG da referência.
    queue = deque()
    seen = set()
    for x in range(image.width): queue.extend(((x, 0), (x, image.height - 1)))
    for y in range(image.height): queue.extend(((0, y), (image.width - 1, y)))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or x < 0 or y < 0 or x >= image.width or y >= image.height: continue
        seen.add((x, y)); r, g, b, _ = pixels[x, y]
        if not background(r, g, b): continue
        pixels[x, y] = (r, g, b, 0)
        queue.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def _draw_waves(c: Canvas):
    c.setStrokeColor(WAVE)
    c.setLineWidth(1.4 * mm)
    c.setLineCap(1)
    width, height = PAGE
    amplitude, period = 5.5 * mm, 68 * mm
    y = 15 * mm
    while y < height - 5 * mm:
        path = c.beginPath()
        path.moveTo(-period, y)
        x = -period
        while x < width + period:
            path.curveTo(x + period * .25, y + amplitude, x + period * .25, y + amplitude, x + period * .5, y)
            path.curveTo(x + period * .75, y - amplitude, x + period * .75, y - amplitude, x + period, y)
            x += period
        c.drawPath(path)
        y += 10.5 * mm


def _paragraph(c: Canvas, text: str, x: float, y_top: float, width: float, height: float, size=11, leading=14, color=TEXT, bold=False):
    style = ParagraphStyle(
        "certificate", fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading, textColor=color, alignment=TA_CENTER,
        splitLongWords=True, allowWidows=0, allowOrphans=0,
    )
    paragraph = Paragraph(text, style)
    _, used = paragraph.wrap(width, height)
    paragraph.drawOn(c, x, y_top - used)
    return used


def _fit_center(c: Canvas, text: str, y: float, max_width: float, initial=22, minimum=12, font="Helvetica"):
    size = initial
    while size > minimum and stringWidth(text, font, size) > max_width:
        size -= .5
    c.setFont(font, size)
    c.setFillColor(GREEN)
    c.drawCentredString(PAGE[0] / 2, y, text)


def _draw_background(c: Canvas):
    width, height = PAGE
    c.setFillColor(colors.HexColor("#FEFEFD"))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    _draw_waves(c)
    c.setFillColor(colors.Color(0.82, 0.88, 0.87, alpha=.35))
    c.circle(5 * mm, 143 * mm, 48 * mm, fill=1, stroke=0)
    c.circle(11 * mm, 112 * mm, 27 * mm, fill=1, stroke=0)
    c.circle(2 * mm, 72 * mm, 22 * mm, fill=1, stroke=0)
    c.setFillColor(GREEN)
    p = c.beginPath(); p.moveTo(176*mm, 0); p.lineTo(width, 0); p.lineTo(width, 72*mm); p.close(); c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    p = c.beginPath(); p.moveTo(0, 0); p.lineTo(218*mm, 0); p.lineTo(0, 38*mm); p.close(); c.drawPath(p, fill=1, stroke=0)
    p = c.beginPath(); p.moveTo(0, 3*mm); p.lineTo(0, 32*mm); p.lineTo(255*mm, 0); p.lineTo(228*mm, 0); p.close(); c.drawPath(p, fill=1, stroke=0)
    c.setStrokeColor(colors.white); c.setLineWidth(3*mm); c.line(0, 36*mm, 213*mm, 1*mm)
    c.setStrokeColor(ORANGE); c.setLineWidth(3.6*mm); c.line(0, 41*mm, 247*mm, 0)
    c.setStrokeColor(ORANGE); c.setLineWidth(3.5*mm); c.rect(1.8*mm, 1.8*mm, width-3.6*mm, height-3.6*mm, fill=0, stroke=1)


def _draw_brand(c: Canvas):
    if REFERENCE.exists():
        # Marca e selo vêm da referência fornecida; nenhum símbolo é redesenhado.
        logo = _crop_reference((515, 35, 1080, 250), "light")
        c.drawImage(ImageReader(logo), 98*mm, 166*mm, width=101*mm, height=38.5*mm, preserveAspectRatio=True, mask="auto")
        seal = _crop_reference((1368, 875, 1587, 1097), "green")
        c.drawImage(ImageReader(seal), 258*mm, 12*mm, width=34*mm, height=34*mm, preserveAspectRatio=True, mask="auto")


def generate_pdf(data: dict, participant: dict, code: str, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(data)
    merged.update({k: v for k, v in participant.get("individual", {}).items() if clean(v)})
    c = Canvas(str(destination), pagesize=PAGE, pageCompression=1)
    c.setTitle(f"Certificado de Voluntariado - {participant['name']}")
    c.setAuthor("Instituto DECIP")
    _draw_background(c)
    _draw_brand(c)
    width, height = PAGE
    c.setFillColor(GREEN); c.setFont("Helvetica", 26)
    c.drawCentredString(width/2, 153*mm, "CERTIFICADO DE VOLUNTARIADO")
    c.setFont("Helvetica", 14); c.drawCentredString(width/2, 143*mm, "Certificamos que")
    _fit_center(c, participant["name"], 128*mm, 190*mm, initial=25, minimum=14)
    role = clean(merged.get("role"))
    paragraph = (
        f"Atuou voluntariamente junto ao Instituto DECIP, exercendo a função de <b>{role}</b>, "
        f"no período de <b>{br_date(merged['start_date'])}</b> a <b>{br_date(merged['end_date'])}</b>, "
        f"totalizando <b>{fmt_hours(merged['hours'])} horas</b> de atividade voluntária."
    )
    _paragraph(c, paragraph, 29*mm, 117*mm, 239*mm, 22*mm, size=10.5, leading=14)
    activities = clean(merged.get("activities"))
    activity_size = 9.7 if len(activities) < 220 else 8.6
    _paragraph(c, f"<b>ATIVIDADES DESENVOLVIDAS:</b> {activities}", 31*mm, 95*mm, 235*mm, 20*mm, size=activity_size, leading=12)
    _paragraph(c, "Durante o período de voluntariado, sua atuação contribuiu para o desenvolvimento das atividades, projetos<br/>e iniciativas institucionais do Instituto DECIP.", 28*mm, 76*mm, 241*mm, 16*mm, size=10.2, leading=13)
    _paragraph(c, "Este certificado é emitido como registro da atividade voluntária prestada à instituição.", 35*mm, 59*mm, 227*mm, 10*mm, size=10.2, leading=12)
    c.setFont("Helvetica", 10.5); c.setFillColor(TEXT)
    c.drawCentredString(width/2, 49*mm, f"{clean(merged['issue_city'])}, {long_date(merged['issue_date'])}")
    # Assinaturas: imagens opcionais ficam sobre a linha, sem alterar o fluxo.
    for idx, center in ((1, 91*mm), (2, 203*mm)):
        signature = clean(merged.get(f"signer{idx}_signature"))
        if signature and Path(signature).exists():
            c.drawImage(signature, center-24*mm, 42*mm, width=48*mm, height=15*mm, preserveAspectRatio=True, mask="auto")
        c.setStrokeColor(GREEN); c.setLineWidth(.35*mm); c.line(center-36*mm, 39*mm, center+36*mm, 39*mm)
        name = clean(merged.get(f"signer{idx}_name"))
        role_text = clean(merged.get(f"signer{idx}_role"))
        c.setFillColor(TEXT); c.setFont("Helvetica-Bold", 8.8); c.drawCentredString(center, 34.2*mm, name.upper())
        c.setFont("Helvetica", 8.2); c.drawCentredString(center, 30.6*mm, role_text.upper())
        c.drawCentredString(center, 27.1*mm, "INSTITUTO DECIP")
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 8.3)
    c.circle(10.5*mm, 25.2*mm, 2.2*mm, fill=0, stroke=1)
    c.line(8.3*mm, 25.2*mm, 12.7*mm, 25.2*mm)
    c.drawString(15*mm, 24*mm, "WWW.DECIP.ORG.BR")
    c.rect(8.3*mm, 16.2*mm, 4.5*mm, 3.2*mm, fill=0, stroke=1)
    c.drawString(15*mm, 16.5*mm, "CONTATO@DECIP.ORG.BR")
    c.setFont("Helvetica", 7); c.drawString(13*mm, 9.5*mm, "CÓDIGO DE VALIDAÇÃO:")
    c.setFont("Helvetica-Bold", 10); c.drawString(13*mm, 5.2*mm, code)
    c.showPage(); c.save()
    return destination
