import re
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)


# Characters that Helvetica (PDF's default font) can't render show up as
# black boxes ("■"). We normalize them to safe ASCII equivalents instead
# of needing to bundle a custom Unicode font.
_CHAR_REPLACEMENTS = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2212": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u00a0": " ", "\u2192": "->", "\u2190": "<-",
}

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F0FF"
    "]+",
    flags=re.UNICODE
)


def _sanitize(text: str) -> str:

    for bad, good in _CHAR_REPLACEMENTS.items():
        text = text.replace(bad, good)

    text = _EMOJI_PATTERN.sub("", text)

    return text.strip()


def _markdown_bold_to_html(text: str) -> str:
    # **bold** -> <b>bold</b>  (reportlab's Paragraph understands basic <b> tags)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _is_heading(line: str) -> bool:

    stripped = line.strip().strip("*").strip()

    if stripped.startswith("#"):
        return True

    # short, title-like lines ending with ":" (e.g. "Overall Summary:")
    if len(stripped) < 40 and stripped.endswith(":") and not stripped.startswith("-"):
        return True

    return False


def generate_report_pdf(summary_text: str, analysis: list) -> bytes:

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0f766e")
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#0f766e"),
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        leading=15,
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=14
    )

    elements = [
        Paragraph("AI Medical Report Summary", title_style),
        Spacer(1, 16),
    ]

    for raw_line in summary_text.split("\n"):

        line = raw_line.strip()

        if not line:
            continue

        line = _sanitize(line)
        line = _markdown_bold_to_html(line)

        if _is_heading(line):
            clean_heading = line.lstrip("#").strip().rstrip(":")
            elements.append(Paragraph(clean_heading, heading_style))
            continue

        if line.startswith(("-", "*", "\u2022")):
            bullet_text = line.lstrip("-*\u2022").strip()
            elements.append(Paragraph(f"\u2022 {bullet_text}", bullet_style))
            continue

        elements.append(Paragraph(line, body_style))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Detailed Lab Values", heading_style))
    elements.append(Spacer(1, 8))

    for section in analysis:

        elements.append(Paragraph(
            _sanitize(section.get("report_type", "Report")),
            styles["Heading3"]
        ))

        table_data = [["Parameter", "Value", "Unit", "Status"]]

        for name, info in section.get("parameters", {}).items():
            table_data.append([
                _sanitize(str(name)),
                _sanitize(str(info.get("value", "-"))),
                _sanitize(str(info.get("unit", ""))),
                _sanitize(str(info.get("status", "")))
            ])

        table = Table(table_data, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdfa")]),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 14))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "This report is AI-generated and for informational purposes only. "
        "It does not replace professional medical advice.",
        styles["Italic"]
    ))

    doc.build(elements)

    buffer.seek(0)
    return buffer.read()