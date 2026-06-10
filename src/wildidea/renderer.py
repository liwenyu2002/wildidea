"""HTML poster renderer. Fills templates/poster.html with candidate data."""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .judge import JudgeScores


@dataclass
class Candidate:
    name: str
    slot: str
    source: str
    proto: str
    desc: str
    fail: str
    advantage: str = ""
    scores: Optional[JudgeScores] = None
    reroll_count: int = 0
    quality_status: str = "passed"
    refund_credit: bool = False
    quality_note: str = ""


def _card_html(index: int, c: Candidate) -> str:
    """Build a single card <article> element."""
    scores_html = ""
    if c.scores:
        scores_html = (
            f'<div class="scores">'
            f'SD:{c.scores.structural_depth} DD:{c.scores.domain_distance} '
            f'NV:{c.scores.novelty} AP:{c.scores.applicability}'
            f"</div>"
        )
    advantage_html = f'<div class="advantage">{html.escape(c.advantage)}</div>' if c.advantage else ""

    return f"""<article class="card">
  <div class="id"><span>P{index:02d}</span><span class="slot">{html.escape(c.slot)}</span></div>
  <div class="source"><strong>{html.escape(c.source)}</strong></div>
  <div class="proto">{html.escape(c.proto)}</div>
  {advantage_html}
  <div class="name">{html.escape(c.name)}</div>
  <div class="desc">{html.escape(c.desc)}</div>
  <div class="fail">{html.escape(c.fail)}</div>
  {scores_html}
</article>"""


def render(
    candidates: list[Candidate],
    title: str,
    focus: str,
    template_path: Path,
    output_path: Path,
    ban_tags: Optional[list[str]] = None,
    stats: Optional[str] = None,
) -> Path:
    """Render candidates into an HTML poster.

    Args:
        candidates: List of Candidate objects (max 10).
        title: Poster title (problem summary).
        focus: Subtitle / focus description.
        template_path: Path to templates/poster.html.
        output_path: Where to write the output HTML.
        ban_tags: List of banned concept tags for the quarantine section.
        stats: Summary statistics string.

    Returns:
        Path to the written HTML file.
    """
    template = template_path.read_text(encoding="utf-8")

    # Build card rows (5 per row)
    cards_html = []
    for i, c in enumerate(candidates, 1):
        cards_html.append(_card_html(i, c))

    # Group into rows of 5
    rows = []
    for chunk_start in range(0, len(cards_html), 5):
        chunk = cards_html[chunk_start : chunk_start + 5]
        row_items = "\n    ".join(chunk)
        rows.append(f'<div class="cards">\n    {row_items}\n  </div>')
    card_rows = "\n  ".join(rows)

    # Meta HTML (stats)
    meta_html = ""
    if candidates:
        scores = [c.scores for c in candidates if c.scores]
        if scores:
            avg_sd = sum(s.structural_depth for s in scores) / len(scores)
            avg_nv = sum(s.novelty for s in scores) / len(scores)
            meta_html = f"""<div class="stats">
    <div class="stat"><b>{avg_sd:.1f}</b><span>Avg SD</span></div>
    <div class="stat"><b>{avg_nv:.1f}</b><span>Avg NV</span></div>
    <div class="stat"><b>{len(candidates)}</b><span>Candidates</span></div>
  </div>"""

    # Quarantine / ban section
    quarantine_html = ""
    if ban_tags:
        tags = "".join(f"<span>{html.escape(t)}</span>" for t in ban_tags)
        quarantine_html = f"""<div class="ban">
    <strong>Banned:</strong>
    <div class="tags">{tags}</div>
  </div>"""

    # Summary
    summary = ""
    if stats:
        summary = f'<div class="bottom"><span>{html.escape(stats)}</span><span class="footer">WildIdea</span></div>'

    # Fill template
    output = template
    replacements = {
        "{TITLE}": html.escape(title),
        "{BADGE_TEXT}": "WILDIDEA",
        "{FOCUS}": html.escape(focus),
        "{META_HTML}": meta_html,
        "{QUARANTINE_HTML}": quarantine_html,
        "{REJECTED_HTML}": "",
        "{CARD_ROWS}": card_rows,
        "{SUMMARY}": summary,
    }
    for placeholder, value in replacements.items():
        output = output.replace(placeholder, value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return output_path
