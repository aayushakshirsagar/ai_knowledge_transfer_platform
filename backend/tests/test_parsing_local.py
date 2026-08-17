from app.ingestion.parsing import parse_document


result = parse_document(
    file_path="tests/test_documents/architecture.pdf",
    mime_type="application/pdf",
)

print("\n" + "=" * 70)
print("PARSED DOCUMENT")
print("=" * 70)

for index, section in enumerate(result.sections, start=1):
    print(f"\nSECTION {index}")
    print(f"TYPE: {section.type}")
    print(f"CONTENT:\n{section.content}")
    print(f"METADATA: {section.metadata}")

