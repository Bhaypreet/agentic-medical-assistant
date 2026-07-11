import platform
import pdfplumber
import pytesseract
from PIL import Image

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# on Linux (Render), tesseract-ocr is installed via apt and is already on PATH


def extract_text_from_pdf(pdf_path: str):

    pages = []

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(pdf.pages, start=1):

            text = page.extract_text()

            pages.append({
                "page": page_number,
                "text": text if text else ""
            })

    return pages


def extract_text_from_image(image_path: str):

    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)

    return [{
        "page": 1,
        "text": text
    }]


def extract_report_pages(file_path: str):

    lower = file_path.lower()

    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_path)

    if lower.endswith((".png", ".jpg", ".jpeg")):
        return extract_text_from_image(file_path)

    raise ValueError(f"Unsupported file type: {file_path}")