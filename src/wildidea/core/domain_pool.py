#!/usr/bin/env python3
"""Randomly sample WildIdea domain slots without loading the full pool into model context.

Usage:
  python scripts/pick_domain_slots.py --type algorithm
  python scripts/pick_domain_slots.py --type product
  python scripts/pick_domain_slots.py --type algorithm --seed 42

Reroll a single slot (single entry point — no separate sub-script CLI needed):
  python scripts/pick_domain_slots.py --reroll mao
  python scripts/pick_domain_slots.py --reroll random_word
  python scripts/pick_domain_slots.py --reroll D1
  python scripts/pick_domain_slots.py --reroll D1 --exclude D1-03 D1-11

The --exclude flag takes anchor ids (shown as "id" in the output JSON, e.g.
D3-07) and prevents rerolls from drawing back an anchor already used or rejected
this round. Ids are stable and live in references/domains.json.

The domain anchor pool lives in references/domains.json so it can be extended
without touching code. SKILL.md should call this script and only read the
returned JSON, not the full pool.
"""
import argparse
import json
import pathlib
import random
import sys


DOMAINS_FILE = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "references" / "domains.json"


def _load_domains():
    try:
        with open(DOMAINS_FILE, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        sys.exit(f"domain pool not found: {DOMAINS_FILE}\n(it ships with the skill — restore references/domains.json)")
    except json.JSONDecodeError as e:
        sys.exit(f"domain pool is not valid JSON: {DOMAINS_FILE}\n{e}")
    for key in ("slot_names", "quotas", "pools"):
        if key not in doc:
            sys.exit(f"domain pool missing required key '{key}': {DOMAINS_FILE}")
    return doc


_DOC = _load_domains()
SLOT_NAMES = _DOC["slot_names"]
QUOTAS = _DOC["quotas"]
# POOLS: each row is the raw anchor dict (already carries its own stable "id").
POOLS = _DOC["pools"]


class PoolExhausted(Exception):
    """Raised when --exclude removes so many anchors a slot can't be filled.

    Carries a user-facing, actionable message; main() prints it via sys.exit
    instead of letting a raw traceback reach the model.
    """


def _import_sibling(name):
    """Import a sibling module by name. Handles renamed modules."""
    # Map old names to new names
    _name_map = {"search_char": "random_word"}
    actual = _name_map.get(name, name)
    import importlib
    return importlib.import_module(f".{actual}", package="wildidea.core")


def sample_pool(slot, n, exclude=None):
    banned = set(exclude or [])
    pool = POOLS.get(slot, [])
    candidates = [row for row in pool if row["id"] not in banned]
    if n > len(candidates):
        excluded_here = len(banned & {row["id"] for row in pool})
        raise PoolExhausted(
            f"槽位 {slot} 的锚点不够了：需要 {n} 条，排除 {excluded_here} 条后只剩 {len(candidates)} 条。\n"
            f"  这通常发生在连续多轮迭代、--exclude 累积太多时。\n"
            f"  办法：减少 --exclude 的 id 数量（少 ban 几条），或在 references/domains.json 的 {slot} 池里补充新锚点。"
        )
    picks = random.sample(candidates, n)
    return [{"slot": slot, "slot_name": SLOT_NAMES[slot], **row} for row in picks]


def pick_mao(exclude=None):
    # 毛选现在也是 references/domains.json 里的一个池（MAO-00..），所以直接走
    # sample_pool，天然支持 --exclude 和 PoolExhausted 兜底，存储与 D1-D4 统一。
    row = sample_pool("MAO", 1, exclude=exclude)[0]
    row["status"] = "picked"
    return row


def pick_random_word(exclude=None):
    # 随机组词没有固定池，exclude 是“本轮已用过的 query 文本”。重抽时换字直到
    # 组出一个没用过的词；多次仍撞上（极罕见）就放弃排除，不阻塞主流程。
    banned = set(exclude or [])
    search_char = _import_sibling("search_char")
    chars = search_char.load_chars()
    a = b = query = None
    for _ in range(50):
        a, b = search_char.pick_chars(chars)
        query = search_char.make_query(a, b)
        if query not in banned:
            break
    return {
        "slot": "RANDOM_WORD",
        "slot_name": SLOT_NAMES.get("RANDOM_WORD", "随机组词"),
        "chars": {"a": a, "b": b},
        "query": query,
        "status": "needs_search",
        "note": "Use current environment search, keep only real rules/events/boundaries.",
    }


def reroll(target, exclude=None):
    """Single entry point for rerolling one slot. target is mao/random_word/D1..D4."""
    if target == "mao":
        return pick_mao(exclude=exclude)
    if target == "random_word":
        return pick_random_word(exclude=exclude)
    if target in POOLS:
        return sample_pool(target, 1, exclude=exclude)[0]
    raise ValueError(f"unknown reroll target: {target} (use mao/random_word/D1/D2/D3/D4)")


def build_slots(problem_type, exclude=None):
    quota = QUOTAS[problem_type]
    slots = []
    for slot in ("D1", "D2", "D3", "D4"):
        n = quota.get(slot, 0)
        if n:
            slots.extend(sample_pool(slot, n, exclude=exclude))
    if quota.get("MAO"):
        slots.append(pick_mao(exclude=exclude))
    if quota.get("RANDOM_WORD"):
        slots.append(pick_random_word(exclude=exclude))
    random.shuffle(slots)
    return slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=sorted(QUOTAS), help="algorithm/research/product/strategy")
    parser.add_argument(
        "--reroll",
        help="Reroll a single slot instead of a full draw: mao/random_word/D1/D2/D3/D4",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="ID",
        help=(
            "Anchor ids already used/rejected this round, e.g. D1-03 or MAO-07 "
            "(skipped when redrawing). For 随机组词, pass the used query text to avoid repeats."
        ),
    )
    parser.add_argument("--seed", type=int, help="Optional deterministic seed")
    parser.add_argument("--stats", action="store_true", help="Only print pool counts")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.stats:
        print(json.dumps({k: len(v) for k, v in POOLS.items()}, ensure_ascii=False, indent=2))
        return

    if args.reroll:
        try:
            result = reroll(args.reroll, exclude=args.exclude)
        except PoolExhausted as e:
            sys.exit(str(e))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not args.type:
        parser.error("either --type or --reroll is required")

    try:
        slots = build_slots(args.type, exclude=args.exclude)
    except PoolExhausted as e:
        sys.exit(str(e))

    output = {
        "problem_type": args.type,
        "quota": QUOTAS[args.type],
        "slots": slots,
        "instruction": "Use only these sampled anchors for this run. Do not load the full domain pool.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
