"""
Creates a reduced metadata.json file (2 lightweight documents) to test the
ETL pipeline quickly before processing all 12 documents.

Usage:
    python src/make_test_metadata.py

Then, to run the ETL on this subset, temporarily update METADATA_FILE in
vector_etl.py (or add a CLI argument if you want to extend it).
"""

import json
import os

FULL_METADATA = "data/raw/metadata.json"
TEST_METADATA = "data/raw/metadata_test.json"

# Choose 2 short documents for a quick test
# (avoid bnp_urd_2025.pdf because it is about 930 pages)
TEST_FILENAMES = [
    "bnp_essentiel_2025.pdf",
    "bnp_essentiel_2026.pdf",
]


def main():
    with open(FULL_METADATA, "r", encoding="utf-8") as f:
        all_docs = json.load(f)

    test_docs = [doc for doc in all_docs if doc["filename"] in TEST_FILENAMES]

    if not test_docs:
        print("⚠️ No matching document found. Available documents:")
        for doc in all_docs:
            print(f"  - {doc['filename']}")
        return

    with open(TEST_METADATA, "w", encoding="utf-8") as f:
        json.dump(test_docs, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(test_docs)} documents selected for the test:")
    for doc in test_docs:
        print(f"  - {doc['filename']}")
    print(f"\nFile created: {TEST_METADATA}")


if __name__ == "__main__":
    main()