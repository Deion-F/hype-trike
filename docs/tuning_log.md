# Difficulty tuning log

One entry per tuning pass (newest first), written by the `difficulty-tuner`
agent (`.claude/agents/difficulty-tuner.md`) or by hand. Each pass names the
recordings it used. Those are archived under `recordings/archive/<stamp>/`.

Tools: `tools/tuning.py summary | report | show | sim | archive`.

<!-- entries below -->

## 2026-11-12 - pass 2

- Recordings: 16 live one-button valley/scrambler run races (heats 1-3: 6/6/4), archived to `recordings/archive/20261112-135928/`. Settings: mouse_steer angle, hover lanes, wheelie ramps, swipe lane mode.
- User focus: (a) in-air leaning feels finicky, (b) early ramps launch you into another ramp, (c) placing targets top 3 / top 2 / win per map.
- Evidence: target-met heat1 100%, heat2 83%, heat3 0% (4 races, all P4, gap 16 s, 2 blow-ups per race on the "Hot Engine" modifier). Crashes: 24 of 26 are `nose`; most clustered on `fin row` (10), `step-up`, `splashdown`. A ghost measurement (generator seeds 1000+, 80 per depth, super-boost pilot) showed landings on an up-slope (>8 deg) at depth 1: 248 of 1927, at depth 2: 405 of 2484, all intra-segment chains: triple 86, fin row 79, step-up 48 (depth 1). Depth 0 had none.
- Track change (generator.py): `triple` ".s.s.s..." → ".s...s...s..."; `fin row` ".f...f...f....." → ".f.....f.....f....."; `fin gauntlet` ".ff...f...ff......" → ".ff.....f.....ff......"; `step-up` "..utUTTDd..." → "..utttUTTDd...". Result: up-slope landings depth 1: 37 of 1898, depth 2: 95 of 2406; none left from triple/fin row/step-up (remaining are whoops, rhythm gap, mesa kicker micro hops/designed).
- Targets: already top 3 (heats 1-2, valley+desert = first map), top 2 (heats 3-5, night/stadium/desert = second map), win (heat 6, volcano = last map) in `_plan_heat`; no change needed.
- Rivals (manager.py): linear `i/5` → `RIVAL_LEVELS = [0.0, 0.15, 0.32, 0.68, 0.92, 1.0]` (eases heats 2-3, steepens 4-5).
- Sim (one, 12 seeds) learning row target-met %: before (baseline, 6 seeds) 100 83 83 100 83 33; after generator change 100 91 66 83 91 41; after rival curve 100 91 83 83 83 41. Goal 95 88 78 68 57 45. Heats 4-5 still 15-25 points too easy for the sim AI (top 2 is a lax target and the sim AI stronger than the real player); not pushed further because the rival level is nearly saturated.
- Control change (ui/input.py, mouse air-aim): `AIR_LEAN_STEP` 10 → 11 px, `AIR_LEAN_HYST` 3 → 4 px. 1.2 deg/px dropped to 1.09 deg/px (full 72 deg now 77 px, not 70) and a hand tremor of 3 px no longer flips the aim step. Evidence is the user's report plus weak input evidence: 166 L/R direction flips over 364 jumps (0.46 per jump, higher in later races, up to 21 in one), steering in about 25% of air ticks. Low confidence; sims do not use the mouse, so they cannot show it. Tests: 123 passed (test_input uses the constants).
- Watch next: whether the mouse air aim feels calmer; heat 3 (Hot Engine) blow-ups in new recordings; Hot Engine may need softening if it still fails; classic mode is too easy at heat 3 and 6 for the learning AI (91/66 vs goal).

## 2026-11-12 - pass 1

- Recordings: 13 live one-button valley/scrambler races (run heats 1-4: 4/4/3/2), archived to `recordings/archive/20261112-133320/`. They were made after the elevated-structure generator change, so they include the new segments. Sample is tiny; hints only. No heat 5/6 data.
- Evidence: target-met heat1 100%, heat2 75% (goal 88), heat3 67%, heat4 0% (2 races, goal 68). Failures were player errors on structures (crashes: muddy mesa x2, stair kicker x2; blow-ups on tabletop, step-up, mesa jump), with gaps of 5-6 s to the best rival in the failed heats, not rival speed. Rough landing rate about 30%.
- Change (generator.py): `muddy mesa` min_depth 1 → 2; `stair kicker` min_depth 2 → 3.
- Sim (one-button, 6 seeds), learning row target-met %: before 100 100 100 100 83 33; after 100 83 83 100 83 33. Goal 95 88 78 68 57 45. Mid heats (3-5) remain too easy for the sim AI while the real player struggles there, so the AI is stronger than this player; did not tighten rivals. Tests: 123 passed.
- Watch next: heat 5/6 recordings, whether the real player's heat 4 failures persist with later structure introduction, and whether sim AIs should be weakened to match human skill.
- Controls check (pass 1): no control change. Across the 13 recordings: 206 landings, 64 rough (31%), 24 perfect (12%) rough landings concentrated in 2 races (15/25 and 13/32, both on structure-heavy tracks) rather than spread evenly; nose crashes 5, clustered on structures (muddy mesa, stair kicker, tabletop). Tilt input changes ran 21.6 per 1000 ticks (about one every 46 ticks), so no sign of pre-landing oscillation. All one-button; no mouse setting recorded. Points at track (new structures), not controls. No global constant touched; recordings were archived anyway. Watch: if rough rate stays about 30% on plain jumps in the next batch, consider PITCH_RATE or LAND_TOLERANCE +5-10%.

## 2026-11-13 - structures + modifier rating (main agent, not a tuner pass)

- No recordings archived (none were used for tuning except the 3 modifier heats read by `mods`).
- Added complex deck structures (overpass, broken bridge, drawbridge) and `complex_weight(depth)`: no complex structures at depth 0, weight 0.55 at depth 1, +0.35 per depth after that.
- Modifier ranking (`modsim --seeds 12`, one-button, average + learning AI, heats 3 and 5), target-met with no modifier 0.71: sticky 0.60 (hurt +0.14), fragile 0.71 (0.00), double_heat 0.77 (-0.09), no_coolant 0.81 (-0.15). Set `MODIFIER_HARDNESS` no_coolant 0.1, double_heat 0.35 (sim said 0.27; 2 human heats with Hot Engine averaged a blow-up per race), fragile 0.5, sticky 0.9. Pick odds: heat 3 no_coolant 39%, double_heat 29%, fragile 24%, sticky 8%; heat 5 sticky 44%, fragile 27%, double_heat 20%, no_coolant 10%.
- Sim learning row (one-button, 6 seeds): before 100 83 100 66 100 33; after 100 83 83 66 50 50 (goal 95 88 78 68 57 45).
- Watch next: crashes on broken bridge / drawbridge in real recordings (are the speed and timing reads fair?), and whether Hot Engine / No Coolant should be redesigned for one-button mode since they barely hurt.
