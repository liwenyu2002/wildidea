"""WildIdea CLI entry point.

Usage:
    wildidea generate "EEG情绪识别的创新方向" --type research
    wildidea generate "相册App创新" --type product --provider openrouter --model anthropic/claude-sonnet-4.5
    wildidea validate outputs/topic.html --forbid-proto-term EEG 脑电
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__


def cmd_generate(args):
    """Run the WildIdea pipeline."""
    from .judge import JudgeConfig, get_thresholds
    from .pipeline import Config, run

    # Build judge config
    judge_model = args.judge_model
    sd_thr, sd_avg = get_thresholds(judge_model)
    judge_config = JudgeConfig(
        model=judge_model,
        provider=args.provider,
        api_key=args.api_key,
        base_url=args.base_url,
        proxy=args.proxy,
        sd_threshold=sd_thr,
        sd_avg_threshold=sd_avg,
    )

    config = Config(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        proxy=args.proxy,
        judge_config=judge_config,
        forbid_terms=args.forbid_proto_term or [],
        output_dir=Path(args.output_dir),
        search_enabled=not args.no_search,
    )

    result = run(args.problem, config)

    if result.errors:
        for e in result.errors:
            print(f"ERROR: {e}", file=sys.stderr)

    if result.html_path:
        print(f"\nHTML: {result.html_path}")

    if result.avg_scores:
        print(f"Scores: {json.dumps({k: round(v, 2) for k, v in result.avg_scores.items()}, ensure_ascii=False)}")

    print(f"Candidates: {len(result.candidates)}")

    # Save JSON summary
    summary = {
        "problem": args.problem,
        "model": args.model,
        "judge_model": judge_model,
        "candidates": [
            {
                "name": c.name,
                "slot": c.slot,
                "source": c.source,
                "proto": c.proto,
                "desc": c.desc,
                "fail": c.fail,
                "scores": {
                    "structural_depth": c.scores.structural_depth,
                    "domain_distance": c.scores.domain_distance,
                    "novelty": c.scores.novelty,
                    "applicability": c.scores.applicability,
                } if c.scores else None,
            }
            for c in result.candidates
        ],
        "avg_scores": result.avg_scores,
    }
    json_path = Path(args.output_dir) / f"{Path(result.html_path).stem if result.html_path else 'result'}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {json_path}")


def cmd_validate(args):
    """Validate an existing HTML poster."""
    from .core.validator import validate

    errors = validate(
        Path(args.html),
        forbid_proto_terms=args.forbid_proto_term or [],
    )

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("Poster is valid!")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="wildidea",
        description="WildIdea: Cross-domain mechanism transfer for innovation ideation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # --- generate ---
    gen = sub.add_parser("generate", help="Generate innovation candidates")
    gen.add_argument("problem", help="Problem statement")
    gen.add_argument("--type", dest="problem_type", choices=["algorithm", "research", "product", "strategy"],
                     help="Problem type (auto-detected if omitted)")
    gen.add_argument("--provider", default="openrouter",
                     help="LLM provider (openrouter/openai/ollama)")
    gen.add_argument("--model", default="anthropic/claude-sonnet-4.5",
                     help="LLM model for candidate generation")
    gen.add_argument("--api-key", help="API key (or set via env var)")
    gen.add_argument("--base-url", help="Custom API base URL")
    gen.add_argument("--proxy", help="HTTP proxy URL")
    gen.add_argument("--judge-model", default="anthropic/claude-sonnet-4.5",
                     help="Judge model for mapping quality evaluation")
    gen.add_argument("--forbid-proto-term", nargs="+", metavar="TERM",
                     help="Forbidden terms for de-anchoring (user domain terms)")
    gen.add_argument("--output-dir", default="outputs",
                     help="Output directory (default: outputs)")
    gen.add_argument("--no-search", action="store_true",
                     help="Disable search dedup")

    # --- validate ---
    val = sub.add_parser("validate", help="Validate an existing HTML poster")
    val.add_argument("html", help="Path to HTML file")
    val.add_argument("--forbid-proto-term", nargs="+", metavar="TERM",
                     help="Forbidden terms for de-anchoring")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "validate":
        sys.exit(cmd_validate(args))


if __name__ == "__main__":
    main()
