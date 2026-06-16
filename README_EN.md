<div align="center">

# WildIdea Skill

[![Skill](https://img.shields.io/badge/Codex%20Skill-v1.3-6f42c1)](./skill/wildidea/SKILL.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

[简体中文](./README.md) | [English](./README_EN.md)

**Inject distant-domain mechanisms into the problem space to generate farther, more concrete ideas.**

WildIdea is a standalone Codex skill for cross-domain ideation across product, strategy, research, algorithm, and design problems.

</div>

## Introduction

The first idea people see when facing a problem is often the least creative one.

WildIdea does not brainstorm inside the user's familiar problem frame. It first draws a source phenomenon from a distant-domain card pool, freezes it as "他山之石", abstracts the transferable method, and then maps that method back to the user's problem. This interrupts habitual answers and reduces the chance of repackaging old solutions as new ones.

## Core Capabilities

| Capability | Description |
|---|---|
| Distant-domain draw | Samples mechanisms from algorithm, academic, humanities/art, product, Mao-style, and random-word pools |
| Source-first reasoning | Shows the source phenomenon before abstracting the transferable method |
| Web search helper | Includes a zero-key search helper for random-word grounding and basic novelty checks |
| Quality filtering | Constrains structural depth, domain distance, novelty, and applicability; weak candidates can be redrawn |
| Standalone use | Download `skill/wildidea/` and use it directly without running extra services |

## Quick Start

Download or clone this repository, then copy the standalone skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

Start a new Codex chat and ask:

```text
Use $wildidea to generate cross-domain ideas for how to make a fresh photo album app
```

## Workflow

1. Input the problem and common solutions to avoid.
2. Draw source mechanisms from distant-domain card pools.
3. Identify the concrete source phenomenon.
4. Abstract a transferable method without target-domain terms.
5. Map the method back to the user's problem.
6. Filter or redraw weak candidates.
7. Return concrete idea cards.

## What Is Included

| Path | Purpose |
|---|---|
| `skill/wildidea/SKILL.md` | Skill entrypoint |
| `skill/wildidea/references/wildidea-skill.md` | Full workflow spec |
| `skill/wildidea/references/domains.json` | Card pool data |
| `skill/wildidea/scripts/search_helper.py` | Zero-key web search helper |
| `skill/wildidea/scripts/pick_domain_slots.py` | Slot sampler |
| `skill/wildidea/templates/poster.html` | Optional poster template |

## Local Validation

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/wildidea
```

## License

MIT
