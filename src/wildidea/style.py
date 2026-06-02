"""Terminal styling utilities. Zero dependencies — ANSI escape codes only."""
from __future__ import annotations

import sys


# ─── ANSI Colors ─────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"
_BG_DARK = "\033[48;5;236m"

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()


def _c(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if _COLOR else text


# ─── Public API ──────────────────────────────────────────────────────────────

def bold(text: str) -> str:
    return _c(_BOLD, text)

def dim(text: str) -> str:
    return _c(_DIM, text)

def red(text: str) -> str:
    return _c(_RED, text)

def green(text: str) -> str:
    return _c(_GREEN, text)

def yellow(text: str) -> str:
    return _c(_YELLOW, text)

def blue(text: str) -> str:
    return _c(_BLUE, text)

def cyan(text: str) -> str:
    return _c(_CYAN, text)

def magenta(text: str) -> str:
    return _c(_MAGENTA, text)


# ─── Components ──────────────────────────────────────────────────────────────

def banner(text: str):
    """Print a styled banner."""
    line = "─" * (len(text) + 4)
    print(f"\n{cyan('┌' + line + '┐')}")
    print(f"{cyan('│')}  {bold(text)}  {cyan('│')}")
    print(f"{cyan('└' + line + '┘')}\n")


def section(title: str):
    """Print a section header."""
    print(f"\n  {cyan('▸')} {bold(title)}")


def step(n: int, total: int, text: str):
    """Print a step indicator."""
    print(f"  {dim(f'[{n}/{total}]')} {text}")


def progress_bar(current: int, total: int, width: int = 30) -> str:
    """Render a progress bar."""
    filled = int(width * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = f"{current * 100 // total}%" if total > 0 else "0%"
    return f"  {cyan(bar)} {dim(pct)} {dim(f'({current}/{total})')}"


def score_line(label: str, value: float, threshold: float = 0, max_val: float = 10):
    """Print a score with color coding."""
    if value >= max_val * 0.8:
        color_fn = green
    elif value >= max_val * 0.5:
        color_fn = yellow
    else:
        color_fn = red

    score_str = f"{value:.1f}"
    if threshold > 0:
        status = green("✓") if value >= threshold else red("✗")
        print(f"    {label:<20} {color_fn(score_str):>8} {dim(f'/ {max_val}')}  {status} {dim(f'(≥ {threshold})')}")
    else:
        print(f"    {label:<20} {color_fn(score_str):>8} {dim(f'/ {max_val}')}")


def candidate_card(index: int, name: str, slot: str, source: str, scores: dict = None):
    """Print a candidate summary card."""
    slot_color = {
        "D1": blue, "D2": cyan, "D3": magenta,
        "D4": yellow, "MAO": red, "RANDOM_WORD": dim,
    }.get(slot, dim)

    score_str = ""
    if scores:
        sd = scores.get("structural_depth", 0)
        nv = scores.get("novelty", 0)
        score_str = f" {dim('SD:')}{green(str(sd)) if sd >= 7 else yellow(str(sd))} {dim('NV:')}{green(str(nv)) if nv >= 7 else yellow(str(nv))}"

    print(f"  {dim(f'{index:>2}.')} {slot_color(f'[{slot}]')} {bold(name)}{score_str}")
    print(f"      {dim(source)}")


def result_box(title: str, lines: list[str]):
    """Print a boxed result summary."""
    max_len = max(len(title), max(len(l) for l in lines)) + 4
    border = "─" * max_len

    print(f"\n  {cyan('╭' + border + '╮')}")
    print(f"  {cyan('│')}  {bold(title)}{' ' * (max_len - len(title) - 2)}{cyan('│')}")
    print(f"  {cyan('├' + border + '┤')}")
    for line in lines:
        padding = max_len - len(line) - 2
        print(f"  {cyan('│')}  {line}{' ' * max(0, padding)}{cyan('│')}")
    print(f"  {cyan('╰' + border + '╯')}\n")


def success(text: str):
    print(f"  {green('✔')} {text}")


def warn(text: str):
    print(f"  {yellow('⚠')} {text}")


def error(text: str):
    print(f"  {red('✖')} {text}")


def info(text: str):
    print(f"  {dim('ℹ')} {text}")
