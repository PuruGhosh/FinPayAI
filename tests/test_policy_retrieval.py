import unittest

from src.finpay.access.scoped_query import UserContext
from src.finpay.policies.retrieval import retrieve_policies


class FakeCollection:
    def __init__(self, metadatas, query_result):
        self.metadatas = metadatas
        self.query_result = query_result
        self.query_calls = []

    def get(self, include):
        return {"metadatas": self.metadatas}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.query_result


class FakeClient:
    def __init__(self, collections):
        self.collections = collections
        self.requested = []

    def get_collection(self, name):
        self.requested.append(name)
        return self.collections[name]


class PolicyRetrievalTests(unittest.TestCase):
    def test_external_user_uses_public_collection_and_filter(self):
    # Collection separation protects the external boundary before filtering.
        collection = FakeCollection(
            [{"visibility": "public"}, {"visibility": "all_internal"}],
            {
                "documents": [["public policy"]],
                "metadatas": [[{"visibility": "public", "title": "Terms"}]],
                "distances": [[0.1]],
            },
        )
        client = FakeClient({"finpay_public_policies": collection})

        results = retrieve_policies(
            client,
            UserContext("anonymous", "", None, "external"),
            "terms",
        )

        self.assertEqual(["finpay_public_policies"], client.requested)
        self.assertEqual([{"visibility": {"$in": ["public"]}}], [
            collection.query_calls[0]["where"]
        ])
        self.assertEqual("public policy", results[0]["text"])

    def test_employee_filter_contains_only_allowed_visibility(self):
        collection = FakeCollection(
            [
                {"visibility": "public"},
                {"visibility": "all_internal"},
                {"visibility": "dept:FIN"},
                {"visibility": "dept:HR"},
            ],
            {
                "documents": [["finance policy"]],
                "metadatas": [[{"visibility": "dept:FIN"}]],
                "distances": [[0.2]],
            },
        )
        client = FakeClient({"finpay_internal_policies": collection})

        retrieve_policies(
            client,
            UserContext("EMP-FIN", "employee", "FIN"),
            "expenses",
        )

        self.assertEqual(
            {
                "visibility": {
                    "$in": ["all_internal", "dept:FIN", "public"]
                }
            },
            collection.query_calls[0]["where"],
        )

    def test_unclassified_result_is_removed(self):
        # Defense in depth rejects unsafe metadata even if the backend returns it.
        collection = FakeCollection(
            [{"visibility": "public"}],
            {
                "documents": [["leaked", "safe"]],
                "metadatas": [[{}, {"visibility": "public"}]],
                "distances": [[0.1, 0.2]],
            },
        )
        client = FakeClient({"finpay_public_policies": collection})

        results = retrieve_policies(
            client,
            UserContext("anonymous", "", None, "external"),
            "policy",
        )

        self.assertEqual(["safe"], [result["text"] for result in results])

    def test_invalid_result_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_policies(
                FakeClient({}),
                UserContext("anonymous", "", None, "external"),
                "policy",
                0,
            )


if __name__ == "__main__":
    unittest.main()
