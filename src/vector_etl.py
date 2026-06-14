"""
ETL pipeline — Phase 1 of the Multi-Modal Enterprise Agent project.

Steps:
  1. Extract text from data/raw/*.pdf and *.htm
  2. Clean the text (remove repeated headers/footers, whitespace, artifacts)
  3. Semantic chunking (group sentences while they remain semantically close;
     split when similarity drops)
  4. Local embeddings with all-MiniLM-L6-v2 (HuggingFace, via sentence-transformers)
  5. Insert into Qdrant with JSON metadata (company_name, document_type,
     document_year, quarter, chunk_index)

Prerequisites:
  - Qdrant must be running: `docker-compose up -d`
  - pip install -r requirements.txt
"""

import os
import re
import json
import sys
import uuid
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from tqdm import tqdm

# Load .env from the project root (one level above src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

RAW_DIR = "data/raw"
METADATA_FILE = os.path.join(RAW_DIR, "metadata.json")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
COLLECTION_NAME = "bnp_reports"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"   # 384 dimensions, local, fast
EMBEDDING_DIM = 384

# Semantic chunking: cosine similarity threshold.
# If the similarity between two consecutive sentences falls BELOW this threshold,
# we consider the topic to have changed and split the chunk.
SIMILARITY_THRESHOLD = 0.55

# Size bounds (in characters) to avoid tiny or oversized chunks
MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 1800


# --------------------------------------------------------------------------
# Step 1: Text extraction
# --------------------------------------------------------------------------

def extract_text_from_pdf(filepath: str) -> str:
    """Extract raw text from a PDF, page by page."""
    full_text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text.append(text)
    return "\n".join(full_text)


def extract_text_from_html(filepath: str) -> str:
    """Extract raw text from an HTML file (SEC EDGAR reports)."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # Remove scripts/styles that would pollute the text
    for tag in soup(["script", "style"]):
        tag.decompose()

    return soup.get_text(separator="\n")


def extract_text(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext in (".htm", ".html"):
        return extract_text_from_html(filepath)
    else:
        raise ValueError(f"Unsupported format: {ext}")


# --------------------------------------------------------------------------
# Step 2: Text cleaning
# --------------------------------------------------------------------------

def clean_text(raw_text: str) -> str:
    """
    Clean the extracted raw text:
      - normalize multiple spaces and line breaks
      - remove very short / purely numeric lines
        (often page numbers or repeated headers)
      - remove control characters
    """
    # Normalize line endings (CRLF -> LF)
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        # Remove lines that are only page numbers
        # (for example: "12", "Page 12", "- 12 -")
        if re.fullmatch(r"[-–—\s]*(?:[Pp]age\s*)?\d{1,4}[-–—\s]*", stripped):
            continue

        # Remove very short lines without letters (often noise)
        if len(stripped) < 3 and not re.search(r"[A-Za-zÀ-ÿ]", stripped):
            continue

        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)

    # Reduce repeated spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Reduce repeated line breaks (maximum 2 consecutive)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# --------------------------------------------------------------------------
# Step 3: Semantic chunking
# --------------------------------------------------------------------------

def split_into_sentences(text: str) -> list[str]:
    """
    Split the text into sentences.
    A simple rule based on final punctuation + following uppercase,
    sufficient for French/English financial reports.
    """
    # Split first by paragraph (line breaks)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    sentences = []
    for para in paragraphs:
        # Split on ., !, ?, followed by a space + uppercase (or end of string)
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ü0-9])", para)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)

    return sentences


def semantic_chunking(
    text: str,
    embedder: SentenceTransformer,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_chars: int = MIN_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[str]:
    """
    Semantic chunking:
      1. Split the text into sentences
      2. Compute the embedding of each sentence
      3. Group consecutive sentences as long as their cosine similarity
         remains >= similarity_threshold
      4. Split the chunk when similarity drops, OR when the maximum size
         is reached
      5. Merge chunks that are too small with the next one
    """
    sentences = split_into_sentences(text)
    if not sentences:
        return []

    # Embed all sentences in one pass (efficient)
    embeddings = embedder.encode(sentences, normalize_embeddings=True)

    chunks = []
    current_chunk_sentences = [sentences[0]]
    current_chunk_len = len(sentences[0])

    for i in range(1, len(sentences)):
        # Cosine similarity = dot product (normalized vectors)
        sim = float(embeddings[i] @ embeddings[i - 1])

        sentence = sentences[i]
        sentence_len = len(sentence)

        would_exceed_max = (current_chunk_len + sentence_len) > max_chars

        if sim < similarity_threshold or would_exceed_max:
            # Semantic break (or chunk too large) -> close the current chunk
            chunks.append(" ".join(current_chunk_sentences))
            current_chunk_sentences = [sentence]
            current_chunk_len = sentence_len
        else:
            # Semantic continuity -> add the sentence to the current chunk
            current_chunk_sentences.append(sentence)
            current_chunk_len += sentence_len

    # Last chunk
    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))

    # Merge chunks that are too small with the next chunk
    merged_chunks = []
    buffer = ""
    for chunk in chunks:
        if buffer:
            buffer = buffer + " " + chunk
        else:
            buffer = chunk

        if len(buffer) >= min_chars:
            merged_chunks.append(buffer)
            buffer = ""

    if buffer:
        if merged_chunks:
            merged_chunks[-1] += " " + buffer
        else:
            merged_chunks.append(buffer)

    return merged_chunks


# --------------------------------------------------------------------------
# Step 4 + 5: Embeddings + Qdrant insertion
# --------------------------------------------------------------------------

def setup_qdrant_collection(client: QdrantClient):
    """Create (or recreate) the Qdrant collection with the correct dimension."""
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists -> deleting and recreating it.")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    print(f"Collection '{COLLECTION_NAME}' created (dim={EMBEDDING_DIM}, distance=COSINE).")


def process_document(
    filepath: str,
    doc_metadata: dict,
    embedder: SentenceTransformer,
) -> list[PointStruct]:
    """
    Process a full document:
      extraction -> cleaning -> semantic chunking -> embeddings -> PointStruct

    Returns the list of Qdrant points ready to be upserted.
    """
    print(f"\n--- Processing {doc_metadata['filename']} ---")

    raw_text = extract_text(filepath)
    print(f"  Raw text extracted: {len(raw_text)} characters")

    cleaned = clean_text(raw_text)
    print(f"  Cleaned text: {len(cleaned)} characters")

    chunks = semantic_chunking(cleaned, embedder)
    print(f"  Chunks generated: {len(chunks)}")

    if not chunks:
        print("  ⚠️ No chunk was generated, document ignored.")
        return []

    # Batch embeddings (faster than one-by-one)
    chunk_embeddings = embedder.encode(
        chunks, normalize_embeddings=True, show_progress_bar=False
    )

    points = []
    for idx, (chunk_text, embedding) in enumerate(zip(chunks, chunk_embeddings)):
        payload = {
            "text": chunk_text,
            "chunk_index": idx,
            "source_file": doc_metadata["filename"],
            "company_name": doc_metadata.get("company_name"),
            "document_type": doc_metadata.get("document_type"),
            "document_year": doc_metadata.get("document_year"),
            "quarter": doc_metadata.get("quarter"),
        }

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding.tolist(),
            payload=payload,
        )
        points.append(point)

    return points


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    # Allows passing an alternative metadata file as an argument,
    # for example: python src/etl_pipeline.py data/raw/metadata_test.json
    metadata_file = sys.argv[1] if len(sys.argv) > 1 else METADATA_FILE

    # Load the metadata generated by scrape_bnp_reports.py
    if not os.path.exists(metadata_file):
        raise FileNotFoundError(
            f"{metadata_file} not found. Run scrape_bnp_reports.py first."
        )

    with open(metadata_file, "r", encoding="utf-8") as f:
        documents_metadata = json.load(f)

    print(f"Metadata file used: {metadata_file}")
    print(f"{len(documents_metadata)} documents to process.")

    # Load the local embedding model (downloaded once and cached)
    print(f"\nChargement du modèle d'embedding '{EMBEDDING_MODEL_NAME}'...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # Connect to Qdrant (must be running via docker-compose up -d)
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    setup_qdrant_collection(client)

    total_points = 0

    for doc_meta in tqdm(documents_metadata, desc="Documents"):
        filepath = os.path.join(RAW_DIR, doc_meta["filename"])

        if not os.path.exists(filepath):
            print(f"\n⚠️ File not found, ignored: {filepath}")
            continue

        points = process_document(filepath, doc_meta, embedder)

        if points:
            # Batch insertion of 64 to keep memory usage reasonable
            batch_size = 64
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                client.upsert(collection_name=COLLECTION_NAME, points=batch)

            total_points += len(points)

    print(f"\n✅ Pipeline completed. {total_points} vectors inserted into '{COLLECTION_NAME}'.")
    print(f"Qdrant dashboard: {QDRANT_URL}/dashboard")


if __name__ == "__main__":
    main()