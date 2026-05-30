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


DOMAINS_FILE = pathlib.Path(__file__).resolve().parent.parent / "references" / "domains.json"


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


def _import_sibling(name):
    script_dir = pathlib.Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    return __import__(name)


def sample_pool(slot, n, exclude=None):
    banned = set(exclude or [])
    pool = POOLS.get(slot, [])
    candidates = [row for row in pool if row["id"] not in banned]
    if n > len(candidates):
        excluded_here = len(banned & {row["id"] for row in pool})
        raise ValueError(
            f"not enough anchors in {slot}: need {n}, have {len(candidates)} "
            f"after excluding {excluded_here}"
        )
    picks = random.sample(candidates, n)
    return [{"slot": slot, "slot_name": SLOT_NAMES[slot], **row} for row in picks]


def pick_mao():
    pick_seed = _import_sibling("pick_seed")
    seed_id, text, hint = pick_seed.pick(1)[0]
    return {
        "slot": "MAO",
        "slot_name": "毛选",
        "seed_id": seed_id,
        "anchor": text,
        "mechanism_hint": hint,
        "status": "picked",
    }


def pick_random_word():
    search_char = _import_sibling("search_char")
    chars = search_char.load_chars()
    a, b = search_char.pick_chars(chars)
    query = search_char.make_query(a, b)
    return {
        "slot": "RANDOM_WORD",
        "slot_name": "随机组词",
        "chars": {"a": a, "b": b},
        "query": query,
        "status": "needs_search",
        "note": "Use current environment search, keep only real rules/events/boundaries.",
    }


def reroll(target, exclude=None):
    """Single entry point for rerolling one slot. target is mao/random_word/D1..D4."""
    if target == "mao":
        return pick_mao()
    if target == "random_word":
        return pick_random_word()
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
        slots.append(pick_mao())
    if quota.get("RANDOM_WORD"):
        slots.append(pick_random_word())
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
        help="Anchor ids already used/rejected this round, e.g. D1-03 (skipped when redrawing)",
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
        print(json.dumps(reroll(args.reroll, exclude=args.exclude), ensure_ascii=False, indent=2))
        return

    if not args.type:
        parser.error("either --type or --reroll is required")

    output = {
        "problem_type": args.type,
        "quota": QUOTAS[args.type],
        "slots": build_slots(args.type, exclude=args.exclude),
        "instruction": "Use only these sampled anchors for this run. Do not load the full domain pool.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
