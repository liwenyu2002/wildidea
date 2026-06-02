"""WildIdea CLI entry point.

Usage:
    wildidea configure                    # interactive setup
    wildidea generate "EEG情绪识别的创新方向"
    wildidea validate outputs/topic.html
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .style import (
    banner, section, step, score_line, candidate_card,
    result_box, success, warn, error, info, bold, dim, cyan, green, red,
)


def cmd_generate(args):
    """Run the WildIdea pipeline with styled output."""
    from .judge import JudgeConfig
    from .pipeline import Config, run

    banner(f"WildIdea v{__version__}")

    # Build judge config (use calibrated thresholds if available)
    judge_model = args.judge_model
    from .calibrate import get_calibrated_thresholds
    from .configure import get_config as _get_cfg
    _cfg = _get_cfg()
    sd_thr, sd_avg = get_calibrated_thresholds(judge_model, _cfg)
    judge_config = JudgeConfig(
        model=judge_model, provider=args.provider,
        api_key=args.api_key, base_url=args.base_url, proxy=args.proxy,
        sd_threshold=sd_thr, sd_avg_threshold=sd_avg,
    )

    config = Config(
        provider=args.provider, model=args.model,
        api_key=args.api_key, base_url=args.base_url, proxy=args.proxy,
        judge_config=judge_config,
        forbid_terms=args.forbid_proto_term or [],
        output_dir=Path(args.output_dir),
        search_enabled=not args.no_search,
    )

    section("Configuration")
    info(f"Model:  {bold(args.model)}")
    info(f"Judge:  {bold(judge_model)} (SD threshold: ≥ {sd_thr})")
    info(f"Search: {'enabled' if config.search_enabled else 'disabled'}")

    section("Generating candidates")

    def on_progress(event, data):
        if event == "type":
            info(f"Problem type: {bold(data['value'])}")
        elif event == "slots_done":
            info(f"Got {data['count']} domain slots")
        elif event == "generating":
            print(f"  {dim(f'[{data[\"done\"]}/10]')} Generating from {cyan(data['slot'])} ({dim(data['domain'])})...", end=" ", flush=True)
        elif event == "candidate_ok":
            print(f"{green('✔')} {bold(data['name'])}")
        elif event == "banned":
            print(f"{yellow('✗')} banned by search")
        elif event == "invalid":
            print(f"{yellow('✗')} {data['errors'][0][:40]}")
        elif event == "gen_fail":
            print(f"{red('✗')} {data['reason']}")
        elif event == "judging_start":
            section(f"Judging ({data['count']} candidates)")
        elif event == "judging":
            print(f"  {dim(f'[{data[\"index\"]}/{data[\"total\"]}]')} {data['name']}...", end=" ", flush=True)
        elif event == "judged":
            sd_str = green(str(data['sd'])) if data['sd'] >= sd_thr else yellow(str(data['sd']))
            print(f"SD={sd_str} NV={data['nv']}")
        elif event == "judge_fail":
            print(f"{red('FAIL')} {data['error'][:40]}")
        elif event == "eliminated":
            warn(f"Eliminated {data['count']} candidates below threshold")
        elif event == "rendered":
            success(f"HTML → {data['path']}")
        elif event == "error":
            error(data['message'])

    result = run(args.problem, config, on_progress=on_progress)

    if result.errors:
        for e in result.errors:
            error(e)
        return

    # Show candidates
    section(f"Candidates ({len(result.candidates)})")
    for i, c in enumerate(result.candidates, 1):
        scores_dict = {
            "structural_depth": c.scores.structural_depth,
            "novelty": c.scores.novelty,
        } if c.scores else None
        candidate_card(i, c.name, c.slot, c.source, scores_dict)

    # Show scores
    if result.avg_scores:
        section("Mapping Quality (Shen et al. 2026 G.6)")
        score_line("Structural Depth", result.avg_scores.get("structural_depth", 0), threshold=sd_avg)
        score_line("Domain Distance", result.avg_scores.get("domain_distance", 0))
        score_line("Novelty", result.avg_scores.get("novelty", 0))
        score_line("Applicability", result.avg_scores.get("applicability", 0))

    # Save JSON
    summary = {
        "problem": args.problem,
        "model": args.model,
        "judge_model": judge_model,
        "candidates": [
            {
                "name": c.name, "slot": c.slot, "source": c.source,
                "proto": c.proto, "desc": c.desc, "fail": c.fail,
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

    # Result summary
    result_box("Done", [
        f"HTML:  {result.html_path or 'N/A'}",
        f"JSON:  {json_path}",
        f"Candidates: {len(result.candidates)}",
    ])


def cmd_validate(args):
    """Validate an existing HTML poster."""
    from .core.validator import validate

    section(f"Validating {args.html}")
    errors = validate(Path(args.html), forbid_proto_terms=args.forbid_proto_term or [])

    if errors:
        for e in errors:
            error(e)
        return 1
    success("Poster is valid!")
    return 0


def _apply_config(args):
    """Apply saved config as defaults for generate command."""
    from .configure import get_config
    config = get_config()
    if not hasattr(args, "provider"):
        return
    if args.provider == "openrouter" and config.get("provider"):
        args.provider = config["provider"]
    if args.model == "anthropic/claude-sonnet-4.5" and config.get("model"):
        args.model = config["model"]
    if args.judge_model == "anthropic/claude-sonnet-4.5" and config.get("judge_model"):
        args.judge_model = config["judge_model"]
    if not args.api_key and config.get("api_key") and config["api_key"] != "__ENV__":
        args.api_key = config["api_key"]
    if not args.base_url and config.get("base_url"):
        args.base_url = config["base_url"]
    if not args.proxy and config.get("proxy"):
        args.proxy = config["proxy"]


def main():
    parser = argparse.ArgumentParser(
        prog="wildidea",
        description="Cross-domain mechanism transfer for innovation ideation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # --- configure ---
    cfg = sub.add_parser("configure", help="Interactive setup wizard")
    cfg.add_argument("--show", action="store_true", help="Show current config")
    cfg.add_argument("--reset", action="store_true", help="Reset config")

    # --- calibrate ---
    cal = sub.add_parser("calibrate", help="Calibrate judge model thresholds")
    cal.add_argument("--judge-model", help="Model to calibrate (uses config if omitted)")
    cal.add_argument("--provider", help="Provider for the judge model")
    cal.add_argument("--save", action="store_true", default=True, help="Save calibration to config")

    # --- generate ---
    gen = sub.add_parser("generate", help="Generate innovation candidates")
    gen.add_argument("problem", help="Problem statement")
    gen.add_argument("--type", dest="problem_type",
                     choices=["algorithm", "research", "product", "strategy"],
                     help="Problem type (auto-detected if omitted)")
    gen.add_argument("--provider", default="openrouter", help="LLM provider")
    gen.add_argument("--model", default="anthropic/claude-sonnet-4.5", help="Generation model")
    gen.add_argument("--api-key", help="API key")
    gen.add_argument("--base-url", help="Custom API base URL")
    gen.add_argument("--proxy", help="HTTP proxy URL")
    gen.add_argument("--judge-model", default="anthropic/claude-sonnet-4.5", help="Judge model")
    gen.add_argument("--forbid-proto-term", nargs="+", metavar="TERM", help="De-anchoring terms")
    gen.add_argument("--output-dir", default="outputs", help="Output directory")
    gen.add_argument("--no-search", action="store_true", help="Disable search dedup")

    # --- validate ---
    val = sub.add_parser("validate", help="Validate an HTML poster")
    val.add_argument("html", help="Path to HTML file")
    val.add_argument("--forbid-proto-term", nargs="+", metavar="TERM", help="De-anchoring terms")

    args = parser.parse_args()

    # Suppress logging when using styled output
    if not args.verbose:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "configure":
        from .configure import configure, show_config, reset_config
        if args.show:
            show_config()
        elif args.reset:
            reset_config()
        else:
            configure()
    elif args.command == "calibrate":
        from .calibrate import calibrate_judge, save_calibration
        from .configure import get_config
        cfg = get_config()
        provider = args.provider or cfg.get("provider", "openrouter")
        model = args.judge_model or cfg.get("judge_model", "anthropic/claude-sonnet-4.5")
        result = calibrate_judge(
            provider=provider, model=model,
            api_key=cfg.get("api_key"), base_url=cfg.get("base_url"), proxy=cfg.get("proxy"),
        )
        if args.save and "error" not in result:
            save_calibration(result)
    elif args.command == "generate":
        _apply_config(args)
        cmd_generate(args)
    elif args.command == "validate":
        sys.exit(cmd_validate(args))


if __name__ == "__main__":
    main()
