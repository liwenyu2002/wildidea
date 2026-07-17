<div align="center">

# WildIdea Skill

[![Skill](https://img.shields.io/badge/Skill-v1.4-6f42c1)](./skill/wildidea/SKILL.md)
[![Web](https://img.shields.io/badge/Web-v1.4-f6d365)](https://wildidea.wenyuli.site)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

[简体中文](./README.md) | [English](./README_EN.md)

**Inject distant-domain mechanisms into the problem space to generate farther, more concrete ideas.**

WildIdea is a standalone ideation skill for cross-domain thinking across product, strategy, research, algorithm, and design problems.

</div>

## Introduction

The first idea people see when facing a problem is often the least creative one.

WildIdea does not brainstorm inside the user's familiar problem frame. It first draws a source phenomenon from a distant-domain card pool, freezes it as "他山之石", abstracts the transferable method, and then maps that method back to the user's problem. This interrupts habitual answers and reduces the chance of repackaging old solutions as new ones.

## Web Version

WildIdea now has a web version: [wildidea.wenyuli.site](https://wildidea.wenyuli.site). Use it directly in the browser to draw, save, and share cross-domain idea cards without installing the local skill. New users receive 30 idea cards after registration.

<p align="center">
  <a href="https://wildidea.wenyuli.site">
    <img src="./docs/assets/wildidea-web-preview.png" alt="WildIdea web version preview" width="900">
  </a>
</p>

## Core Capabilities

| Capability | Description |
|---|---|
| Distant-domain draw | Samples mechanisms from algorithm, academic, humanities/art, product, Mao-style, and random-word pools |
| Source-first reasoning | Shows the source phenomenon before abstracting the transferable method |
| Isolated structure mapping | Separate roles graph the source mechanism and target problem before causal/functional alignment |
| Red/blue adversarial review | Every card receives evidence-backed attacks plus recorded survival reasons, weaknesses, or a fatal counterexample |
| Live novelty search | Uses OpenAlex, arXiv, or public web evidence to detect target-field collisions |
| Quality and diversity control | Independent judging, targeted repair, Vendi diversity, and solution-form checks constrain the batch |
| Auto-research ready | The `research` quality tier raises the novelty/domain-distance bar and relaxes immediate feasibility at generation time, screening for novel, implementable cross-domain ideas ready to feed an idea -> implementation -> benchmark pipeline |
| Standalone use | Download `skill/wildidea/` and use it directly without running extra services |

## Quick Start

Paste the instruction below into your agent and send it. The agent will install this skill automatically:

```bash
curl -fsSL https://raw.githubusercontent.com/liwenyu2002/wildidea/main/scripts/install.sh | bash
```

After installation, you can say to your agent:

```text
Use wildidea to help me answer: how should I design a photo album app?
```

## Workflow

1. Structure the problem and build its target relation graph.
2. Draw a distant source and build its source graph in an isolated context.
3. Align the graphs and generate from the shared causal structure.
4. Run an independent judge and evidence-backed red-team attacks.
5. Record blue-team survival reasons or inject counterevidence into targeted repair.
6. Run target-field novelty, falsifiable inference, and batch-diversity checks.
7. Return idea cards with red/blue dossiers and validated HTML.

## What Is Included

| Path | Purpose |
|---|---|
| `skill/wildidea/SKILL.md` | Skill entrypoint |
| `skill/wildidea/references/wildidea-skill.md` | Full workflow spec |
| `skill/wildidea/references/red-blue-workflow.md` | Red/blue roles, evidence gates, and audit dossier |
| `skill/wildidea/references/domains.json` | Card pool data |
| `skill/wildidea/scripts/search_helper.py` | Zero-key web search helper |
| `skill/wildidea/scripts/pick_domain_slots.py` | Slot sampler |
| `skill/wildidea/templates/poster.html` | Optional poster template |
| `scripts/install.sh` | One-command installer |

## Local Validation

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py skill/wildidea
```

## License

MIT
