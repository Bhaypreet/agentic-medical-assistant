from app.report.section_detector import detect_report_type

sample = """
Complete Blood Count

Hemoglobin

Platelet Count
"""

print(detect_report_type(sample))