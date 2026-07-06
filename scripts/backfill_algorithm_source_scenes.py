#!/usr/bin/env python3
"""Backfill plain source scenes for D1 algorithm cards.

The D1 pool contains many paper-title-like anchors. This script asks an
OpenAI-compatible model to rewrite each row into a short, concrete, Chinese
source-world scene for non-expert readers, then stores it as source_scene.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DOMAINS_FILE = ROOT / "references" / "domains.json"
CACHE_FILE = ROOT / "tmp" / "d1_source_scenes_cache.json"


SYSTEM = """你是 WildIdea 卡池清洗器。任务：把算法/技术卡池里的英文论文式锚点，改写成非专业用户一眼能懂的“实际场景版源现象”。

要求：
1. 只描述源世界里实际发生的事，不要映射到用户问题。
2. 一句话，35-85 个中文字符为宜。
3. 尽量使用中文；专业缩写必须放在中文名后的中文括号里，如“随机采样一致性（RANSAC）”。
4. prompt 译为“提示词”，token 译为“词元”，mask 译为“掩码”，agent 译为“智能体”，reward model 译为“奖励模型”，test-time 译为“推理时”。
5. 不要写论文标题，不要写“该论文/研究提出”，不要写“applies/draws analogy”等英文论文腔。
6. 保留机制的关键因果链：输入/约束、关键操作、输出/结果。

只输出 JSON 对象：{"D1-00": "……", "D1-01": "……"}。"""


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def row_payload(row: dict[str, Any]) -> dict[str, Any]:
    method = (row.get("methods") or [{}])[0]
    example = (row.get("transfer_examples") or [{}])[0]
    return {
        "id": row.get("id"),
        "domain": row.get("domain"),
        "anchor": row.get("anchor"),
        "method_name": method.get("name"),
        "mechanism": method.get("mechanism"),
        "process": method.get("process"),
        "key_insight": method.get("key_insight"),
        "example": example,
    }


def fallback_scene(row: dict[str, Any]) -> str:
    """Deterministic fallback when no model is available."""
    method = (row.get("methods") or [{}])[0]
    anchor = str(row.get("anchor") or "").strip()
    mechanism = str(method.get("mechanism") or "").strip()
    text = anchor or mechanism or str(row.get("domain") or "算法机制")
    replacements = {
        "prompt": "提示词",
        "Prompt": "提示词",
        "token": "词元",
        "Token": "词元",
        "mask": "掩码",
        "Mask": "掩码",
        "agent": "智能体",
        "Agent": "智能体",
        "reward model": "奖励模型",
        "Reward model": "奖励模型",
        "test-time": "推理时",
        "Test-time": "推理时",
        "RANSAC": "随机采样一致性（RANSAC）",
        "CTC": "连接主义时序分类（CTC）",
        "DDPM": "去噪扩散概率模型（DDPM）",
        "LoRA": "低秩适配（LoRA）",
        "RAG": "检索增强生成（RAG）",
        "DPO": "直接偏好优化（DPO）",
        "PCGrad": "冲突梯度投影（PCGrad）",
        "UCB": "置信上界（UCB）",
        "NMS": "非极大值抑制（NMS）",
        "HNSW": "分层可导航小世界图（HNSW）",
        "FFT": "快速傅里叶变换（FFT）",
        "QUBO": "二次无约束二元优化（QUBO）",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.replace("：Applies ", "中，")
    text = text.replace("：Draws analogy between ", "中，把")
    text = text.replace("：Uses ", "中，用")
    text = text.replace("：Transforms ", "中，把")
    text = text.replace("：", "：")
    return text[:110].rstrip("，。；:： ") + "。"


def batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def call_model(rows: list[dict[str, Any]], provider: str, model: str) -> dict[str, str]:
    from wildidea.llm import LLMClient

    client = LLMClient(provider=provider, model=model)
    user = "请改写以下卡池条目：\n" + json.dumps(
        [row_payload(r) for r in rows],
        ensure_ascii=False,
        indent=2,
    )
    parsed = client.chat_json(SYSTEM, user, temperature=0.1, max_tokens=2500, retries=3)
    return {str(k): str(v).strip() for k, v in parsed.items() if str(v).strip()}


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fallback-only", action="store_true")
    parser.add_argument("--provider", default=os.environ.get("WILDIDEA_PROVIDER", "deepseek"))
    parser.add_argument("--model", default=os.environ.get("WILDIDEA_MODEL", "deepseek-chat"))
    args = parser.parse_args()

    doc = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
    rows = doc["pools"]["D1"]
    target_rows = rows[: args.limit] if args.limit else rows

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    for batch in batched([r for r in target_rows if not cache.get(r["id"])], args.batch_size):
        if args.fallback_only:
            updates = {r["id"]: fallback_scene(r) for r in batch}
        else:
            try:
                updates = call_model(batch, args.provider, args.model)
            except Exception as exc:
                print(f"model batch failed, using fallback: {exc}")
                updates = {r["id"]: fallback_scene(r) for r in batch}
        cache.update(updates)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"cached {len(cache)}/{len(target_rows)}")

    for row in rows:
        if row.get("id") in cache:
            row["source_scene"] = cache[row["id"]]

    DOMAINS_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {DOMAINS_FILE}")


if __name__ == "__main__":
    main()
