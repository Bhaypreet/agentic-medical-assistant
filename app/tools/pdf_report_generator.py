import re
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_CHAR_REPLACEMENTS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u00a0": " ",
    "\u2192": "->",
    "\u2190": "<-",
}

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f000-\U0001f0ff"
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "\U0000fe00-\U0000fe0f"  # variation selectors - left behind by the
    "\U0000200d"  # ranges above, and ZWJ joins emoji sequences
    "\U000020e3"  # combining enclosing keycap
    "]+",
    flags=re.UNICODE,
)


def _sanitize(text: str) -> str:

    for bad, good in _CHAR_REPLACEMENTS.items():
        text = text.replace(bad, good)

    text = _EMOJI_PATTERN.sub("", text)

    # neutralize ANY raw HTML/XML-like tags the LLM might have written
    # (e.g. stray "<br>" inside a markdown table cell) - ReportLab's
    # Paragraph parser treats these as real tags and crashes if they're
    # malformed. Escaping here means our OWN <b> tags (added later) are
    # the only real tags that ever reach ReportLab.
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    # markdown table rows (LLM sometimes writes "| Diet | tips |") don't
    # render as tables here - convert pipes into a readable dash-separated line
    if text.count("|") >= 2:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        text = " - ".join(parts)

    return text.strip()


def _markdown_bold_to_html(text: str) -> str:
    # applied AFTER _sanitize, so these are the only real tags ReportLab sees
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _is_heading(line: str) -> bool:

    stripped = line.strip().strip("*").strip()

    if stripped.startswith("#"):
        return True

    return len(stripped) < 40 and stripped.endswith(":") and not stripped.startswith("-")


_STATUS_COLOURS = {
    "High": colors.HexColor("#b91c1c"),
    "Low": colors.HexColor("#b45309"),
    "Borderline": colors.HexColor("#c2410c"),
    "Unknown": colors.HexColor("#6b7280"),
}


def _append_footer(elements, styles) -> None:
    elements.append(Spacer(1, 20))
    elements.append(
        Paragraph(
            "This report is AI-generated and for informational purposes only. "
            "It does not replace professional medical advice. A value marked "
            "'Unknown' could not be interpreted and is not a statement that it is normal.",
            styles["Italic"],
        )
    )


def generate_report_pdf(summary_text: str, analysis: list) -> bytes:

    summary_text = summary_text or "No summary available."
    analysis = analysis or []

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Title"], textColor=colors.HexColor("#0f766e")
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#0f766e"),
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle("Body", parent=styles["Normal"], leading=15, spaceAfter=4)

    bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=14)

    elements = [
        Paragraph("AI Medical Report Summary", title_style),
        Spacer(1, 16),
    ]

    for raw_line in summary_text.split("\n"):
        line = raw_line.strip()

        if not line:
            continue

        line = _sanitize(line)

        if not line:
            continue

        line = _markdown_bold_to_html(line)

        try:
            if _is_heading(line):
                clean_heading = line.lstrip("#").strip().rstrip(":")
                elements.append(Paragraph(clean_heading, heading_style))
                continue

            if line.startswith(("-", "*", "\u2022")):
                bullet_text = line.lstrip("-*\u2022").strip()
                elements.append(Paragraph(f"\u2022 {bullet_text}", bullet_style))
                continue

            elements.append(Paragraph(line, body_style))

        except Exception:
            # last-resort safety net: never let one bad line crash the
            # whole PDF - fall back to fully plain, tag-free text
            plain = re.sub(r"<[^>]*>", "", line)
            elements.append(Paragraph(plain, body_style))

    if not analysis:
        elements.append(Spacer(1, 20))
        elements.append(
            Paragraph(
                "No structured laboratory values could be extracted from the uploaded file.",
                body_style,
            )
        )
        _append_footer(elements, styles)
        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Detailed Lab Values", heading_style))
    elements.append(Spacer(1, 8))

    unknown_total = 0

    for section in analysis:
        elements.append(
            Paragraph(_sanitize(section.get("report_type", "Report")), styles["Heading3"])
        )

        table_data = [["Parameter", "Value", "Unit", "Status"]]
        status_styles = []

        for row_index, (name, info) in enumerate(section.get("parameters", {}).items(), start=1):
            if not isinstance(info, dict):
                continue

            status = str(info.get("status", ""))

            table_data.append(
                [
                    _sanitize(str(name)),
                    _sanitize(str(info.get("value", "-"))),
                    _sanitize(str(info.get("unit", ""))),
                    _sanitize(status),
                ]
            )

            colour = _STATUS_COLOURS.get(status)

            if colour:
                status_styles.append(("TEXTCOLOR", (3, row_index), (3, row_index), colour))

            if status == "Unknown":
                unknown_total += 1

        table = Table(table_data, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f0fdfa")],
                    ),
                    *status_styles,
                ]
            )
        )

        elements.append(table)
        elements.append(Spacer(1, 14))

    if unknown_total:
        elements.append(
            Paragraph(
                f"<b>{unknown_total} value(s) are marked Unknown.</b> These could not be "
                "interpreted automatically and must be confirmed with your clinician. "
                "They are not a statement that the value is normal.",
                body_style,
            )
        )
        elements.append(Spacer(1, 10))

    _append_footer(elements, styles)

    doc.build(elements)

    buffer.seek(0)
    return buffer.read()
