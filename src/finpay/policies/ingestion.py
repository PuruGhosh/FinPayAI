"""Load policy markdown into metadata-rich chunks for Chroma ingestion."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
DEFAULT_CHUNK_SIZE = 1200


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


def _parse_policy(path: Path) -> tuple[dict[str, Any], str]:
    # Frontmatter is the source of truth for retrieval visibility metadata.
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(f"policy is missing YAML frontmatter: {path.name}")
    metadata = yaml.safe_load(match.group(1)) or {}
    required = {"doc_id", "doc_type", "title", "visibility"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"{path.name} is missing metadata: {sorted(missing)}")
    return metadata, content[match.end():].strip()


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    # Keep paragraphs together when possible, then split unusually long paragraphs.
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[start:start + chunk_size]
                for start in range(0, len(paragraph), chunk_size)
            )
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > chunk_size and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def load_policy_chunks(
    policy_dir: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[PolicyChunk]:
    """Parse and chunk every policy markdown file in a directory."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    chunks: list[PolicyChunk] = []
    for path in sorted(Path(policy_dir).glob("*.md")):
        metadata, body = _parse_policy(path)
        base_metadata = {
            "doc_id": str(metadata["doc_id"]),
            "file_name": path.name,
            "doc_type": str(metadata["doc_type"]),
            "title": str(metadata["title"]),
            "visibility": str(metadata["visibility"]),
            "department_owner": str(metadata.get("department_owner", "")),
        }
        for index, text in enumerate(_chunk_text(body, chunk_size)):
            chunks.append(
                PolicyChunk(
                    chunk_id=f"{base_metadata['doc_id']}-chunk-{index:04d}",
                    text=text,
                    metadata={**base_metadata, "chunk_index": index},
                )
            )
    return chunks


def ingest_policy_chunks(
    client: Any,
    chunks: list[PolicyChunk],
    embedding_function: Any,
    public_collection_name: str = "finpay_public_policies",
    internal_collection_name: str = "finpay_internal_policies",
) -> None:
    """Replace the two Chroma collections with the supplied policy chunks."""
    public = client.get_or_create_collection(
        public_collection_name,
        embedding_function=embedding_function,
    )
    internal = client.get_or_create_collection(
        internal_collection_name,
        embedding_function=embedding_function,
    )

    def synchronize(collection: Any, selected: list[PolicyChunk]) -> None:
        # Synchronize by stable chunk ID so repeated ingestion is idempotent.
        desired = {chunk.chunk_id: chunk for chunk in selected}
        existing = collection.get(include=["documents", "metadatas"])
        existing_by_id = {
            chunk_id: (document, metadata)
            for chunk_id, document, metadata in zip(
                existing.get("ids", []),
                existing.get("documents", []),
                existing.get("metadatas", []),
            )
        }

        stale_ids = sorted(set(existing_by_id) - set(desired))
        if stale_ids:
            collection.delete(ids=stale_ids)

        new_chunks = [desired[chunk_id] for chunk_id in sorted(set(desired) - set(existing_by_id))]
        if new_chunks:
            collection.add(
                ids=[chunk.chunk_id for chunk in new_chunks],
                documents=[chunk.text for chunk in new_chunks],
                metadatas=[chunk.metadata for chunk in new_chunks],
            )

        changed_chunks = [
            desired[chunk_id]
            for chunk_id in sorted(set(desired) & set(existing_by_id))
            if (
                existing_by_id[chunk_id][0] != desired[chunk_id].text
                or existing_by_id[chunk_id][1] != desired[chunk_id].metadata
            )
        ]
        if changed_chunks:
            collection.update(
                ids=[chunk.chunk_id for chunk in changed_chunks],
                documents=[chunk.text for chunk in changed_chunks],
                metadatas=[chunk.metadata for chunk in changed_chunks],
            )

    synchronize(public, [chunk for chunk in chunks if chunk.metadata["visibility"] == "public"])
    synchronize(internal, chunks)