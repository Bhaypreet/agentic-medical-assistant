from app.report.extractor import extract_report_information
from app.report.analyzer import analyze_report
from app.report.parser import extract_text_from_pdf


pdf_path = input("Enter PDF Path: ")

pages = extract_text_from_pdf(pdf_path)

first_page = pages[0]["text"]

report = extract_report_information(first_page)

# If extractor returns string, convert it
import json

report = json.loads(report)

analysis = analyze_report(report)

print("\n========== ANALYSIS ==========\n")

print(analysis)