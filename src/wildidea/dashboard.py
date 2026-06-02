"""Terminal dashboard for parallel execution."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from .style import _COLOR, cyan, green, yellow, red, dim, bold

_IS_WINDOWS = os.name == "nt"


@dataclass
class WorkerSlot:
    """State of one parallel worker."""
    index: int
    status: str = "idle"
    slot: str = ""
    domain: str = ""
    name: str = ""
    attempt: int = 0
    error: str = ""

    def render(self, width: int = 32) -> str:
        lines = []
        header = f"Worker {self.index + 1}"
        lines.append(f"┌{'─' * (width - 2)}┐")
        lines.append(f"│ {bold(header):<{width - 3}}│")
        lines.append(f"├{'─' * (width - 2)}┤")

        if self.status == "idle":
            status_str = dim("等待中...")
        elif self.status == "generating":
            status_str = yellow(f"▸ 生成中 [{self.slot}]")
        elif self.status == "done":
            status_str = green(f"✔ {self.name}")
        elif self.status == "fail":
            status_str = red(f"✗ {self.error[:20]}")
        else:
            status_str = dim(self.status)

        lines.append(f"│ {status_str:<{width - 3}}│")
        domain_str = dim(self.domain[:width - 4]) if self.domain else ""
        lines.append(f"│ {domain_str:<{width - 3}}│")
        if self.name and self.status == "done":
            lines.append(f"│ {self.name[:width - 4]:<{width - 3}}│")
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
        self._use_ansi = _COLOR and not _IS_WINDOWS

    def show(self):
        print(f"\n  {cyan('▸')} {bold('Parallel Execution')} ({self.n_workers} workers)")
        if self._use_ansi:
            self._render_cards()
        else:
            # Windows: just show initial state
            for w in self.workers:
                print(f"  Worker {w.index + 1}: {dim('等待中...')}")
        self._header_printed = True

    def _render_cards(self):
        card_width = 32
        rows = []
        for row_start in range(0, self.n_workers, self.cols):
            row_workers = self.workers[row_start:row_start + self.cols]
            card_lines = [w.render(card_width) for w in row_workers]
            for line_idx in range(len(card_lines[0])):
                row = ""
                for card in card_lines:
                    row += card[line_idx] + " "
                rows.append(row.rstrip())

        if self._lines_printed > 0:
            sys.stdout.write(f"\033[{self._lines_printed}A")

        for line in rows:
            print(f"\033[2K  {line}")
        self._lines_printed = len(rows)
        sys.stdout.flush()

    def update(self, worker_index: int, **kwargs):
        if not self._header_printed:
            return

        w = self.workers[worker_index]
        for k, v in kwargs.items():
            if hasattr(w, k):
                setattr(w, k, v)

        if self._use_ansi:
            self._render_cards()
        else:
            # Windows: print status line
            status = w.status
            if status == "generating":
                print(f"  Worker {w.index + 1}: {yellow('▸')} {w.slot} ({w.domain})")
            elif status == "done":
                print(f"  Worker {w.index + 1}: {green('✔')} {w.name}")
            elif status == "fail":
                print(f"  Worker {w.index + 1}: {red('✗')} {w.error[:40]}")

    def finish(self, total_ok: int, total_fail: int):
        print(f"\n  {green('✔')} {total_ok} succeeded, {red('✗')} {total_fail} failed\n")
