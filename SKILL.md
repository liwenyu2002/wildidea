---
name: wildidea
description: Generate concrete cross-domain innovation ideas by forcing far-domain mechanisms into product, strategy, research, algorithm, design, or invention questions. Use when the user asks for WildIdea, idea generation, innovation directions, escaping conventional thinking, "他山之石", card-style inspiration, or mapping distant domain mechanisms back to a current problem. This is an agent skill workflow, not a user-facing CLI.
---

# WildIdea Skill v1.3

Run WildIdea as an agent workflow. Draw a distant source first, freeze its concrete phenomenon and transferable method, then map that method back to the user's problem as an implementable proposal.

Do not expose the internal Python helpers as the product. The user should experience an idea-card workflow.

## Core Order

Always preserve this order:

1. Capture the problem and the user's common solutions to avoid.
2. Detect `algorithm`, `research`, `product`, or `strategy`.
3. Restate the problem as a `problem_card` before drawing any slot: five plain-string keys `actor`, `constraint`, `bottleneck_relation`, `desired_change`, `trade_off`. This step only structures the problem itself; it must not contain a solution.
4. Draw source slots before writing any target-domain solution.
5. Freeze the concrete source phenomenon as `他山之石`.
6. Abstract a target-domain-free method from that phenomenon.
7. Map the method into a concrete proposal in the user's domain, checked against the `problem_card`.
8. Run basic readability and actionability checks.
9. Send the candidate to an independent judge, who also checks the mapping against the `problem_card`.
10. Reroll that slot when it misses the quality gate, subject to the retry limit.
11. Run live novelty search, render the final HTML, validate it, and return its path.
12. After all 9 slots finish, audit `problem_card` coverage across the 9 cards' declared target keys and disclose any key none of them targeted.

Never start from a conventional answer and decorate it with a distant-domain name afterward.

## Problem Card

Before drawing slots, restate the user's problem as a `problem_card`: `actor` (who is stuck), `constraint` (what currently limits them), `bottleneck_relation` (the relation/link that is jammed), `desired_change` (the change they want), `trade_off` (the trade-off they must choose between). All five are plain strings describing the problem, not a solution.

- `problem_card` only structures the problem; it must never contain a mechanism name, target-domain conventional fix, or any proposal.
- Every card's mapping step and the independent judge must check the candidate against `problem_card`, not just against the raw problem text.
- Each card's `desc` must open by declaring which single key it primarily targets (see Card Contract).
- After the 9 slots finish, tally which of the five keys were actually targeted by at least one card. Disclose any key that no card touched — do not silently omit it.

This does not conflict with mechanism-transfer.md's rule that source-domain freezing must not look at the target domain: `problem_card` structures the problem side only, before any source mechanism is chosen, and produces no solution.

## Web-Parity Contract

Match the current Web v1.4 generation logic unless the user explicitly requests a different count or mode:

- Draw **9 cards by default**. Treat 9 as the normal maximum for one run.
- Generate and judge each slot independently. A completed card may be reported immediately; do not wait for every other slot before acknowledging it.
- Give each slot at most **3 total attempts**: the initial attempt plus at most **2 rerolls**.
- The quality gate has two tiers, selected by `risk_profile`; default to `pragmatic` unless the user asks to go wilder/explore.
  - `pragmatic` (default): `Structural Depth` reaches the judge-model-calibrated threshold, `Novelty >= 7`, and `Applicability >= 9`.
  - `explore`: `Structural Depth` reaches the same threshold, `Novelty >= 7`, `Applicability >= 7`, and at least one of `Domain Distance >= 7` or `Unexpectedness >= 8`.
  - Switch to `explore` when the user says things like "更野"/"探索模式"/wilder/explore mode, and disclose which tier was actually used when delivering results.
- If no attempt passes after 3 tries but at least one valid, scored, search-confirmable candidate remains, keep the eligible attempt with the highest mean of `Structural Depth`, `Domain Distance`, `Novelty`, and `Applicability`. Mark it `未达标保底`; do not describe it as passed.
- A malformed candidate, unsupported source, or confirmed direct duplicate is not eligible as a fallback. If every attempt is unusable, retain a failed slot instead of inventing a result.
- Do not keep drawing indefinitely until 9 cards pass. Preserve the 9 original slot outcomes so the user can see where quality gates failed.
- The Web product refunds a failed/fallback card. The standalone Skill has no credit ledger, so preserve the quality label but do not claim that money or credits were refunded.

## Slot Pool

Use `scripts/pick_domain_slots.py` and read only its sampled JSON. Do not load the full pool unless editing it.

- `D1`: algorithm and technical mechanisms
- `D2`: academic, scientific, and engineering mechanisms
- `D3`: humanities, art, architecture, and narrative mechanisms
- `D4`: product, interaction, and business mechanisms
- `D5`: social, policy, governance, and institutional mechanisms
- `MAO` / displayed `D6`: 毛选 methods
- `RANDOM_WORD` / displayed `D7`: random-word disruption

Supported pool modes mirror the website:

- `default`: use the problem-type quota from `references/domains.json`
- `social_policy`: 9 x `D5`
- `algorithm`: 9 x `D1`
- `product`: 9 x `D4`

Use `--pool-mode <mode>` when the user selects a preset. Keep D numbers tied to the top-level pool; use the adjacent domain label for the specific discipline.

By default, exclude anchors already marked as a completed cross-domain mapping (a finished, packaged case study) — reusing one risks a double-hop analogy that just borrows someone else's existing packaging. Only include them when the user explicitly asks to go wilder, via `--include-completed-analogies`, and disclose that they were included.

## Card Contract

Each candidate must contain:

- a short Chinese title;
- the slot number and specific source domain;
- `source_phenomenon`: a concrete source-world event, rule, operation, or constraint, written mainly in Chinese;
- `proto`: the abstract transferable method, containing no target-domain terms;
- `desc`: 2-4 operational sentences, opening with which `problem_card` key this card primarily targets, then naming inputs/materials, action order, trigger, resulting change, and a visible or measurable output;
- `advantage`: a plain-language sentence beginning with `这种方案的优势在于，`, preferably within 50 Chinese characters;
- `fail`: a concrete hidden premise or failure condition, retained as internal/detail metadata even when the compact card hides it.

For technical English terms, show the Chinese name first and place only the necessary acronym in Chinese parentheses, such as `随机采样一致性（RANSAC）`.

Reject a candidate when removing the source mechanism leaves only industry common sense, a renamed conventional solution, or a vague "use X to improve Y" sentence.

## Random Word Rule

Keep the sampled word as the source. Ground it with a real search result before extracting an operation or rule. Do not silently replace it with an unrelated natural or scientific mechanism. If grounding is weak, reroll or fail the slot.

`RANDOM_WORD` slots do not use the 6-dimension structural-mapping score. Judge them with the dedicated `judge_random_word.txt` template instead, on 4 dimensions (0-10 each): `chain_clarity`, `actionability`, `novelty`, `unexpectedness`. Pass line: `chain_clarity >= 6` and `actionability >= 6` and `novelty >= 7` (an initial, uncalibrated bar).

## Standard-Mode Requirements

The standalone Skill preserves the web quality gate and adds stricter execution evidence:

- **Live search**: use the current agent's online search capability for every final candidate. Search products, papers, code, patents, datasets, or nearest neighbors as appropriate. Local helpers are fallback utilities, not substitutes for real online search.
- **Independent judge isolation**: the website already uses a separate judge call; the Skill must additionally keep that judge in a fresh sub-agent/evaluator context. The generator must not self-score. Retain all 6 dimensions: Structural Depth, Domain Distance, Applicability, Novelty, Unexpectedness, and Non-Obviousness — except `RANDOM_WORD` slots, which use the separate 4-dimension judge described in Random Word Rule.
- **Validated HTML**: create `outputs/<topic>.html` plus the search sidecar and validate the artifact before replying.

If one of these capabilities is unavailable, say exactly which standard step is blocked or switch only with the user's explicit permission to a non-standard quick/text draft. Never silently downgrade.

## Deepen (Optional Stage Two)

After the user picks one delivered card for a closer look, produce a deepen artifact for that single card instead of drawing a new slot:

- A minimal falsifiable experiment: a control/comparison object plus a concrete criterion for what would count as failure. Reuse the `最小可证伪实验` field spec already defined in `references/mechanism-transfer.md` — that spec is domain-general, not exclusive to algorithm/research cards; apply it to product, strategy, and design cards too.
- Verification-or-avoidance steps for the card's `fail` field: how to check whether the hidden failure premise actually holds for the user's situation, and what to do if it does (mitigate, substitute, or narrow scope).
- Keep this stage optional and per-card. Do not run it for all 9 cards unless the user explicitly asks for that.

## Detailed Spec

Read the following before a standard run:

- `references/wildidea-skill.md` when present in the installed package; otherwise `docs/wildidea-skill.md` in the source checkout
- `references/search-integration.md`
- `references/mechanism-transfer.md` for algorithm or research questions, and for its `最小可证伪实验` field spec reused by Deepen on any problem type
- `references/poster-guide.md`
