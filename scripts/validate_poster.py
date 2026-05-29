#!/usr/bin/env python3
"""Validate WildIdea poster HTML output.

Usage:
  python scripts/validate_poster.py outputs/example.html
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_CARD_CLASSES = ("slot", "source", "proto", "name", "desc", "fail")
FORBIDDEN_CLASS_NAMES = (
    "anchor",
    "match",
    "badge-row",
    "insight",
    "container",
    "its-says",
    "you-try",
)


def class_regex(class_name: str) -> re.Pattern[str]:
    return re.compile(rf'class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\']')


def validate(path: Path, expected_cards: int = 10) -> list[str]:
    errors: list[str] = []

    if not path.exists():
        return [f"file not found: {path}"]

    text = path.read_text(encoding="utf-8")

    placeholders = sorted(set(re.findall(r"\{[A-Z_]+\}", text)))
    if placeholders:
        errors.append("unreplaced placeholders: " + ", ".join(placeholders))

    cards = re.findall(
        r"<article\b[^>]*class=[\"'][^\"']*\bcard\b[^\"']*[\"'][^>]*>.*?</article>",
        text,
        flags=re.S | re.I,
    )
    if len(cards) != expected_cards:
        errors.append(f"expected {expected_cards} cards, found {len(cards)}")

    for index, card in enumerate(cards, start=1):
        missing = [name for name in REQUIRED_CARD_CLASSES if not class_regex(name).search(card)]
        if missing:
            errors.append(f"card {index} missing classes: {', '.join(missing)}")

    if not re.search(r'class=["\'][^"\']*\bban\b[^"\']*\brejected\b[^"\']*["\']', text):
        errors.append("missing .ban.rejected section")

    for class_name in FORBIDDEN_CLASS_NAMES:
        if class_regex(class_name).search(text):
            errors.append(f"forbidden old class present: {class_name}")

    if "aspect-ratio" in text:
        errors.append("fixed aspect-ratio is not allowed")

    forbidden_overflow = re.search(
        r"\.(slide|card)\s*\{[^}]*overflow\s*:\s*hidden",
        text,
        flags=re.S,
    )
    if forbidden_overflow:
        errors.append("overflow:hidden is not allowed on .slide or .card")

    for class_name in ("proto", "desc", "fail"):
        block = re.search(rf"\.{class_name}\s*\{{(?P<body>[^}}]*)\}}", text, flags=re.S)
        if not block:
            errors.append(f"missing CSS block: .{class_name}")
            continue
        css = block.group("body")
        if "word-break: break-word" not in css or "overflow-wrap: break-word" not in css:
            errors.append(f".{class_name} missing word-break/overflow-wrap guard")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", help="Path to generated WildIdea HTML")
    parser.add_argument("--cards", type=int, default=10, help="Expected card count")
    args = parser.parse_args()

    errors = validate(Path(args.html), args.cards)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print("Poster is valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
