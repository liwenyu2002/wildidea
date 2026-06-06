"""Opt-in smoke test for the real LLM pipeline.

Run manually when you want to spend a small amount of API quota:

    WILDIDEA_RUN_REAL_API_SMOKE=1 pytest tests/test_real_api_smoke.py -q -s
"""
from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("WILDIDEA_RUN_REAL_API_SMOKE") != "1",
    reason="Set WILDIDEA_RUN_REAL_API_SMOKE=1 to run the real API smoke test.",
)
def test_real_api_pipeline_reaches_generation_and_judging(tmp_path):
    from wildidea.configure import get_config
    from wildidea.judge import JudgeConfig
    from wildidea.pipeline import Config, run

    local_config = get_config()
    provider = os.environ.get("WILDIDEA_PROVIDER") or local_config.get("provider") or "openrouter"
    model = os.environ.get("WILDIDEA_MODEL") or local_config.get("model") or "deepseek/deepseek-v4-pro"
    judge_model = os.environ.get("WILDIDEA_JUDGE_MODEL") or local_config.get("judge_model") or model
    api_key = (
        os.environ.get("WILDIDEA_API_KEY")
        or local_config.get("api_key")
        or _provider_api_key(provider)
    )
    if not api_key:
        pytest.skip(f"No API key configured for provider {provider}.")

    base_url = (
        os.environ.get("WILDIDEA_BASE_URL")
        or local_config.get("base_url")
        or _provider_base_url(provider)
    )
    proxy = os.environ.get("WILDIDEA_PROXY") or local_config.get("proxy")
    cards = int(os.environ.get("WILDIDEA_REAL_SMOKE_CARDS", "2"))
    parallel = int(os.environ.get("WILDIDEA_REAL_SMOKE_PARALLEL", str(cards)))
    problem = os.environ.get("WILDIDEA_REAL_SMOKE_PROBLEM", "给相册 app 找一个记忆整理功能创新思路")
    events: list[tuple[str, dict]] = []

    config = Config(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        proxy=proxy,
        judge_config=JudgeConfig(
            provider=provider,
            model=judge_model,
            api_key=api_key,
            base_url=base_url,
            proxy=proxy,
        ),
        output_dir=tmp_path,
        search_enabled=False,
        target_count=cards,
        parallel=parallel,
        max_retries=int(os.environ.get("WILDIDEA_REAL_SMOKE_RETRIES", "3")),
    )

    result = run(problem, config, on_progress=lambda event, data: events.append((event, data)))
    event_types = {event for event, _ in events}

    assert "slots_done" in event_types
    assert event_types & {"judged", "candidate_ok", "threshold_rejected"}
    assert result.candidates or "threshold_rejected" in event_types
    print(
        "real_api_smoke",
        {
            "provider": provider,
            "model": model,
            "judge_model": judge_model,
            "cards": cards,
            "candidates": len(result.candidates),
            "events": sorted(event_types),
        },
    )


def _provider_api_key(provider: str) -> str | None:
    env_keys = {
        "openrouter": "OPENROUTER_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "xiaomi": "MIMO_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    key = env_keys.get(provider)
    return os.environ.get(key or "") if key else None


def _provider_base_url(provider: str) -> str | None:
    from wildidea.configure import PROVIDERS

    for item in PROVIDERS.values():
        if item["id"] == provider:
            return item.get("base_url")
    return None
