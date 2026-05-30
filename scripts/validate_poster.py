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

# Slot names that must NOT appear as a card's `.source` — the source has to be a
# concrete mechanism (e.g. "Hyperband"), not the bucket label. Keep in sync with
# SLOT_NAMES in pick_domain_slots.py plus the 毛选/随机组词 buckets.
SLOT_LABELS = (
    "算法技术",
    "学术机制",
    "人文艺术",
    "产品机制",
    "毛选",
    "随机组词",
)

# Verbatim placeholder/example strings from templates/poster.html and
# references/poster-guide.md. If any survive into output, the card was not
# actually filled in.
TEMPLATE_SAMPLE_TEXT = (
    "候选机制名",
    "映射到用户领域前冻结出的通用操作机制",
    "用户领域怎么干（通俗展开）：把做法写成读者脑中能出现画面的",
    "如果这个现象没有发生，说明方向不成立",
    "映射到用户领域之前最后冻结出的通用机制",
)


def text_of(class_name: str, card: str) -> str:
    """Return the inner text of the first element with class_name in card, tags stripped.

    The body runs from the opening tag to the next sibling field (another
    class="..." div) or the end of the card, so nested inline tags like
    <strong>...</strong> inside the element are included, not truncated at the
    first </tag>.
    """
    open_tag = re.search(
        rf'<[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>',
        card,
        flags=re.I,
    )
    if not open_tag:
        return ""
    rest = card[open_tag.end():]
    # stop at the next field's opening div, or the card/section close
    stop = re.search(r'<div\b[^>]*class=|</article>|</section>', rest, flags=re.I)
    body = rest[: stop.start()] if stop else rest
    inner = re.sub(r"<[^>]+>", "", body)
    return re.sub(r"\s+", " ", inner).strip()


def class_regex(class_name: str) -> re.Pattern[str]:
    return re.compile(rf'class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\']')


def validate(path: Path, expected_cards: int = 10, forbid_proto_terms=None, cards_explicit=True) -> list[str]:
    errors: list[str] = []
    forbid_proto_terms = forbid_proto_terms or []

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
        hint = ""
        if cards_explicit is False and len(cards) < expected_cards:
            hint = f" (if this is a 精简/极端/一杀 run, pass --cards {len(cards)})"
        errors.append(f"expected {expected_cards} cards, found {len(cards)}{hint}")

    for index, card in enumerate(cards, start=1):
        missing = [name for name in REQUIRED_CARD_CLASSES if not class_regex(name).search(card)]
        if missing:
            errors.append(f"card {index} missing classes: {', '.join(missing)}")
            continue

        # .slot must carry a real slot number D1–D6, not be an empty label (问题3).
        slot_text = text_of("slot", card)
        if not re.search(r"\bD[1-6]\b", slot_text):
            errors.append(f"card {index}: .slot must name a slot D1–D6, got {slot_text!r}")

        # Candidate-contract content checks (SKILL.md "Candidate Contract").
        source = text_of("source", card)
        # strip a leading "来源：" / "来源:" label if present
        source_val = re.sub(r"^来源\s*[:：]\s*", "", source)
        if not source_val:
            errors.append(f"card {index}: empty .source (must name a concrete mechanism)")
        elif source_val in SLOT_LABELS:
            errors.append(
                f"card {index}: .source is the slot label '{source_val}', not a concrete source"
            )

        for cls in ("name", "proto", "desc", "fail"):
            body = text_of(cls, card)
            for sample in TEMPLATE_SAMPLE_TEXT:
                if sample in body:
                    errors.append(f"card {index}: .{cls} still contains template sample text")
                    break

        proto = text_of("proto", card)
        for term in forbid_proto_terms:
            if term and term in proto:
                errors.append(
                    f"card {index}: .proto leaks user-domain term '{term}' "
                    f"(source prototype must be domain-free)"
                )

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
    parser.add_argument("--cards", type=int, default=None, help="Expected card count (default 10)")
    parser.add_argument(
        "--forbid-proto-term",
        nargs="*",
        default=[],
        metavar="TERM",
        help="User-domain terms that must NOT appear in any .proto (de-anchoring guard)",
    )
    args = parser.parse_args()

    cards_explicit = args.cards is not None
    errors = validate(
        Path(args.html),
        args.cards if cards_explicit else 10,
        forbid_proto_terms=args.forbid_proto_term,
        cards_explicit=cards_explicit,
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print("Poster is valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
