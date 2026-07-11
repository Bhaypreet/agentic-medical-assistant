import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text from a PDF report.

    Args:
        pdf_path (str): Path to the uploaded PDF.

    Returns:
        str: Extracted text from all pages.
    """

    extracted_text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                text = page.extract_text()

                if text:
                    extracted_text += text + "\n"

    except Exception as e:
        raise Exception(f"Error reading PDF: {e}")

    return extracted_text