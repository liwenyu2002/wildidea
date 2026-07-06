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
6. **Live novelty audit**: use the agent's online search capability to check each mapped idea against existing products, papers, code, patents, and obvious nearest neighbors.
7. **Independent judging**: send candidates to an independent sub-agent judge for 6-dimension scoring; do not let the generator self-score standard results.
8. **HTML artifact**: generate and validate an `outputs/<topic>.html` card page before the final response.
9. **Output**: return the HTML path plus a concise summary of passed cards, search status, and judge status.

## Mandatory Standard Mode

Standard WildIdea runs have three non-negotiable requirements:

- **HTML is mandatory**: every standard run must create a validated `outputs/<topic>.html` artifact. A plain-text answer alone is not a standard WildIdea result.
- **Live search is mandatory**: use the current agent/runtime's web search or browser/search tool for novelty checking. `scripts/search_helper.py` is only a fallback helper, not a replacement for the agent's own online search capability. If no online search is available, ask the user to enable it or explicitly switch to a non-standard draft mode.
- **Independent scoring is mandatory**: standard results must be scored by an independent sub-agent/evaluator that did not generate the candidates. If the runtime cannot spawn a sub-agent, the run is non-standard and must be labeled as such.

## Slot Pool

Use `scripts/pick_domain_slots.py` as an internal helper when available. Read only the sampled JSON output, not the full domain pool, unless you are editing the pool itself.

- `D1`: algorithm / technical mechanisms
- `D2`: academic / scientific / engineering mechanisms
- `D3`: humanities / art / architecture / narrative mechanisms
- `D4`: product / interaction / business mechanisms
- `D5`: social / policy / governance mechanisms
- `MAO` or `D6`: 毛选-style contradiction, route, organization, and struggle methods
- `RANDOM_WORD` or `D7`: random word disruption

For product or strategy questions, prefer a mixed pool that includes `D2`, `D3`, `D4`, `D5`, `MAO`, and `RANDOM_WORD`.
For social simulation, policy, governance, city, welfare, or institutional-design questions, increase `D5`.
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

Use independent judging for every standard run. Prefer ideas with high domain distance, novelty, structural depth, and applicability.

## Detailed Spec

For the full workflow, output contracts, mandatory HTML/poster rules, mandatory search sidecar rules, and independent judging details, read:

- `docs/wildidea-skill.md`
- `references/search-integration.md` for every standard run, because live novelty/search evidence is mandatory
- `references/mechanism-transfer.md` for algorithm or research questions
- `references/poster-guide.md` for every standard run, because HTML output is mandatory
