from app.tools.report_parser import extract_text_from_pdf


if __name__ == "__main__":

    pdf_path = input("Enter PDF path: ")

    extracted_text = extract_text_from_pdf(pdf_path)

    print("\n========== EXTRACTED TEXT ==========\n")

    print(extracted_text)