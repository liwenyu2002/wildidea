"""Terminal dashboard for parallel execution. ANSI cursor-based live updates."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

from .style import _COLOR, cyan, green, yellow, red, dim, bold


@dataclass
class WorkerSlot:
    """State of one parallel worker."""
    index: int
    status: str = "idle"      # idle, generating, searching, validating, done, fail
    slot: str = ""
    domain: str = ""
    name: str = ""
    attempt: int = 0
    error: str = ""

    def render(self, width: int = 32) -> str:
        """Render one card as a list of strings."""
        lines = []
        # Header
        header = f"Worker {self.index + 1}"
        lines.append(f"┌{'─' * (width - 2)}┐")
        lines.append(f"│ {bold(header):<{width - 3}}│")
        lines.append(f"├{'─' * (width - 2)}┤")

        # Status line
        if self.status == "idle":
            status_str = dim("等待中...")
        elif self.status == "generating":
            status_str = yellow(f"▸ 生成中 [{self.slot}]")
        elif self.status == "searching":
            status_str = cyan("▸ 查重中...")
        elif self.status == "done":
            status_str = green(f"✔ {self.name}")
        elif self.status == "fail":
            status_str = red(f"✗ {self.error[:20]}")
        else:
            status_str = dim(self.status)

        # Truncate if too long
        visible_len = len(status_str) - len(self.status) + len(self.status)  # approximate
        lines.append(f"│ {status_str:<{width - 3}}│")

        # Domain line
        if self.domain:
            domain_str = dim(self.domain[:width - 4])
            lines.append(f"│ {domain_str:<{width - 3}}│")
        else:
            lines.append(f"│{'':>{width - 1}}│")

        # Name line (if done)
        if self.name and self.status == "done":
            name_str = self.name[:width - 4]
            lines.append(f"│ {name_str:<{width - 3}}│")
        else:
            lines.append(f"│{'':>{width - 1}}│")

        lines.append(f"└{'─' * (width - 2)}┘")
        return lines


class Dashboard:
    """Live terminal dashboard for parallel workers."""

    def __init__(self, n_workers: int, cols: int = 3):
        self.n_workers = n_workers
        self.cols = min(cols, n_workers)
        self.workers = [WorkerSlot(index=i) for i in range(n_workers)]
        self._lines_printed = 0
        self._header_printed = False

    def _card_height(self) -> int:
        return 6  # top + header + separator + status + domain/name + bottom

    def _render_row(self, row_workers: list[WorkerSlot], card_width: int = 32) -> list[str]:
        """Render one row of cards side by side."""
        card_lines = [w.render(card_width) for w in row_workers]
        # Interleave lines from each card
        result = []
        for line_idx in range(len(card_lines[0])):
            row = ""
            for card in card_lines:
                row += card[line_idx] + " "
            result.append(row.rstrip())
        return result

    def show(self):
        """Initial render of all cards."""
        if not _COLOR:
            return  # Skip in non-color terminals

        card_width = 32
        rows = []
        for row_start in range(0, self.n_workers, self.cols):
            row_workers = self.workers[row_start:row_start + self.cols]
            rows.extend(self._render_row(row_workers, card_width))

        # Print header
        print(f"\n  {cyan('▸')} {bold('Parallel Execution')} ({self.n_workers} workers)")
        for line in rows:
            print(f"  {line}")
        self._lines_printed = len(rows) + 1  # +1 for header
        self._header_printed = True

    def update(self, worker_index: int, **kwargs):
        """Update a worker's state and re-render."""
        if not _COLOR or not self._header_printed:
            return

        w = self.workers[worker_index]
        for k, v in kwargs.items():
            if hasattr(w, k):
                setattr(w, k, v)

        # Move cursor up and re-render
        card_width = 32
        rows = []
        for row_start in range(0, self.n_workers, self.cols):
            row_workers = self.workers[row_start:row_start + self.cols]
            rows.extend(self._render_row(row_workers, card_width))

        # Move cursor up
        if self._lines_printed > 0:
            sys.stdout.write(f"\033[{self._lines_printed}A")

        # Re-print header + cards
        print(f"\r  {cyan('▸')} {bold('Parallel Execution')} ({self.n_workers} workers)")
        for line in rows:
            # Clear line first
            print(f"\033[2K  {line}")
        self._lines_printed = len(rows) + 1

        sys.stdout.flush()

    def finish(self, total_ok: int, total_fail: int):
        """Print summary after all workers done."""
        if not _COLOR:
            return
        print(f"\n  {green('✔')} {total_ok} succeeded, {red('✗')} {total_fail} failed\n")
