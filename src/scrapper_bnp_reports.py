"""
Scrape the BNP Paribas reports and documentation page and download
12 of the most relevant documents for the project (URD, integrated
reports, financial statements, social report).

Each "document/..." page on invest.bnpparibas may contain either:
  - a direct PDF link (often the page itself is served as PDF)
  - or an external link to cdn-group.bnpparibas.com / reports.invest.bnpparibas

This script:
  1. Visits each document page
  2. Detects the Content-Type (direct PDF vs HTML with a PDF link)
  3. Downloads the PDF into data/raw/
  4. Generates a metadata.json file with document metadata
"""

import os
import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

OUTPUT_DIR = "data/raw"

# (filename, url, metadata)
DOCUMENTS = [
    ("bnp_urd_2025.pdf",
     "https://invest.bnpparibas/document/document-d-enregistrement-universel-et-rapport-financier-annuel-2025-pdf",
     {"company_name": "BNP Paribas", "document_type": "URD", "document_year": 2025, "quarter": None}),

    ("bnp_urd_amendement1_2025.pdf",
     "https://invest.bnpparibas/document/1er-amendement-au-document-d-enregistrement-universel-et-rapport-financier-annuel-2025",
     {"company_name": "BNP Paribas", "document_type": "URD_Amendement", "document_year": 2025, "quarter": None}),

    ("bnp_rapport_integre_2025.pdf",
     "https://invest.bnpparibas/document/rapport-integre-2025",
     {"company_name": "BNP Paribas", "document_type": "Rapport_Integre", "document_year": 2025, "quarter": None}),

    ("bnp_rapport_integre_2024.pdf",
     "https://invest.bnpparibas/document/rapport-integre-2024",
     {"company_name": "BNP Paribas", "document_type": "Rapport_Integre", "document_year": 2024, "quarter": None}),

    ("bnp_urd_amendement1_2024.pdf",
     "https://invest.bnpparibas/document/1er-amendement-au-document-denregistrement-universel-et-rapport-financier-annuel-2024",
     {"company_name": "BNP Paribas", "document_type": "URD_Amendement", "document_year": 2024, "quarter": None}),

    ("bnp_urd_amendement2_2024.pdf",
     "https://invest.bnpparibas/document/2eme-amendement-au-document-denregistrement-universel-et-rapport-financier-annuel-2024",
     {"company_name": "BNP Paribas", "document_type": "URD_Amendement", "document_year": 2024, "quarter": None}),

    ("bnp_urd_amendement3_2024.pdf",
     "https://invest.bnpparibas/document/3eme-amendement-au-document-denregistrement-universel-et-rapport-financier-annuel-2024",
     {"company_name": "BNP Paribas", "document_type": "URD_Amendement", "document_year": 2024, "quarter": None}),

    ("bnp_etats_financiers_q4_2025.pdf",
     "https://invest.bnpparibas/document/4t25-efna",
     {"company_name": "BNP Paribas", "document_type": "Etats_Financiers", "document_year": 2025, "quarter": "Q4"}),

    ("bnp_etats_financiers_q2_2025.pdf",
     "https://invest.bnpparibas/document/2t25-efna",
     {"company_name": "BNP Paribas", "document_type": "Etats_Financiers", "document_year": 2025, "quarter": "Q2"}),

    ("bnp_essentiel_2025.pdf",
     "https://invest.bnpparibas/document/lessentiel-2025",
     {"company_name": "BNP Paribas", "document_type": "Essentiel", "document_year": 2025, "quarter": None}),

    ("bnp_essentiel_2026.pdf",
     "https://invest.bnpparibas/document/l-essentiel-2026",
     {"company_name": "BNP Paribas", "document_type": "Essentiel", "document_year": 2026, "quarter": None}),

    ("bnp_bilan_social_2024.pdf",
     "https://invest.bnpparibas/document/bilan-social-2024",
     {"company_name": "BNP Paribas", "document_type": "Bilan_Social", "document_year": 2024, "quarter": None}),
]


def resolve_pdf_url(page_url: str) -> str:
    """
    Visit the document page. If the response is already a PDF, return page_url.
    Otherwise, parse the HTML to find the real PDF link (often on cdn-group.bnpparibas.com).
    """
    resp = requests.get(page_url, headers=HEADERS, timeout=30, allow_redirects=True)
    content_type = resp.headers.get("Content-Type", "")

    if "pdf" in content_type.lower():
        return resp.url  # already a PDF (follows redirects)

    # Otherwise, parse the HTML to find a .pdf link
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            if href.startswith("http"):
                return href
            return "https://invest.bnpparibas" + href

    # Fallback : chercher un pattern PDF dans le HTML brut (cdn-group)
    match = re.search(r'https://cdn-group\.bnpparibas\.com[^\s"\']+\.pdf', resp.text)
    if match:
        return match.group(0)

    return None


def download_documents():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    metadata_records = []

    for filename, page_url, meta in DOCUMENTS:
        print(f"\n--- {filename} ---")
        print(f"Resolving PDF URL from: {page_url}")

        try:
            pdf_url = resolve_pdf_url(page_url)
        except Exception as e:
            print(f"  ❌ Resolution error: {e}")
            continue

        if not pdf_url:
            print("  ❌ No PDF link found on the page.")
            continue

        print(f"  → PDF found: {pdf_url}")

        try:
            pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
            pdf_resp.raise_for_status()
        except Exception as e:
            print(f"  ❌ Download error: {e}")
            continue

        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(pdf_resp.content)

        size_mb = len(pdf_resp.content) / (1024 * 1024)
        print(f"  ✅ Downloaded ({size_mb:.2f} MB)")

        record = {"filename": filename, "source_url": pdf_url, **meta}
        metadata_records.append(record)

    # Save metadata for Phase 1 (chunking + embeddings)
    meta_path = os.path.join(OUTPUT_DIR, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_records, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Completed. {len(metadata_records)}/{len(DOCUMENTS)} documents downloaded.")
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    download_documents()