"""Tests for WildIdea CLI package.

Usage:
    python -m pytest tests/ -v              # all tests
    python -m pytest tests/ -v -k unit      # unit tests only (no API calls)
    python -m pytest tests/ -v -k integration  # integration tests (needs API key)
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─── Unit Tests (no API calls) ──────────────────────────────────────────────

class TestLLMExtractJSON(unittest.TestCase):
    """Test JSON extraction from LLM responses."""

    def test_plain_json(self):
        from wildidea.llm import extract_json
        result = extract_json('{"a": 1, "b": 2}')
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_json_in_markdown(self):
        from wildidea.llm import extract_json
        text = 'Here is the result:\n```json\n{"score": 7}\n```\nDone.'
        result = extract_json(text)
        self.assertEqual(result, {"score": 7})

    def test_json_with_surrounding_text(self):
        from wildidea.llm import extract_json
        text = 'Analysis shows {"structural_depth": {"score": 8}} is correct.'
        result = extract_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["structural_depth"]["score"], 8)

    def test_nested_json(self):
        from wildidea.llm import extract_json
        text = '{"a": {"b": {"c": 1}}, "d": 2}'
        result = extract_json(text)
        self.assertEqual(result["a"]["b"]["c"], 1)
        self.assertEqual(result["d"], 2)

    def test_no_json(self):
        from wildidea.llm import extract_json
        result = extract_json("no json here")
        self.assertIsNone(result)

    def test_empty_string(self):
        from wildidea.llm import extract_json
        result = extract_json("")
        self.assertIsNone(result)


class TestDomainPool(unittest.TestCase):
    """Test domain pool operations."""

    def test_build_slots_product(self):
        from wildidea.core.domain_pool import build_slots
        slots = build_slots("product")
        self.assertEqual(len(slots), 10)
        slot_types = [s["slot"] for s in slots]
        self.assertIn("D4", slot_types)  # product type has D4

    def test_build_slots_algorithm(self):
        from wildidea.core.domain_pool import build_slots
        slots = build_slots("algorithm")
        self.assertEqual(len(slots), 10)
        slot_types = [s["slot"] for s in slots]
        self.assertEqual(slot_types.count("D1"), 5)  # algorithm type has 5 D1

    def test_slots_have_required_fields(self):
        from wildidea.core.domain_pool import build_slots
        slots = build_slots("research")
        for s in slots:
            self.assertIn("slot", s)
            # RANDOM_WORD doesn't have "id", others do
            if s["slot"] != "RANDOM_WORD":
                self.assertIn("id", s)

    def test_exclude_works(self):
        from wildidea.core.domain_pool import build_slots
        slots1 = build_slots("product")
        # Exclude only slots that have "id" (not RANDOM_WORD)
        exclude_ids = [s["id"] for s in slots1[:3] if "id" in s]
        slots2 = build_slots("product", exclude=exclude_ids)
        for s in slots2:
            if "id" in s:
                self.assertNotIn(s["id"], exclude_ids)


class TestDetectType(unittest.TestCase):
    """Test problem type auto-detection."""

    def test_algorithm(self):
        from wildidea.pipeline import detect_type
        self.assertEqual(detect_type("用算法优化信号处理"), "algorithm")

    def test_product(self):
        from wildidea.pipeline import detect_type
        self.assertEqual(detect_type("帮我想10个App的功能创新"), "product")

    def test_strategy(self):
        from wildidea.pipeline import detect_type
        self.assertEqual(detect_type("用户增长的运营策略"), "strategy")

    def test_research(self):
        from wildidea.pipeline import detect_type
        self.assertEqual(detect_type("研究CRISPR的新实验假设"), "research")

    def test_unknown_defaults_to_product(self):
        from wildidea.pipeline import detect_type
        self.assertEqual(detect_type("xyzzy"), "product")


class TestValidateCandidate(unittest.TestCase):
    """Test candidate validation."""

    def test_valid_candidate(self):
        from wildidea.pipeline import _validate_candidate
        candidate = {
            "name": "测试候选",
            "proto": "通用机制描述",
            "desc": "具体实施方案",
            "fail": "失败条件",
        }
        errors = _validate_candidate(candidate, forbid_terms=[])
        self.assertEqual(errors, [])

    def test_missing_field(self):
        from wildidea.pipeline import _validate_candidate
        candidate = {"name": "测试", "desc": "描述"}
        errors = _validate_candidate(candidate, forbid_terms=[])
        self.assertTrue(any("proto" in e for e in errors))

    def test_deanchoring_violation(self):
        from wildidea.pipeline import _validate_candidate
        candidate = {
            "name": "测试",
            "proto": "用EEG信号检测情绪",  # leaks "EEG"
            "desc": "描述",
            "fail": "失败条件",
        }
        errors = _validate_candidate(candidate, forbid_terms=["EEG"])
        self.assertTrue(any("EEG" in e for e in errors))


class TestRenderer(unittest.TestCase):
    """Test HTML rendering."""

    def test_render_produces_html(self):
        from wildidea.renderer import Candidate, render
        template = Path(__file__).parent.parent / "templates" / "poster.html"
        if not template.exists():
            self.skipTest("Template not found")

        candidates = [
            Candidate(
                name="测试卡片",
                slot="D1",
                source="测试来源",
                proto="通用机制",
                desc="具体方案",
                fail="失败条件",
            )
        ]
        output = Path("/tmp/test_wildidea_output.html")
        result = render(
            candidates=candidates,
            title="测试标题",
            focus="测试焦点",
            template_path=template,
            output_path=output,
        )
        self.assertTrue(result.exists())
        html = result.read_text()
        self.assertIn("测试卡片", html)
        self.assertIn("D1", html)
        output.unlink(missing_ok=True)


class TestJudgeConfig(unittest.TestCase):
    """Test judge threshold lookup."""

    def test_claude_thresholds(self):
        from wildidea.judge import get_thresholds
        thr, avg = get_thresholds("anthropic/claude-sonnet-4.5")
        self.assertEqual(thr, 6)
        self.assertEqual(avg, 6.0)

    def test_v4pro_thresholds(self):
        from wildidea.judge import get_thresholds
        thr, avg = get_thresholds("deepseek/deepseek-v4-pro")
        self.assertEqual(thr, 7)
        self.assertEqual(avg, 7.0)

    def test_unknown_model_defaults(self):
        from wildidea.judge import get_thresholds
        thr, avg = get_thresholds("some/random-model")
        self.assertEqual(thr, 6)


# ─── Integration Tests (need API key) ──────────────────────────────────────

@unittest.skipUnless(
    __import__("os").environ.get("OPENROUTER_API_KEY"),
    "OPENROUTER_API_KEY not set",
)
class TestLLMClientIntegration(unittest.TestCase):
    """Test real LLM API calls."""

    def test_chat_returns_string(self):
        from wildidea.llm import LLMClient
        client = LLMClient(
            provider="openrouter",
            model="anthropic/claude-sonnet-4",
            proxy="http://127.0.0.1:7897",
        )
        result = client.chat(
            system="You are a helpful assistant.",
            user="What is 2+2? Reply with just the number.",
            temperature=0.0,
        )
        self.assertIn("4", result)

    def test_chat_json_returns_dict(self):
        from wildidea.llm import LLMClient
        client = LLMClient(
            provider="openrouter",
            model="anthropic/claude-sonnet-4",
            proxy="http://127.0.0.1:7897",
        )
        result = client.chat_json(
            system="Return valid JSON only.",
            user='Return: {"name": "test", "score": 5}',
            temperature=0.0,
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["score"], 5)


if __name__ == "__main__":
    unittest.main()
