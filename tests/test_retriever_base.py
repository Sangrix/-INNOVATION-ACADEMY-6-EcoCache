import importlib.util
import sys
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
RETRIEVER_BASE_PATH = ROOT_DIR / "rag" / "retriever_base.py"


class RetrieverBaseModelCacheTest(unittest.TestCase):
    def _load_retriever_base(self, sentence_transformer_cls):
        fake_config = types.ModuleType("config")
        fake_config.EMBED_MODEL_ID = "fake/model"
        fake_config.QDRANT_URL = "http://localhost:6333"
        fake_config.QDRANT_API_KEY = None
        fake_config.TOP_K = 5

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = object()
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)

        fake_qdrant_client = types.ModuleType("qdrant_client")
        fake_qdrant_client.QdrantClient = object

        fake_qdrant_models = types.ModuleType("qdrant_client.models")
        fake_qdrant_models.Filter = object
        fake_qdrant_models.FieldCondition = object
        fake_qdrant_models.MatchValue = object
        fake_qdrant_models.Range = object

        fake_sentence_transformers = types.ModuleType("sentence_transformers")
        fake_sentence_transformers.SentenceTransformer = sentence_transformer_cls

        module_name = "retriever_base_under_test"
        spec = importlib.util.spec_from_file_location(module_name, RETRIEVER_BASE_PATH)
        module = importlib.util.module_from_spec(spec)

        fake_modules = {
            "config": fake_config,
            "torch": fake_torch,
            "qdrant_client": fake_qdrant_client,
            "qdrant_client.models": fake_qdrant_models,
            "sentence_transformers": fake_sentence_transformers,
        }

        with patch.dict(sys.modules, fake_modules):
            spec.loader.exec_module(module)
        return module

    def test_get_model_reuses_single_instance(self):
        created = []

        class FakeSentenceTransformer:
            def __init__(self, *args, **kwargs):
                created.append((args, kwargs))

        retriever_base = self._load_retriever_base(FakeSentenceTransformer)

        first = retriever_base.get_model()
        second = retriever_base.get_model()

        self.assertIs(first, second)
        self.assertEqual(1, len(created))

    def test_get_model_is_thread_safe_during_first_load(self):
        created = []

        class FakeSentenceTransformer:
            def __init__(self, *args, **kwargs):
                time.sleep(0.02)
                created.append((args, kwargs))

        retriever_base = self._load_retriever_base(FakeSentenceTransformer)

        with ThreadPoolExecutor(max_workers=8) as executor:
            models = list(executor.map(lambda _: retriever_base.get_model(), range(8)))

        self.assertTrue(all(model is models[0] for model in models))
        self.assertEqual(1, len(created))

    def test_search_records_query_stage_timings(self):
        class FakeSentenceTransformer:
            pass

        class FakeVector:
            def tolist(self):
                return [[0.1, 0.2]]

        class FakeModel:
            def encode(self, texts, normalize_embeddings):
                return FakeVector()

        class FakeClient:
            def query_points(self, **kwargs):
                point = types.SimpleNamespace(score=0.9, payload={"doc_id": "doc-1"})
                return types.SimpleNamespace(points=[point])

        retriever_base = self._load_retriever_base(FakeSentenceTransformer)
        retriever_base._model = FakeModel()
        retriever_base._client = FakeClient()
        timings = []

        results = retriever_base.search(
            "question",
            "documents",
            timings=timings,
            stage_prefix="document_search",
        )

        self.assertEqual([{"score": 0.9, "payload": {"doc_id": "doc-1"}}], results)
        stages = {timing["stage"] for timing in timings}
        self.assertIn("document_search.query_embedding", stages)
        self.assertIn("document_search.qdrant_query", stages)
        self.assertIn("document_search.total", stages)


if __name__ == "__main__":
    unittest.main()
