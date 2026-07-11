import platform
import pdfplumber
import pytesseract
from PIL import Image, ImageOps

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


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


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Improves OCR accuracy on dense lab-report tables:
    - upscales small images (Tesseract struggles with small text)
    - converts to grayscale
    - increases contrast via auto-contrast
    """

    # upscale if the image is on the smaller side
    if image.width < 1800:
        scale = 1800 / image.width
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)

    image = image.convert("L")          # grayscale
    image = ImageOps.autocontrast(image)

    return image


def extract_text_from_image(image_path: str):

    image = Image.open(image_path)
    processed = _preprocess_for_ocr(image)

    text = pytesseract.image_to_string(processed, config="--psm 6")

    # DEBUG: print what OCR actually saw, so we can diagnose extraction
    # issues from the backend terminal
    print("\n===== OCR EXTRACTED TEXT (first 500 chars) =====")
    print(text[:500])
    print("===== END OCR TEXT =====\n")

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