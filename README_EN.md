# WildIdea Skill

<a href="./README.md"><kbd>中文版</kbd></a>

WildIdea is a standalone Codex skill for generating cross-domain innovation ideas.

It does not start from the user's existing problem frame. It first draws a distant-domain source mechanism, freezes it as "他山之石", abstracts the transferable method, then maps that method back to the user's product, strategy, research, algorithm, or design problem.

## Version

- Skill: 1.3

## Install

Download or clone this repository, then copy the standalone skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

Start a new Codex chat and ask:

```text
Use $wildidea to generate cross-domain ideas for ...
```

## What Is Included

- `skill/wildidea/SKILL.md`: skill entrypoint
- `skill/wildidea/references/wildidea-skill.md`: full workflow spec
- `skill/wildidea/references/domains.json`: card pool
- `skill/wildidea/scripts/search_helper.py`: zero-key web search helper
- `skill/wildidea/scripts/pick_domain_slots.py`: slot sampler
- `skill/wildidea/templates/poster.html`: optional poster template

Users who want the networking/search version can download `skill/wildidea/` directly and use it without deploying anything else.

## Core Flow

1. Input the problem and common solutions to avoid.
2. Draw distant source mechanisms from the card pool.
3. Identify the source phenomenon.
4. Abstract a transferable method without target-domain terms.
5. Map the method back to the user's problem.
6. Filter or reroll weak ideas.
7. Return concrete idea cards.

## Project Layout

```text
skill/wildidea/           Standalone downloadable Codex skill
SKILL.md                  Root mirror of the skill entrypoint
docs/wildidea-skill.md    Root copy of the full skill workflow spec
```

## Local Validation

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/wildidea
```

## License

MIT
