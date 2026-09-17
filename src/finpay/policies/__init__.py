"""Policy-document loading and vector-store ingestion."""

from .ingestion import PolicyChunk, load_policy_chunks

__all__ = ["PolicyChunk", "load_policy_chunks"]