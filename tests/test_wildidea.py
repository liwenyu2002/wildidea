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
            "advantage": "这种方案的优势在于，用户能先看到收益",
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
            "advantage": "这种方案的优势在于，能快速解释价值",
            "desc": "描述",
            "fail": "失败条件",
        }
        errors = _validate_candidate(candidate, forbid_terms=["EEG"])
        self.assertTrue(any("EEG" in e for e in errors))


class TestPipelinePublicSlot(unittest.TestCase):
    """Test public progress slot payloads."""

    def test_public_slot_repairs_truncated_anchor_from_mechanism(self):
        from wildidea.pipeline import _public_slot

        slot = {
            "id": "D2-41",
            "slot": "D2",
            "domain": "Seismology",
            "anchor": (
                "Earthquake-aftershock model for pandemic spread：Applies the "
                "earthquake/aftershock model (ETAS) as an analogy to model COVID-19 "
                "pandemic propagation, treating infection pressure like seismic pressure d"
            ),
            "methods": [{
                "name": "Earthquake-aftershock model for pandemic spread",
                "mechanism": (
                    "Applies the earthquake/aftershock model (ETAS) as an analogy to "
                    "model COVID-19 pandemic propagation, treating infection pressure "
                    "like seismic pressure diffusing through porous media."
                ),
            }],
        }

        public = _public_slot(slot)

        self.assertIn("diffusing through porous media.", public["source"])
        self.assertEqual(public["source"], public["source_phenomenon"])


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
                advantage="这种方案的优势在于，能快速解释价值",
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
        self.assertEqual(thr, 8)
        self.assertEqual(avg, 8.0)

    def test_unknown_model_defaults(self):
        from wildidea.judge import get_thresholds
        thr, avg = get_thresholds("some/random-model")
        self.assertEqual(thr, 6)

    def test_threshold_requires_novelty(self):
        from wildidea.judge import JudgeClient, JudgeScores

        judge = JudgeClient.__new__(JudgeClient)
        judge.sd_threshold = 6
        judge.novelty_threshold = 7
        judge.applicability_threshold = 9

        self.assertFalse(judge.passes_threshold(JudgeScores(structural_depth=8, novelty=6, applicability=9)))
        self.assertTrue(judge.passes_threshold(JudgeScores(structural_depth=8, novelty=7, applicability=9)))

    def test_threshold_requires_applicability_9(self):
        from wildidea.judge import JudgeClient, JudgeScores

        judge = JudgeClient.__new__(JudgeClient)
        judge.sd_threshold = 6
        judge.novelty_threshold = 7
        judge.applicability_threshold = 9

        self.assertFalse(judge.passes_threshold(JudgeScores(structural_depth=8, novelty=8, applicability=8)))
        self.assertTrue(judge.passes_threshold(JudgeScores(structural_depth=8, novelty=8, applicability=9)))

    def test_v4pro_rejects_sd_below_8(self):
        from wildidea.judge import JudgeClient, JudgeScores

        judge = JudgeClient.__new__(JudgeClient)
        judge.sd_threshold = 8
        judge.novelty_threshold = 7
        judge.applicability_threshold = 9

        self.assertFalse(judge.passes_threshold(JudgeScores(structural_depth=7, novelty=9, applicability=9)))
        self.assertTrue(judge.passes_threshold(JudgeScores(structural_depth=8, novelty=9, applicability=9)))


class TestPipelineThresholdReroll(unittest.TestCase):
    """Test per-card judge threshold reroll behavior."""

    def test_low_novelty_candidate_is_rerolled(self):
        from wildidea import pipeline
        from wildidea.judge import JudgeConfig, JudgeScores

        slot = {
            "id": "D1-test",
            "slot": "D1",
            "domain": "测试领域",
            "anchor": "测试源现象",
            "methods": [{"mechanism": "测试机制"}],
        }
        drafts = iter([
            {
                "name": "低新颖方案",
                "slot": "D1",
                "source": "测试方法",
                "proto": "结构足够但太常见",
                "advantage": "这种方案的优势在于，能快速解释价值",
                "desc": "低新颖落地方案",
                "fail": "失败边界",
            },
            {
                "name": "高新颖方案",
                "slot": "D1",
                "source": "测试方法",
                "proto": "结构足够且更意外",
                "advantage": "让用户先看懂为什么值得采用",
                "desc": "高新颖落地方案",
                "fail": "失败边界",
            },
        ])

        class FakeLLM:
            def __init__(self, *args, **kwargs):
                pass

        class FakeJudge:
            sd_threshold = 6
            novelty_threshold = 7
            applicability_threshold = 9

            def __init__(self, config):
                pass

            def evaluate(self, problem, source_domain, target_domain, proto, desc):
                novelty = 5 if "低新颖" in desc else 8
                return JudgeScores(
                    structural_depth=8,
                    domain_distance=8,
                    applicability=9,
                    novelty=novelty,
                )

            def passes_threshold(self, scores):
                return (
                    scores.structural_depth >= self.sd_threshold
                    and scores.novelty >= self.novelty_threshold
                    and scores.applicability >= self.applicability_threshold
                )

        events = []
        with patch.object(pipeline, "LLMClient", FakeLLM), \
             patch.object(pipeline, "JudgeClient", FakeJudge), \
             patch.object(pipeline, "_build_target_slots", return_value=[slot]), \
             patch.object(pipeline, "_generate_candidate", side_effect=lambda problem, slot, llm: next(drafts)):
            result = pipeline.run(
                "测试问题",
                pipeline.Config(
                    judge_config=JudgeConfig(model="fake-model", provider="fake-provider"),
                    target_count=1,
                    max_retries=2,
                    output_dir=Path("/tmp/wildidea-test-output"),
                ),
                on_progress=lambda event, payload: events.append((event, payload)),
            )

        self.assertEqual([candidate.name for candidate in result.candidates], ["高新颖方案"])
        self.assertIn("threshold_rejected", [event for event, _ in events])
        self.assertNotIn("banned", [event for event, _ in events])
        ok_payload = next(payload for event, payload in events if event == "candidate_ok")
        self.assertEqual(ok_payload["name"], "高新颖方案")
        self.assertEqual(ok_payload["attempt"], 2)
        self.assertEqual(ok_payload["reroll_count"], 1)
        self.assertEqual(ok_payload["proto"], "结构足够且更意外")
        self.assertEqual(ok_payload["advantage"], "这种方案的优势在于，让用户先看懂为什么值得采用")
        self.assertEqual(ok_payload["desc"], "高新颖落地方案")
        self.assertEqual(ok_payload["fail"], "失败边界")
        self.assertEqual(ok_payload["scores"]["structural_depth"], 8)
        self.assertEqual(ok_payload["scores"]["novelty"], 8)
        self.assertEqual(ok_payload["scores"]["applicability"], 9)


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
