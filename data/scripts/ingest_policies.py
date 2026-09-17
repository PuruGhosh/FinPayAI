"""Ingest policy chunks into separate persistent Chroma collections."""

from pathlib import Path
import os
import sys

import chromadb
from dotenv import load_dotenv
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from src.finpay.policies.ingestion import ingest_policy_chunks, load_policy_chunks


DATA_DIR = Path(__file__).resolve().parents[1]
CHROMA_DIR = DATA_DIR / "db" / "chroma"
POLICY_DIR = DATA_DIR / "policies"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def create_chroma_client():
    host = os.getenv("CHROMA_HOST")
    if host:
    # Use the configured server for shared ingestion when available.
        port = int(os.getenv("CHROMA_PORT", "8000"))
        return chromadb.HttpClient(host=host, port=port)
    # Persistent local storage supports the no-server POC setup.
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def main() -> None:
    # Parse policy files once, then synchronize both physical collections.
    chunks = load_policy_chunks(POLICY_DIR)
    client = create_chroma_client()
    embedding_function = DefaultEmbeddingFunction()
    ingest_policy_chunks(client, chunks, embedding_function)
    public_count = client.get_collection("finpay_public_policies").count()
    internal_count = client.get_collection("finpay_internal_policies").count()
    print(f"Ingested {len(chunks)} chunks")
    print(f"  finpay_public_policies: {public_count} chunks")
    print(f"  finpay_internal_policies: {internal_count} chunks")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    location = os.getenv("CHROMA_HOST", str(CHROMA_DIR))
    print(f"Chroma database: {location}")


if __name__ == "__main__":
    main()