from pathlib import Path
import unittest

from src.finpay.policies.ingestion import PolicyChunk, ingest_policy_chunks, load_policy_chunks


POLICY_DIR = Path(__file__).parents[1] / "data" / "policies"


class FakeCollection:
    def __init__(self):
        self.records = {}
        self.add_calls = 0
        self.update_calls = 0
        self.delete_calls = 0

    def get(self, include):
        return {
            "ids": list(self.records),
            "documents": [self.records[key][0] for key in self.records],
            "metadatas": [self.records[key][1] for key in self.records],
        }

    def add(self, ids, documents, metadatas):
        self.add_calls += 1
        self.records.update(zip(ids, zip(documents, metadatas)))

    def update(self, ids, documents, metadatas):
        self.update_calls += 1
        self.records.update(zip(ids, zip(documents, metadatas)))

    def delete(self, ids):
        self.delete_calls += 1
        for chunk_id in ids:
            self.records.pop(chunk_id, None)


class FakeClient:
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name, embedding_function):
        return self.collections.setdefault(name, FakeCollection())


class PolicyIngestionTests(unittest.TestCase):
    def test_all_policy_files_are_chunked_with_security_metadata(self):
    # Every chunk must retain the metadata needed for later authorization.
        chunks = load_policy_chunks(POLICY_DIR, chunk_size=500)
        self.assertGreater(len(chunks), 10)
        self.assertEqual(10, len({chunk.metadata["doc_id"] for chunk in chunks}))
        self.assertTrue(all(chunk.text for chunk in chunks))
        self.assertTrue(all("---" not in chunk.text for chunk in chunks))
        self.assertTrue(all("visibility" in chunk.metadata for chunk in chunks))

    def test_chunk_ids_are_unique_and_bounded(self):
        chunks = load_policy_chunks(POLICY_DIR, chunk_size=300)
        self.assertEqual(len(chunks), len({chunk.chunk_id for chunk in chunks}))
        self.assertTrue(all(len(chunk.text) <= 300 for chunk in chunks))

    def test_invalid_chunk_size_is_rejected(self):
        with self.assertRaises(ValueError):
            load_policy_chunks(POLICY_DIR, chunk_size=0)

    def test_reingestion_skips_unchanged_chunks(self):
        # Stable IDs make repeated ingestion safe and inexpensive.
        chunks = [
            PolicyChunk("POL-001-chunk-0000", "public text", {"visibility": "public"}),
            PolicyChunk("POL-002-chunk-0000", "internal text", {"visibility": "all_internal"}),
        ]
        client = FakeClient()

        ingest_policy_chunks(client, chunks, embedding_function=object())
        public = client.collections["finpay_public_policies"]
        internal = client.collections["finpay_internal_policies"]
        public.add_calls = internal.add_calls = 0

        ingest_policy_chunks(client, chunks, embedding_function=object())

        self.assertEqual(0, public.add_calls)
        self.assertEqual(0, internal.add_calls)
        self.assertEqual(0, public.update_calls)
        self.assertEqual(0, internal.update_calls)
        self.assertEqual(0, public.delete_calls)
        self.assertEqual(0, internal.delete_calls)


if __name__ == "__main__":
    unittest.main()