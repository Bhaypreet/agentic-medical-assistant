from app.report.parser import extract_text_from_pdf
from app.report.extractor import extract_report_information


if __name__ == "__main__":

    pdf_path = input("Enter PDF path: ")

    pages = extract_text_from_pdf(pdf_path)

    print(f"Total Pages: {len(pages)}")

    # First page only
    first_page = pages[0]["text"]

    print("\n========== PAGE 1 ==========\n")
    print(first_page)

    print("\n========== LLM OUTPUT ==========\n")

    result = extract_report_information(first_page)

    print(result)