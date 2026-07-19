---
name: wildidea
description: Generate concrete cross-domain innovation ideas with an auditable red-team/blue-team workflow. Use when the user asks for WildIdea, idea generation, innovation directions, escaping conventional thinking, "他山之石", card-style inspiration, research-grade cross-domain analogies, adversarial idea vetting, or mapping distant mechanisms back to a product, strategy, research, algorithm, design, policy, or invention problem.
---

# WildIdea Skill v1.4

Run one unified WildIdea workflow. There is no separate fast Skill and Harness Skill: every standard run uses source-first structure mapping, independent judging, evidence-backed red-team attacks, blue-team survival/repair records, target-field novelty checking, and batch diversity control.

Do not expose Python helpers or a CLI as the product. The user should experience an idea-card workflow. Internal scripts and the repository harness may be used to execute it reliably.

## Non-Negotiable Order

1. Capture the problem and common solutions the user wants to avoid.
2. Detect `algorithm`, `research`, `product`, or `strategy`.
3. Build a solution-free `problem_card` with five plain-string keys: `actor`, `constraint`, `bottleneck_relation`, `desired_change`, `trade_off`.
4. Draw 9 distant source slots before proposing any target-domain solution.
5. Build the target problem relation graph once.
6. For each slot, freeze the concrete source phenomenon and build its source relation graph in an isolated context that never sees the target problem.
7. Align the two graphs by causal/functional relations, not by similar nouns. Compute or explicitly assess coverage and systematicity.
8. Write the card from that alignment: source phenomenon -> target-free abstract method -> mapped implementation.
9. Run the basic quality gate and an independent judge.
10. Run red-team attacks and record the blue-team outcome for every delivered card. A red-team kill is valid only with evidence.
11. Repair or reangle failed cards using the exact gate, judge, or red-team evidence; never blindly resample.
12. Ground passed cards with falsifiable candidate inferences, then run target-field novelty search when enabled.
13. After all slots finish, run Vendi-style semantic diversity plus solution-form diversity. Replace the most redundant card when fewer than roughly 6 distinct directions remain.
14. Render and validate the final HTML and search sidecar, then disclose problem-card coverage and red/blue outcomes.

Never begin with a conventional answer and decorate it with a distant-domain label afterward.

## Isolated Structure Mapping

Use separate contexts for these roles:

- `target_structurer`: sees only the problem and `problem_card`; produces a target relation graph without solutions.
- `base_structurer`: sees only the sampled source anchor; produces a source relation graph without any target vocabulary.
- `aligner`: receives both graphs and proposes node/edge correspondences by shared relation and topology.
- `card_writer`: receives the accepted alignment and writes the candidate; it must not invent unrelated mappings.

The base graph must contain concrete nodes, causal/functional edges, and any higher-order relation tying multiple edges together. Structural depth is high only when the mapped edge pairs remain linked by one shared higher-order relation. Multiple isolated noun matches are not systematicity.

When the repository runtime is present, `src/wildidea/harness` is the canonical internal orchestrator for this workflow. In a standalone Skill installation, reproduce the same role isolation with fresh sub-agents/evaluator contexts and use the bundled scripts for slot sampling, search records, and artifact validation.

## Red/Blue Contract

Every final visible card gets an adversarial dossier:

- `survived`: attacks that failed to kill the card and the concrete reason the mapping survived.
- `weaknesses`: the strongest remaining objections, ranked `minor`, `major`, or `fatal`.
- `fatal`: the evidence-backed attack that killed the candidate, when one exists.
- `judge_dims`: strongest and weakest scored dimensions with explanations.

Use at least these red-team lenses:

- **Structural killer**: construct a counter-mapping or a target implication that contradicts the proposal.
- **Naked test**: remove the source terminology and test whether only conventional advice remains.
- **Staleness detective**: when live search is available, find a direct target-field implementation or publication collision.

`kill = kill`; do not average a valid fatal attack away. But a kill must carry a counter-mapping, stripped-to-cliche text, citation, or direct implementation evidence. Unsupported dislike is only a weakness, not a kill.

Blue-team handling:

- If the attack fails, record why the card survived.
- If it exposes a repairable defect, inject the exact evidence into the next attempt.
- If it proves the mechanism is stale, malformed, unsupported, or merely conventional, reject it from passed/fallback eligibility as appropriate.

Read `references/red-blue-workflow.md` before every standard run.

## Retry And Quality Profiles

Each slot receives at most 3 total attempts:

1. **Fresh**: generate from the frozen source alignment.
2. **Repair**: carry forward the exact failed rule, judge dimension, or red-team evidence and rewrite only the affected fields.
3. **Reangle**: if the same defect repeats, keep the source anchor but choose a different causal-chain segment and rebuild the alignment angle.

Use these profiles:

- `pragmatic` (default): calibrated Structural Depth, `Novelty >= 7`, `Applicability >= 8`.
- `explore`: calibrated Structural Depth, `Novelty >= 7`, `Applicability >= 7`, plus `Domain Distance >= 7` or `Unexpectedness >= 8`.
- `research`: calibrated Structural Depth, `Novelty >= 8`, `Applicability >= 6`, `Domain Distance >= 7`.

If all attempts miss the judge but valid scored candidates remain, keep the highest mean of Structural Depth, Domain Distance, Novelty, and Applicability as `未达标保底`. If no attempt reaches the judge, keep the draft with the fewest quality-rule violations only when it is still structurally valid and search-confirmable. Never use malformed, unsupported, or direct-duplicate material as fallback.

## Slot Pool

Use `scripts/pick_domain_slots.py` and read only its sampled JSON unless editing the pool.

- `D1`: algorithm and technical mechanisms
- `D2`: academic, scientific, and engineering mechanisms
- `D3`: humanities, art, architecture, and narrative mechanisms
- `D4`: product, interaction, and business mechanisms
- `D5`: social, policy, governance, and institutional mechanisms
- `MAO`, displayed `D6`: 毛选 methods
- `RANDOM_WORD`, displayed `D7`: random-word disruption

Default quotas:

- `algorithm`: D1 x5, D2 x2, D3 x1, D6 x1
- `research`: D1 x4, D2 x2, D3 x1, D5 x1, D6 x1
- `product`: D1 x1, D2 x2, D3 x1, D4 x2, D5 x1, D6 x1, D7 x1
- `strategy`: D1 x1, D2 x2, D3 x1, D4 x1, D5 x2, D6 x1, D7 x1

Pool presets remain `default`, `social_policy`, `algorithm`, and `product`. Algorithm and research runs do not use random-word slots. Exclude completed cross-domain case studies by default to avoid double-hop analogies.

## Card Contract

Each candidate contains:

- a short, self-explanatory Chinese title;
- slot and specific source domain;
- `source_phenomenon`: a concrete source-world event, operation, rule, or constraint, mainly in Chinese;
- `proto`: a target-domain-free causal/conditional abstraction;
- `claimed_method`: a real existing method/algorithm/technique, or exactly `抽象概括（无真实具名对应）`;
- `relation_pairs`: 2-4 causal/functional source-target relation pairs derived from the alignment;
- `targets`: one primary `problem_card` key;
- `desc`: an operational implementation with no fixed word or sentence ceiling; use the detail the problem requires, naming the targeted gap, relevant facts and hard constraints, actors/resources, sequence, triggers, phases, visible/measurable output, and why it is hard to copy;
- `advantage`: plain language beginning with `这种方案的优势在于，`, preferably within 50 Chinese characters;
- `fail`: a concrete hidden premise or failure condition;
- the red/blue dossier described above.

Use the versioned `wildidea.candidate.v1` contract for every machine-readable
card artifact. Do not collapse it to a display summary: expose the source
fields, mapping fields, implementation and advantage, failure boundary, full
judge scores, quality/refund state, retry history, novelty result, grounding,
mapping, and adversarial dossier. This contract contains explicit product and
audit outputs only; never expose credentials, system prompts, or hidden model
reasoning.

For technical English, show the Chinese name first and only the necessary acronym in Chinese parentheses, such as `随机采样一致性（RANSAC）`.

Reject the card when removing the source mechanism leaves common sense, a renamed conventional fix, or vague “use X to improve Y” language.

## Search, Grounding, And Diversity

- Use real live search for every final candidate in standard mode. Local helpers are fallbacks, not substitutes for evidence.
- For algorithm/research novelty, use OpenAlex first and arXiv as fallback. For product/strategy, search public products, functions, patents, and cases.
- Judge only whether the claimed method is already used for this specific target problem; the method being famous in its source field is not a collision.
- When novelty checking is active and a collision is confirmed, redraw from a new source anchor up to the independent novelty-reroll limit.
- For passed cards, use reachable but unmapped source edges to propose a falsifiable target inference. Verify it as `confirmed`, `contradicted`, `untested_falsifiable`, or `untestable`.
- Run real Vendi Score when the harness runtime is available; otherwise use an explicit semantic-equivalence clustering fallback and disclose it. Also detect solution-form collapse, such as nine different mechanisms all becoming an app.

## Delivery Contract

Standard mode requires:

- fresh-context generator/judge/red-team separation;
- a red/blue dossier for every delivered card;
- real search evidence and `outputs/<topic>.search.json`;
- validated `outputs/<topic>.html`;
- disclosure of quality profile, pass/fallback/fail counts, distinct-direction count, problem-card coverage, and any budget/tool limitation.

If sub-agent isolation, live search, or artifact validation is unavailable, state exactly which step is blocked and ask before switching to a non-standard text draft. Never silently downgrade.

After the user selects one card, deepen that card with a minimal falsifiable experiment and a plan to test or avoid its `fail` premise. Do not deepen all nine unless requested.

## References

Read these before a standard run:

- `references/red-blue-workflow.md` for role isolation, attacks, dossier schema, grounding, state, and budget behavior;
- `references/wildidea-skill.md` for quotas, quality rules, retry semantics, and output contract;
- `references/search-integration.md` for evidence and novelty-search rules;
- `references/mechanism-transfer.md` for algorithm/research structure mapping and falsifiable experiments;
- `references/poster-guide.md` for HTML rendering and validation.
