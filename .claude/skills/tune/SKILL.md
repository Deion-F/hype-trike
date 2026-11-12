---
name: tune
description: Run the difficulty-tuner subagent on Hype Trike. It reviews race recordings and AI sims, tunes track generation, CPU rival difficulty and the player controls, archives the recordings it used, and logs the pass. Use when the user types /tune or asks to tune or balance difficulty.
argument-hint: "[focus, e.g. 'final heat feels too hard' or 'classic mode only']"
---

Launch the `difficulty-tuner` subagent (defined in `.claude/agents/difficulty-tuner.md`)
with the Agent tool, `subagent_type: "difficulty-tuner"`. Don't do the tuning yourself.

Prompt to give it:

> Run a full tuning pass following your workflow: summary and report on the
> live recordings, inspect the worst races, baseline sim, small changes,
> re-sim, then check the player controls and tune them if the evidence
> points there, run the tests, archive the recordings you used, and log the pass in
> docs/tuning_log.md and DECISIONS.md. Don't commit.
>
> Focus from the user: $ARGUMENTS

If `$ARGUMENTS` is empty, leave out the "Focus from the user" line.

If `difficulty-tuner` isn't an available agent type (agent files load at session
start), use `subagent_type: "general-purpose"` with `model: "sonnet"` instead, and
put the body of `.claude/agents/difficulty-tuner.md` (everything after the
frontmatter) before the prompt above, so it follows the same instructions.

When it reports back, relay its summary to the user: what the data showed, the
changes (with file links, control changes called out separately so the user can veto them), the learning row before/after, test status, the
archive folder, and its open questions. The user can't see the agent's report,
so include everything that matters. Don't commit.
