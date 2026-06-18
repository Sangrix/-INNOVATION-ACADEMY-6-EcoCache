"""Tests for CIASC dynamic alpha calculation — SPEC-CIASC-001.

Covers SC-1 through SC-7 from acceptance.md.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).resolve().parents[1]
CIASC_PATH = ROOT_DIR / "rag" / "baseline_ciasc.py"


def _make_fake_config(**overrides):
    m = types.ModuleType("config")
    m.TOP_K = 5
    m.COLLECTION_QA = "qa_pairs"
    m.COLLECTION_DOCS = "documents"
    m.QA_SIMILARITY_THRESHOLD = 0.75
    m.CIASC_CI_MIN = 350.0
    m.CIASC_CI_MAX = 500.0
    m.CIASC_ALPHA_K = 0.5
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _make_fake_retriever_base():
    m = types.ModuleType("retriever_base")

    class FakeBase:
        pass

    m.BaseRetriever = FakeBase
    m.search = MagicMock(return_value=[])
    return m


def _load_ciasc(fake_config=None, fake_rb=None):
    """Load CIASCRetriever module with injected fake dependencies."""
    if fake_config is None:
        fake_config = _make_fake_config()
    if fake_rb is None:
        fake_rb = _make_fake_retriever_base()

    saved = {name: sys.modules.get(name) for name in ("config", "retriever_base")}
    sys.modules["config"] = fake_config
    sys.modules["retriever_base"] = fake_rb
    try:
        spec = importlib.util.spec_from_file_location("_ciasc_test", CIASC_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, fake_rb
    finally:
        for name, orig in saved.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig


class TestCalculateDynamicAlpha(unittest.TestCase):
    """Unit tests for CIASCRetriever._calculate_dynamic_alpha()."""

    def setUp(self):
        self.mod, _ = _load_ciasc()
        self.R = self.mod.CIASCRetriever

    def test_sc1_mid_ci(self):
        """SC-1: CI=420 → alpha_used ≈ 0.1525, not equal to 0.15."""
        r = self.R(alpha=0.15, k=0.5)
        alpha = r._calculate_dynamic_alpha(420.0)
        # CI_norm = (420-350)/150 = 0.4667
        # alpha = 0.15 * (1 + 0.5 * |0.4667 - 0.5|) = 0.15 * (1 + 0.5*0.0333) ≈ 0.15248
        self.assertAlmostEqual(alpha, 0.15248, delta=0.001)
        self.assertNotEqual(alpha, 0.15)

    def test_sc2_min_ci(self):
        """SC-2: CI=350 (CI_norm=0) → alpha_used = 0.1875."""
        r = self.R(alpha=0.15, k=0.5)
        alpha = r._calculate_dynamic_alpha(350.0)
        # alpha = 0.15 * (1 + 0.5 * |0 - 0.5|) = 0.15 * 1.25 = 0.1875
        self.assertAlmostEqual(alpha, 0.1875, places=9)

    def test_sc3_max_ci(self):
        """SC-3: CI=500 (CI_norm=1) → alpha_used = 0.1875."""
        r = self.R(alpha=0.15, k=0.5)
        alpha = r._calculate_dynamic_alpha(500.0)
        self.assertAlmostEqual(alpha, 0.1875, places=9)

    def test_symmetry(self):
        """CI=350 and CI=500 produce identical alpha (symmetric formula)."""
        r = self.R(alpha=0.15, k=0.5)
        self.assertEqual(
            r._calculate_dynamic_alpha(350.0),
            r._calculate_dynamic_alpha(500.0),
        )

    def test_sc6_custom_k(self):
        """SC-6: k=1.0, CI=500 → alpha_used = 0.225."""
        r = self.R(alpha=0.15, k=1.0)
        alpha = r._calculate_dynamic_alpha(500.0)
        # CI_norm=1, alpha = 0.15 * (1 + 1.0 * 0.5) = 0.15 * 1.5 = 0.225
        self.assertAlmostEqual(alpha, 0.225, places=9)

    def test_ci_norm_clamped_above(self):
        """CI=600 → CI_norm clamped to 1.0, same result as CI=500."""
        r = self.R(alpha=0.15, k=0.5)
        self.assertEqual(
            r._calculate_dynamic_alpha(600.0),
            r._calculate_dynamic_alpha(500.0),
        )

    def test_ci_norm_clamped_below(self):
        """CI=200 → CI_norm clamped to 0.0, same result as CI=350."""
        r = self.R(alpha=0.15, k=0.5)
        self.assertEqual(
            r._calculate_dynamic_alpha(200.0),
            r._calculate_dynamic_alpha(350.0),
        )

    def test_k_zero_returns_alpha_base(self):
        """k=0 → alpha_used = alpha_base (no amplification)."""
        r = self.R(alpha=0.15, k=0.0)
        alpha = r._calculate_dynamic_alpha(420.0)
        self.assertAlmostEqual(alpha, 0.15, places=9)

    def test_k_defaults_from_config(self):
        """When k is not passed, k is read from config.CIASC_ALPHA_K."""
        cfg = _make_fake_config(CIASC_ALPHA_K=1.0)
        mod, _ = _load_ciasc(fake_config=cfg)
        r = mod.CIASCRetriever(alpha=0.15)
        # k=1.0, CI=500 → alpha = 0.225
        alpha = r._calculate_dynamic_alpha(500.0)
        self.assertAlmostEqual(alpha, 0.225, places=9)


class TestRetrieveReturnsAlphaUsed(unittest.TestCase):
    """Integration: retrieve() returns alpha_used in result dict."""

    def _make_retriever_with_threshold(self, threshold, alpha_used):
        mod, fake_rb = _load_ciasc()
        r = mod.CIASCRetriever(alpha=0.15, k=0.5)
        # Monkeypatch _get_threshold to bypass real carbon API
        r._get_threshold = lambda: (threshold, alpha_used)
        # Monkeypatch search on the module
        mod.search = MagicMock(return_value=[])
        return r

    def test_sc2_alpha_in_result(self):
        """SC-2: retrieve() includes alpha_used=0.1875 when CI=350."""
        r = self._make_retriever_with_threshold(0.85, 0.1875)
        result = r.retrieve("장학금 신청 방법")
        self.assertIn("alpha_used", result)
        self.assertAlmostEqual(result["alpha_used"], 0.1875, places=9)

    def test_sc7_fallback_on_ci_none(self):
        """SC-7: CI=None → alpha_used = alpha_base (0.15) via fallback."""
        r = self._make_retriever_with_threshold(0.75, 0.15)
        result = r.retrieve("테스트 질문")
        self.assertIn("alpha_used", result)
        self.assertAlmostEqual(result["alpha_used"], 0.15, places=9)

    def test_alpha_used_present_on_cache_hit(self):
        """alpha_used is included in result even on qa_pairs cache hit."""
        mod, fake_rb = _load_ciasc()
        r = mod.CIASCRetriever(alpha=0.15, k=0.5)
        r._get_threshold = lambda: (0.5, 0.1875)  # low threshold → cache hit
        # search returns a result with score above threshold
        mod.search = MagicMock(return_value=[{"score": 0.9, "payload": {}}])
        result = r.retrieve("캐시 히트 테스트")
        self.assertIn("alpha_used", result)
        self.assertEqual(result["source"], "qa_pairs")

    def test_alpha_used_present_on_document_fallback(self):
        """alpha_used is included when fallback to documents."""
        mod, fake_rb = _load_ciasc()
        r = mod.CIASCRetriever(alpha=0.15, k=0.5)
        r._get_threshold = lambda: (0.95, 0.1875)  # high threshold → no cache hit
        mod.search = MagicMock(return_value=[])
        result = r.retrieve("문서 검색 테스트")
        self.assertIn("alpha_used", result)
        self.assertEqual(result["source"], "documents")


class TestGetThresholdReturnsTuple(unittest.TestCase):
    """_get_threshold() must return (threshold, alpha_used) tuple."""

    def test_returns_tuple_of_two_floats(self):
        """_get_threshold always returns a (float, float) tuple."""
        mod, _ = _load_ciasc()
        r = mod.CIASCRetriever(alpha=0.15, k=0.5)
        result = r._get_threshold()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        threshold, alpha_used = result
        self.assertIsInstance(threshold, float)
        self.assertIsInstance(alpha_used, float)

    def test_fallback_on_exception(self):
        """On carbon_optimizer import error, fallback returns (QA_SIMILARITY_THRESHOLD, self.alpha)."""
        from unittest.mock import patch
        mod, _ = _load_ciasc()
        r = mod.CIASCRetriever(alpha=0.15, k=0.5)
        # Setting sys.modules entry to None causes ImportError on `from carbon_optimizer import ...`
        with patch.dict(sys.modules, {"carbon_optimizer": None}):
            threshold, alpha_used = r._get_threshold()
        self.assertAlmostEqual(threshold, 0.75, places=9)
        self.assertAlmostEqual(alpha_used, 0.15, places=9)


if __name__ == "__main__":
    unittest.main()
