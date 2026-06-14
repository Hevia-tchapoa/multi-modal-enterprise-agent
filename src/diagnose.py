"""
Quick diagnostic — tests each component independently, WITHOUT calling the
Gemini API (so no quota is consumed).

Usage: python src/diagnose.py
"""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)  # force the working directory to the project root

print("=" * 60)
print("1. .env check")
print("=" * 60)
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

api_key = os.environ.get("GOOGLE_API_KEY")
if api_key:
    print(f"✅ GOOGLE_API_KEY found (length={len(api_key)})")
else:
    print("❌ GOOGLE_API_KEY missing")

print()
print("=" * 60)
print("2. SQLite check")
print("=" * 60)

db_path = "data/finances.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"✅ {db_path} exists. Tables: {tables}")
    conn.close()
else:
    print(f"❌ {db_path} not found. Run: python src/create_sqlite_db.py")

print()
print("=" * 60)
print("3. Qdrant check")
print("=" * 60)

try:
    from qdrant_client import QdrantClient
    QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    print(f"✅ Qdrant is reachable at {QDRANT_URL}. Collections: {names}")

    if "bnp_reports" in names:
        info = client.get_collection("bnp_reports")
        print(f"   -> bnp_reports: {info.points_count} points")
    else:
        print("⚠️  Collection 'bnp_reports' missing — run the ETL pipeline")
except Exception as e:
    print(f"❌ Qdrant error: {e}")

print()
print("=" * 60)
print("4. SentenceTransformer check (local embeddings)")
print("=" * 60)

try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    vec = model.encode("test")
    print(f"✅ Embedding model loaded. Vector dimension: {len(vec)}")
except Exception as e:
    print(f"❌ Embedding error: {e}")

print()
print("=" * 60)
print("5. Import check for tools.py / agent.py (without LLM calls)")
print("=" * 60)

try:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from tools import execute_sql
    print("✅ tools.py imported without error")

    # Test execute_sql directly (no LLM call)
    result = execute_sql.invoke("SELECT * FROM annual_results")
    print(f"✅ execute_sql works. Result (excerpt):\n{result[:300]}")
except Exception as e:
    import traceback
    print(f"❌ tools.py error: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("Diagnostic completed.")
print("=" * 60)