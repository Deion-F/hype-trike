# Decisions Log — hype-trike

Confirmed decisions for this project. When a decision here conflicts with
PROJECT_SPEC.md, this file wins: the spec says the user's live answers override it.
Each entry records the date and where it came from.

Status key: ✅ confirmed · ⏳ pending (asked, no answer yet) · 📝 note (fact, not a choice)

---

## 0. Scope and identity

| # | Decision | Status | Date | Notes |
|---|---|---|---|---|
| 0.1 | Build an **original** side-scrolling motocross game that uses the same kinds of mechanics as the spec (4 lanes, ramps, heat gauge, landing angle). Do **not** use the Excitebike name, Nintendo sprites or audio, or the original's tracks or look. | 📝 | 2026-11-09 | Claude's constraint, raised at kickoff. The mechanics and tuning numbers in §3.1 are fine to use. §3.2 changes from "ripped sprites" to original art. |
| 0.2 | On-screen title: **Hype Trike** | ✅ | 2026-11-09 | |
| 0.3 | Vehicles: **dirt bike** is the starting vehicle; a **trike (three-wheeled ATV)** is an unlockable vehicle class. Both use the same core physics. | ✅ | 2026-11-09 | User answer. |
| 0.4 | Later generated levels include **ground materials** such as grass, dirt and sand. Unlockable vehicles do better on some of these, so vehicle choice becomes a real sidegrade. | ✅ | 2026-11-09 | User answer. Ties to Q8 (sidegrades) and the §5 generator. |

## 0b. Implementation choices (Claude's defaults; override any time)

| # | Choice | Why |
|---|---|---|
| I.1 | Use **pygame-ce with an asyncio main loop** instead of the `pgzrun.go()` runner. The Wireframe code gets refactored into it. | pygbag needs an `async` main loop that yields to the browser every frame. Pygame Zero's blocking runner doesn't fit that, and pygbag ships pygame-ce, so desktop and web use the same library. This is still the Python + pygbag path (Option A). |
| I.2 | Fixed logic resolution: **360 px tall**, with width set from the screen's aspect ratio (640 on 16:9, about 780 on a 19.5:9 phone) | "Smooth fill" with no stretching and no black bars: wider phones show more track ahead. |
| I.3 | Track column = **80 px** (8 per 640 px view) | Keeps the homage's "8 blocks on screen" rhythm (100 px in 800 px). |
| I.4 | Simulation runs at a **fixed 60 Hz**, deterministic and frame-based | The ghost-rider validator and the CPU rivals run the exact same physics as the player. |
| I.5 | All art and audio are **generated in code** (pixel art drawn with pygame, chiptune synthesized) | Original assets, nothing ripped, no asset pipeline needed. |

## 1. Environment (§12 setup)

| # | Fact | Date |
|---|---|---|
| 1.1 | Python 3.12.3 on WSL2. System `pip3`/`ensurepip` aren't installed, so `uv` is used instead. | 2026-11-09 |
| 1.2 | Project venv is `.venv/` (made with `uv venv`). Venv Python is **3.11.18** (uv-managed, not the system 3.12). Installed: pgzero 1.2.1, pygame 2.6.1, numpy 2.4.6. | 2026-11-09 |
| 1.3 | Wireframe-66 homage was read in full: about 80 lines, one file, tile list `track` (0 flat, 1 jump, 2 start/finish), `muck` list (lane index), 100 px blocks, 800×600 window, lanes at y = 375–525 in 50 px steps, float speed 1–5, angle-based crash (< −25° on landing). User allowed running it, and it ran headless for 4 s with no errors. Assets: bike 50×50, track/jump tiles 101×246, background 800×600. | 2026-11-09 |

## 2. Tech stack (§2)

| # | Decision | Status | Date | Notes |
|---|---|---|---|---|
| 2.1 | **Option A: Pygame Zero + pygbag** (WASM, mobile browser). Keep game logic engine-agnostic. | ✅ | 2026-11-09 | User picked the recommended option. |

## 3. Platform and controls (§9.1)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q1 | Mobile target | **Android only** | ✅ | 2026-11-09 |
| Q2 | Touch controls | **On-screen buttons for throttle (A/B) and tilt, plus swipe up/down for lane changes** | ✅ | 2026-11-09 |
| Q3 | Screen orientation | **Landscape only** | ✅ | 2026-11-09 |

## 4. Visual fidelity (§9.2)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q4 | Art direction | **Modern pixel look**: original art, similar proportions, more detail, a richer palette, smoother animation | ✅ | 2026-11-09 |
| Q5 | Screen scaling | **Smooth fill** (fills the screen, no letterboxing) | ✅ | 2026-11-09 |

## 5. Roguelike depth (§9.3)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q6 | Run length (heats) | **6 heats** | ✅ | 2026-11-09 |
| Q7 | Upgrade agency | **Pick 1 of 3 random upgrades** between heats | ✅ | 2026-11-09 |
| Q8 | Meta-progression tone | **Sidegrades and options** (bike classes, starting choices, cosmetics, themes); cap any permanent power | ✅ | 2026-11-09 |
| Q9 | Failure forgiveness | **Time loss only**: a crash costs jog-back time and fails the run only if the heat target is missed. "One crash forgiven" exists only as an optional upgrade. | ✅ | 2026-11-09 |

## 6. Map editor (§9.4)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q10 | Editor scope | **Share with friends**: polished UX, friendly share codes, validation on import | ✅ | 2026-11-09 |
| Q11 | Editor complexity | **Simple tile painter**: per-lane grid, drag-to-paint, scroll, save/load, share code, playtest, ghost-rider warning. Advanced features deferred. | ✅ | 2026-11-09 |

## 7. Audio (§9.5)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q12 | Audio direction | **Original chiptune**: new 8-bit-style SFX and music | ✅ | 2026-11-09 |

## 8. Scope control (§9.6)

| # | Question | Answer | Status | Date |
|---|---|---|---|---|
| Q13 | First must-have after the core feels right | **Spec order**: procedural, then run loop, then meta, then editor | ✅ | 2026-11-09 |

---

## 9. Milestone log

| Milestone | Status | Date | Notes |
|---|---|---|---|
| M1 Authentic Core | ✅ built, awaiting feel feedback | 2026-11-09 | §3.1 constants in `config.py`; 13 physics tests pass; art in `docs/art/`. |
| M2 Touch + mobile | ✅ built; phone test pending | 2026-11-09 | Web build verified in headless mobile Chromium (multi-touch A + swipe). Phone delivery: **local Wi-Fi** via `tools/serve_phone.sh` (user's choice). Settings: lane mode swipe/buttons/both, button size, side swap. |
| M3 Procedural tracks | ✅ | 2026-11-09 | 19-segment library, difficulty by depth, heat-budget coolant, grass from depth 2 and sand from depth 3, ghost validation with the base bike **and** the selected vehicle, auto-softening. 8 generator tests. |
| M4 Roguelike run loop | ✅ | 2026-11-09 | 6 heats: time, place or survive-a-modifier targets, final heat = win. 16 upgrades in 5 categories, multiplicative with stack caps, pick 1 of 3. Missing a target ends the run. A full run is simulated in tests. |
| M5 Meta-progression | ✅ | 2026-11-09 | Garage shop: Trike 300 / Scrambler 450 / Sprinter 650 coins, 5 liveries, 7 start kits (one equipped), themes desert/night/stadium. Unlocks are sidegrades (tested). Profile persists via file, localStorage, or memory fallback. |
| M6 Map editor | ✅ | 2026-11-09 | Lane-grid painter, minimap, zoom, two-finger pan and pinch, undo, save/load, JSON files, `HT1-` share codes (sanitised on import), live ghost warnings, playtest on the base bike. Verified in the browser, including localStorage across a reload and import via browser prompt. |
| M7 Polish | ✅ | 2026-11-09 | Synthesized chiptune SFX, pitch-stepped engine, menu music (built incrementally, worst frame 13 ms). Dust, sparks, steam. Demo rider on the title screen. Track columns pre-rendered: frame cost 5.8 to 0.7 ms. |

## 10. Open items (need the user)

- **Feel feedback** (M1 acceptance): tune in `hypetrike/config.py`. The likeliest knobs are `PITCH_RATE`, `AIR_NOSE_DROP`, `LAND_TOLERANCE`, `GRAVITY`, `SPEED_TO_PX`, `HEAT_B`.
- **Phone test** (M2 acceptance): run `tools/serve_phone.sh`, then the printed Windows commands, then open on the phone. Check touch latency and frame rate on the real device.
- **Economy and difficulty**: a winning run pays about 450–550 coins; shop prices are 60–650. Rivals and par times are tuned against an AI, not a human yet.

## Change history

- 2026-11-12: Tuning pass 2 (16 live recordings, archived in `recordings/archive/20261112-135928/`, user focus: finicky air lean, ramp-into-ramp, placing ladder). Generator: chained-jump segments respaced so a jump no longer lands on the next ramp's up-slope (`triple`, `fin row`, `fin gauntlet`, `step-up`; ghost up-slope landings at depth 1 248 → 37 of ~1900). Placing targets confirmed as top 3 (heats 1-2), top 2 (heats 3-5), win (heat 6 volcano); no code change needed. Rival level is now a table `RIVAL_LEVELS` in `run/manager.py` (0, .15, .32, .68, .92, 1) instead of linear. CONTROL CHANGE: mouse in-air aim `AIR_LEAN_STEP` 10 → 11 px and `AIR_LEAN_HYST` 3 → 4 px in `ui/input.py` (less twitchy). See `docs/tuning_log.md`.
- 2026-11-12: Tuning pass 1 (13 live one-button recordings, archived in `recordings/archive/20261112-133320/`). The player crashed or blew up mostly on the new elevated structures (muddy mesa, stair kicker, tabletop, step-up, mesa jump), so those two heavier ones are introduced later: `muddy mesa` min_depth 1 → 2, `stair kicker` min_depth 2 → 3 in `track/generator.py`. Rival curve untouched. Controls checked and left unchanged. See `docs/tuning_log.md`.
- 2026-11-12: Race recordings + tuning. Every race is recorded by default (setting "Race recordings") as JSON in `recordings/` (`hypetrike/replay.py`): the track (share-code form + generator segment per column), the player's stats, the rival setup and seed, the throttle mode, the player's controls every tick (RLE), an event log for the player and every rival, state samples, and a summary. Replays re-simulate exactly (tested in both modes) and are watchable from a new title-screen **REPLAYS** list (F = 2× speed). `tools/tuning.py` has summary / report (per run heat vs `TARGET_CURVE` 95→45%) / show / sim (AI players novice, average, good and learning, over full runs) / archive (moves used recordings to `recordings/archive/<stamp>/` with a NOTE.md). The `difficulty-tuner` agent (Sonnet 5.5) runs the review → tune → verify → archive → log loop. Its log is `docs/tuning_log.md`. Baseline sim (2 seeds): heats 1–5 near 100% for average and better, then a cliff at the volcano final, so the curve needs work.
- 2026-11-12: Scrambler, Sprinter and Trike redrawn to match the new dirt bike (52×50 grid, big wheels, coloured bars + hand guard, front fenders that hug the tyre with nothing poking ahead). **Scrambler**: retro trail bike with a round tank, brown bench seat, high pipe with a heat shield, round headlight, fork gaiters, rear rack, chunky block tread, and a high fender with a gap above the tyre. **Sprinter**: supermoto on cast five-spoke wheels with slicks and a livery rim stripe, belly pan, number fairing + screen, sharp tail spoiler, rider tucked further forward. **Trike**: fat balloon knobbies with the far rear wheel showing between the wheels, wide rear fender, rack, rounded nose with a small headlight, upright rider. Per-vehicle exhaust origins updated; the trike's heat-arc offset was removed (all riders sit at one height).
- 2026-11-12: Heat is measured in **bars**: 12 bars over the gauge (`HEAT_BAR` ≈ 2.67 heat, the segments of the arc over the rider). The one-button red super-boost window is the top **3 bars** (`ONE_SUPER_AT` 27 → 24), so it lasts about 1.9 s at the boost heat rate instead of 1.2 s. Pads come in three sizes: small (`PAD_S`, share-code `k`), medium (`COOLANT`, `c`) and large (`PAD_L`, `K`), adding +1/+2/+3 bars in one-button mode (was a flat +5 heat). In classic mode any size still cools fully. The plate width and chevron count show the size. The generator mixes sizes 40/35/25%. The editor's pad tool cycles S → M → L on a second tap. Lava pits are defined as 3 bars (same 8 heat).
- 2026-11-12: Player marker: a pulsing white/yellow 2 px outline plus a "YOU" tag over the helmet during the countdown and for 1.5 s after GO, with the player drawn on top of the pack meanwhile. Gold outline while airborne whenever the current nose angle would land PERFECT on the predicted landing slope (`Bike.perfect_aligned`, real jumps only, not pits). New lane surface **Water** (editor tile, share-code char `p`, generator segments "puddles" and "splashdown", ghost AI avoids it): a splash takes 6 heat and 25% speed in both modes. New **Volcano** theme (`lava`): heat rises ×1.35 faster and cools ×0.55 slower, pits fill with lava, embers drift up, and puddles become lava pits (+8 speed over the cap and +8 heat, which can blow you up in the red). Every run's final heat is on the Volcano; it is also a 250-coin theme pack for quick races and the editor. Ghost-AI run sim: 7/9 seeds won (was 8/9).
- 2026-11-12: Run upgrades redesigned for the throttle modes. Each upgrade lists its modes, and runs remember the mode they started in (offers, names and descriptions follow it). One-button only: Supercharger (+2 speed in the red), Quick Warm-Up (cold heat ×1.4), Heat Wrap (release drain ×0.65), Pre-Heater (restart warm after a crash). Reworked: Cool Head now slows heating only in the red zone (both modes); Radiator is a once-per-race vent instead of a blow-up/stall (both modes; it used to drain heat faster, which hurt one-button play); Heat Sink also shortens blow-ups; Cryo Pads reads as "Pad Lock" on heat pads; Turbo Tune reads as "Long Boost". New: Hype Landing (perfect landing +3 heat in one-button mode, -3 in classic, never a blow-up), Plush Forks (rough landings cost half), Quick Steer (lanes 40% faster, also a garage kit). New categories Heat and Handling replace Cooling. Unknown upgrade ids from old saves are skipped.
- 2026-11-12: New "Mouse lanes" setting, default **Follow cursor**: the rider takes whichever lane the cursor is over (bands rise with the ground under the cursor on ramps), with or without a button held. It wakes on the first cursor movement of a race, and lane keys take over until the mouse moves again. Lean still works from home, horizontally. "Drag from home" keeps the old scheme; the lane-dots setting only applies to that mode.
- 2026-11-12: Mouse lane dots around home are a setting ("Mouse lane dots"), off by default; the aimed-lane chevron by the rider stays. The dashed nose-angle line is replaced by a curved arrow just ahead of the bike's nose that turns the way the bike is being rotated (cyan curling up = lean back, orange curling down = lean forward). It shows for mouse, keys and touch. Mid-air mouse aim makes it longer, thicker and more vivid per aim step. Rivals line up level with the player (no 6–24 px stagger), and the checkered line is drawn `START_LINE_DX` ahead of `START_X` so every front tyre touches it. Dirt-bike family redrawn: low upswept tail, flat seat, tank shroud with no beak, a front fender hugging the tyre, a coloured hand guard by the glove, and bigger spoked wheels with knobby tread (sprinter keeps smooth tyres). The sprite grid grew to 52×54 (contact 26,48), with more headroom for the helmet. Translucent dust puffs come off every bike's rear tyre (more with speed and boost, less on grass), and a dust cloud on touchdown is sized by fall speed. The settings list now fits the 360 px canvas.
- 2026-11-10: One-button throttle is now the default (old saves migrate once via `settings_v`). In that mode heat drives speed: 0–9 ramps to A top speed, 9–27 is the boost band, and 27–32 is super boost. Letting go cools the engine, and speed falls with it. Pads are heat pads (+5 heat, can blow you up in the red), rough landings cost 6 heat, and the exhaust flame shows the heat level. Mouse: sticky anchor, hold still 0.5 s to move home. Air lean zones are tighter than ground ones (10 px per 12° step). The anchor moves to the cursor on every landing and after a crash. Rivals scale with the run round (`rival_level` 0→1: speed, turbo, landing precision, botched jumps, missed hazards); whoops are rarer and absent at depth 0. Every run heat is a race vs 3 rivals with a placing target (modifier heats keep their modifier); solo par runs moved to a new TIME TRIAL mode. Rival turbo is capped at the player's turbo speed. New "Mouse wheelie" setting (default ramps only). Boosting eases in a visual "speed feel": faster backdrop parallax, camera lead, speed lines, super-boost shake (FX_* in config.py). Heat also shows as a segmented arc over the rider's helmet once in the boost zone (setting "Heat gauge": rider + bar / rider / bar). Throttle grace (0.6 s heat freeze after release) is classic-mode only now.

- 2026-11-09: All §9 questions (Q1–Q13) and the §2 stack choice confirmed. Ready for Milestone 1.
- 2026-11-09: File created. §12 setup steps 1–2 done; step 3 done after the user allowed it.
