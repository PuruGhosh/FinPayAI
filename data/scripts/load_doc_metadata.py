"""
Parses YAML frontmatter from each policy markdown file and loads it into
the doc_metadata table. This same frontmatter is what you'll use as
ChromaDB chunk metadata at ingestion time -- keeping one source of truth.
"""
import sqlite3
import re
import glob
from pathlib import Path
import yaml

DATA_DIR = Path(__file__).resolve().parents[1]
DB_PATH = DATA_DIR / "db" / "finpay_poc.db"
POLICY_DIR = DATA_DIR / "policies"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
# Rebuild the audit mirror so it matches the current policy frontmatter.
cur.execute("DELETE FROM doc_metadata")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

rows = []
for path in sorted(POLICY_DIR.glob("*.md")):
    # Store the same visibility metadata later used by Chroma retrieval.
    with path.open(encoding="utf-8") as f:
        content = f.read()
    m = FRONTMATTER_RE.match(content)
    if not m:
        print(f"WARNING: no frontmatter in {path}")
        continue
    meta = yaml.safe_load(m.group(1))
    file_name = path.name
    rows.append((
        meta.get("doc_id"), file_name, meta.get("doc_type"),
        meta.get("visibility"), meta.get("department_owner"), meta.get("title"),
    ))

cur.executemany("""
    INSERT INTO doc_metadata (doc_id, file_name, doc_type, visibility, department_owner, title)
    VALUES (?,?,?,?,?,?)
""", rows)
conn.commit()

print(f"Loaded {len(rows)} documents into doc_metadata:\n")
for r in cur.execute("SELECT doc_id, title, visibility, department_owner FROM doc_metadata ORDER BY doc_id"):
    print(f"  {r[0]:10s} {r[1]:55s} visibility={r[2]:15s} owner={r[3]}")

conn.close()
