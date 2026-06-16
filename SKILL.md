---
name: wildidea
description: Generate concrete cross-domain innovation ideas by forcing far-domain mechanisms into product, strategy, research, algorithm, design, or invention questions. Use when the user asks for WildIdea, idea generation, innovation directions, escaping conventional thinking, "他山之石", card-style inspiration, or mapping distant domain mechanisms back to a current problem. This is an agent skill workflow, not a user-facing CLI.
---

# WildIdea Skill v1.3

Use WildIdea as an agent workflow: deliberately draw a distant source mechanism, freeze it as "他山之石", abstract the transferable method, then map it back to the user's problem as a concrete implementable idea.

Do not treat WildIdea as a CLI product. The Python scripts in this repo are internal helpers for the agent to sample slots, search, and validate outputs. The user should experience a skill, not terminal instructions.

## Core Idea

Human first ideas usually stay inside the problem's familiar frame. WildIdea breaks that frame by injecting a far-away mechanism before solution writing begins.

Always preserve this order:

1. **Input**: capture the user's problem and any common solutions to avoid.
2. **Slot draw**: sample distant slots from the card pool.
3. **Source phenomenon**: identify the concrete outside-domain phenomenon, rule, event, or mechanism.
4. **Abstract method**: express the transferable method without target-domain terms.
5. **Mapping**: map the method back into the user's problem.
6. **Quality filter**: reject or reroll ideas that are conventional, self-justifying, or not implementable.
7. **Output**: show readable cards with source, method, solution, advantage, and optional risk/failure boundary.

## Slot Pool

Use `scripts/pick_domain_slots.py` as an internal helper when available. Read only the sampled JSON output, not the full domain pool, unless you are editing the pool itself.

- `D1`: algorithm / technical mechanisms
- `D2`: academic / scientific / engineering mechanisms
- `D3`: humanities / art / architecture / narrative mechanisms
- `D4`: product / interaction / business mechanisms
- `MAO` or `D6`: 毛选-style contradiction, route, organization, and struggle methods
- `RANDOM_WORD` or `D7`: random word disruption

For product or strategy questions, prefer a mixed pool that includes `D2`, `D3`, `D4`, `MAO`, and `RANDOM_WORD`.
For algorithm or research questions, increase `D1` and `D2`.

## Random Word Rule

Random word cards must not let the model freely invent a source mechanism from a meaningless word. First search or otherwise ground the word in a real result, phenomenon, rule, or event. If the search grounding is weak, reroll or explicitly mark it as weak instead of pretending it came from a real mechanism.

## Candidate Quality

A candidate is good only if:

- the outside source is concrete, not just a vague metaphor;
- the abstract method does not already contain the user's target-domain terms;
- the final solution says what data/materials are used, in what order, and what changes;
- it would still look non-obvious after removing the card title;
- it avoids repackaging the user's known/common solution.

Use independent judging when possible. Prefer ideas with high domain distance, novelty, structural depth, and applicability.

## Detailed Spec

For the full original workflow, output contracts, HTML/poster rules, search sidecar rules, and validation details, read:

- `docs/wildidea-skill.md`
- `references/search-integration.md` when online novelty/search evidence is needed
- `references/mechanism-transfer.md` for algorithm or research questions
- `references/poster-guide.md` only when the user asks for HTML/poster-style output
