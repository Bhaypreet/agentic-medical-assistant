from tools.severity_classifier import (
    classify_severity,
    severity_label
)

from rag.chain import medical_rag

query = input("Enter symptom: ")

result = classify_severity(query)

severity = result["severity"]

print("\nDetected Severity:")
print(severity_label(severity))

if severity <= 2:

    print("\nProceeding to Medical RAG...\n")

    answer = medical_rag(query)

    print(answer)

else:

    print("\nYour symptoms may require professional medical attention.")
    print("Please consider visiting a nearby doctor or hospital.")