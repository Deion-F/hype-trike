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

- 2026-11-10: One-button throttle is now the default (old saves migrate once via `settings_v`). In that mode heat drives speed: 0–9 ramps to A top speed, 9–27 is the boost band, and 27–32 is super boost. Letting go cools the engine, and speed falls with it. Pads are heat pads (+5 heat, can blow you up in the red), rough landings cost 6 heat, and the exhaust flame shows the heat level. Mouse: sticky anchor, hold still 0.5 s to move home. Air lean zones are tighter than ground ones (10 px per 12° step). The anchor moves to the cursor on every landing and after a crash. Rivals scale with the run round (`rival_level` 0→1: speed, turbo, landing precision, botched jumps, missed hazards); whoops are rarer and absent at depth 0. Every run heat is a race vs 3 rivals with a placing target (modifier heats keep their modifier); solo par runs moved to a new TIME TRIAL mode. Rival turbo is capped at the player's turbo speed. New "Mouse wheelie" setting (default ramps only). Boosting eases in a visual "speed feel": faster backdrop parallax, camera lead, speed lines, super-boost shake (FX_* in config.py). Heat also shows as a segmented arc over the rider's helmet once in the boost zone (setting "Heat gauge": rider + bar / rider / bar). Throttle grace (0.6 s heat freeze after release) is classic-mode only now.

- 2026-11-09: All §9 questions (Q1–Q13) and the §2 stack choice confirmed. Ready for Milestone 1.
- 2026-11-09: File created. §12 setup steps 1–2 done; step 3 done after the user allowed it.
