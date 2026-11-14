# Project Specification: Excitebike Modernized (Personal Use)

**Version:** 1.0
**Status:** Ready for Claude Code handoff
**Owner:** Personal project — not for distribution or sale

---

## Table of Contents

0. How to Use This Document (Instructions for Claude Code)
1. Project Overview
2. Technical Stack Decision (Claude Must Confirm with User)
3. Authenticity Specification (The "Feel" Contract)
4. Core Game Loop (Preserved from Original)
5. Procedural Track Generation
6. Roguelike Run Structure and Meta-Progression
7. Map Editor
8. Architecture and Module Breakdown
9. Clarification Questions (Claude Must Ask the User)
10. Milestones and Acceptance Criteria
11. Technical Risks and Mitigations
12. What Claude Should Do First

---

## 0. How to Use This Document (Instructions for Claude Code)

You are building a personal modernization of *Excitebike* (NES, 1984) using the
Pygame Zero foundation from Wireframe Magazine issue 66. Your job is to produce
a runnable game that feels indistinguishable from the original at its core, then
layer on procedural generation, a roguelike run structure, meta-progression, and
a map editor.

**You must follow this protocol at every major decision point:**

1. Before writing code for a milestone, ask the user any questions listed in §9
   that are relevant to that milestone.
2. When this document leaves a design choice ambiguous, present 2–3 concrete
   options with trade-offs and ask the user to choose. Do not silently pick one.
3. After completing each milestone, provide a short playable build (or clear run
   instructions) and ask for feel-based feedback before proceeding.

Your north star is **feel fidelity**: the bike must accelerate, tilt, overheat,
and crash in a way that a childhood player of *Excitebike* would recognize
immediately. Every new system must sit on top of that core without diluting it.

---

## 1. Project Overview

| Item | Specification |
|---|---|
| **Base** | Pygame Zero homage to *Excitebike* from Wireframe Magazine #66 (Wireframe-66/source-code-excitebike/exitebike.py) |
| **Core feel** | NES *Excitebike*: side-scrolling motocross, four lanes, ramps, heat management, angle-based landings |
| **New systems** | Procedural track generation, roguelike run loop, permanent upgrades, meta-currency, unlocks, in-game map editor |
| **Primary target** | Mobile (Android first, iOS if feasible) |
| **Secondary target** | Desktop (Windows/macOS/Linux) for development and testing |
| **Legal scope** | Strictly personal use. Do not distribute ROMs or Nintendo assets. Original NES sprites may be used as visual reference; final assets should be either ripped sprite sheets used locally or redrawn equivalents. |

---

## 2. Technical Stack Decision (Claude Must Confirm with User)

Pygame Zero runs on desktop Python, but **mobile deployment is not native**.
Before building, Claude must present these options and ask the user to choose:

| Option | How mobile is achieved | Pros | Cons |
|---|---|---|---|
| **A. Pygame Zero + pygbag (WebAssembly)** | Package the game as a web app; play in mobile browser (Chrome/Safari). Can be wrapped in a WebView for an APK. | Fastest path; uses the Wireframe code directly; works on Android and iOS browsers. | Not a "native" app; performance overhead of WASM; touch controls must be implemented in Pygame. |
| **B. Port logic to Godot 4** | Native Android/iOS export. | Best mobile performance and native touch/gesture support. | Requires rewriting the Pygame Zero code in GDScript; more upfront work. |
| **C. Pygame CE + Buildozer** | Native APK via Python-for-Android. | Keeps Python codebase. | Toolchain is fragile; iOS support is very limited. |

**Recommendation to present to user:** Option A for a fast, playable mobile
prototype; Option B if the user wants a polished native app and is willing to
accept a rewrite. The specification below assumes Option A (Pygame Zero) unless
the user overrides it, but the game logic is written to be engine-agnostic so a
later Godot port remains possible.

---

## 3. Authenticity Specification (The "Feel" Contract)

These constants and behaviors are non-negotiable. They come from the documented
NES RAM map and physics analyses.

### 3.1 Core physics constants

| Parameter | Value / Behavior | Source |
|---|---|---|
| Speed units | Integer, **starts at 0**, **maxes at 46–47**. Speed cap around 47–49. | RAM map: `0x00F3` starts 0, max 46/47; 47/49 appears cap |
| Acceleration (A button) | Speed increment **+1 per step**. | RAM map: "A adds just one" |
| Acceleration (B / Turbo) | Speed increment **+2 per step**, but temperature rises faster. | RAM map: "B … increments by 2" |
| Engine temperature | **Starts at 8**. **Stabilizes at 17** while holding A. **Overheats at 32**. | RAM map: `0x03E3` |
| Coolant / speed-up pads | Reset temperature (not merely slow its rise). | RAM map: "running over 'speedup' actually just resets your temp" |
| Air angle | Bike pitch is controlled with left/right while airborne. **Landing with wheels roughly level preserves momentum; wrong angle causes crash.** | Physics analysis: "only a landing with the wheels roughly level keeps you upright" |
| Crash penalty | Rider is thrown off and must jog back to the bike on foot. | Same |
| Lane system | Four lanes (1–4). Sand/off-track areas behave differently. | RAM map: lane `0x00B0` 1–4, 0 = sand |

### 3.2 Visual authenticity

- **Resolution and scale:** Use the NES sprite dimensions as the reference. The
  Red Bike sprite is approximately **20×21 px**; moving/crashed frames vary
  (18–22 px wide). The bike should remain at a fixed X coordinate on screen
  while the track scrolls beneath it.
- **Track tiles:** The Wireframe implementation uses a simple integer list:
  `0` = plain track, `1` = jump, `2` = start/finish. Extend this tile vocabulary
  (see §5) but keep the visual grid granular enough to read like the original.
- **Scrolling:** The track is composed of **100-pixel-wide blocks** in the
  Wireframe code; smooth scrolling is achieved by offsetting block drawing by
  `trackPos % 100`. Preserve this rhythm; the original's scroll speed is tied
  directly to bike speed.
- **Bike vibration:** Alternate between two frames based on speed to create the
  original's characteristic engine shudder.
- **Assets:** Use the public *Excitebike* sprite sheets from The Spriters
  Resource (bike frames, track parts) as **local reference only**. Do not commit
  ripped Nintendo assets to a public repository. If the user wants to share the
  project, redraw sprites in the same dimensions and palette.

---

## 4. Core Game Loop (Preserved from Original)

The base loop must work before any new system is added:

1. Bike sits at starting line; countdown timer (`0x0034` → `0x0024`) reaches "go".
2. Player accelerates with **A** (normal) or **B** (turbo). Speed rises;
   temperature rises faster on B.
3. Track scrolls. Ramps launch the bike; while airborne, left/right adjusts
   pitch.
4. Landing angle determines success or crash. Crash costs time (rider jogs
   back).
5. Coolant pads reset temperature. Off-track/sand slows the bike.
6. Lap completes when track position passes the finish threshold; lap time is
   recorded.

**Validation criterion:** A player familiar with NES *Excitebike* should be able
to pick up the build and clear a simple track without needing to relearn the
controls.

---

## 5. Procedural Track Generation

### 5.1 Design goals

- Every run produces **novel but readable** tracks.
- Generated tracks must be **solvable with the base bike** (no impossible jump
  gaps at starting speed).
- Difficulty should scale with run depth.

### 5.2 Tile vocabulary (minimum)

| Tile ID | Name | Behavior |
|---|---|---|
| 0 | Flat | Neutral driving |
| 1 | Ramp (small) | Short jump |
| 2 | Ramp (large) | Longer jump, more air time |
| 3 | Coolant pad | Resets temperature |
| 4 | Mud / sand | Slows bike |
| 5 | Debris | Crash if hit at speed; can be jumped |
| 6 | Start/finish | Lap boundary |
| 7 | Gap / pit | Requires sufficient speed and correct angle to clear |
| 8 | Whoops (rhythm section) | Series of small bumps; demands throttle control |

### 5.3 Generation algorithm (recommended)

Use **constraint-based segment assembly** rather than pure noise:

1. Define a **segment library**: hand-authored short sequences of tiles with
   metadata (entry speed required, exit speed produced, difficulty rating, heat
   cost).
2. At generation time, build a path by selecting segments whose **entry
   requirements** match the bike's current capability, weighted by run
   difficulty.
3. Insert **coolant pads** at intervals calibrated to the expected heat
   accumulation over the preceding segment sequence.
4. Validate the generated track by simulating a **ghost rider** with baseline
   physics; if the ghost cannot finish, regenerate or soften the segment.

This produces tracks that feel authored rather than random, while remaining
infinitely replayable.

---

## 6. Roguelike Run Structure and Meta-Progression

### 6.1 Run structure

- A **run** is a sequence of **heats** (e.g., 5–8 tracks).
- Each heat has a **target**: finish within a time limit, place above a position,
  or survive a track with a modified constraint (e.g., no coolant pads, doubled
  heat gain).
- **Permanent death:** failing a heat ends the run. No mid-run saves.
- Between heats, the player chooses **one of three upgrades** from a random pool.

### 6.2 Upgrade categories (examples)

| Category | Example upgrades |
|---|---|
| **Engine** | +2 max speed; slower heat gain; turbo costs less temperature |
| **Cooling** | Coolant pads give a larger reset; passive slow cooling while coasting |
| **Air control** | Faster pitch rotation; wider landing tolerance; reduced crash penalty |
| **Recovery** | Shorter jog-back time after crash; one crash forgiven per run |
| **Economy** | +% meta-currency earned; chance for bonus currency on perfect landings |

Upgrades should **stack multiplicatively where possible** and be visible in a
simple run HUD.

### 6.3 Meta-currency and unlocks

- **Earned per run** based on distance travelled, heats cleared, and perfect
  landings.
- **Spent between runs** on permanent unlocks:
  - New **bike classes** (different base stats: heavier/slower but more stable;
    lighter/faster but hotter).
  - **Starting upgrades** (begin a run with one upgrade already active).
  - **Cosmetic liveries** (palette swaps for the bike).
  - ~~Track theme packs~~ (dropped 2026-11-13: biomes are the stages of a run instead, see DECISIONS.md).
- Meta-progression must **never make the game trivial**; it should widen options
  rather than simply inflate power.

---

## 7. Map Editor

### 7.1 Requirements

- **Grid-based placement** of the tile vocabulary from §5.
- **Pan and zoom** (or at minimum horizontal scroll) for longer tracks.
- **Save/load** tracks as JSON files.
- **Share/import** via a compact text code (Base64-encoded JSON) so the user can
  send tracks to themself across devices.
- **Playtest button** that immediately launches the current editor track with
  the base bike.
- **Validation:** warn if a track contains a gap that is unclearable at base
  speed, using the same ghost-rider check as §5.

### 7.2 UI constraints

Touch-first: large tile palette buttons, drag-to-paint, pinch/scroll for
navigation. On desktop, mouse and keyboard shortcuts are acceptable.

---

## 8. Architecture and Module Breakdown

Claude should implement the following modules. The Pygame Zero script can begin
as a single file but should be refactored into these packages by Milestone 3.

    excitebike_modern/
    ├── main.py                  # Entry point (Pygame Zero or launcher)
    ├── config.py                # Constants: physics values, colors, tile IDs, upgrade definitions
    ├── bike.py                  # Bike actor: physics, angle, temperature, crash state
    ├── track/
    │   ├── tiles.py             # Tile definitions and collision metadata
    │   ├── generator.py         # Procedural generation (§5)
    │   └── validator.py         # Ghost-rider solvability check
    ├── run/
    │   ├── manager.py           # Run state: heat sequence, upgrades, death
    │   └── upgrades.py          # Upgrade pool and stacking logic
    ├── meta/
    │   └── profile.py           # Persistent meta-currency, unlocks, save/load
    ├── editor/
    │   ├── ui.py                # Touch-first editor interface
    │   └── io.py                # JSON save/load and share-code encoding
    ├── ui/
    │   ├── hud.py               # Speed, temperature, lap time, run progress
    │   └── menus.py             # Main menu, upgrade choice, meta-shop
    └── assets/
        ├── sprites/             # Bike frames, tiles, UI elements
        └── audio/               # Engine loop, jump, crash, UI sounds

**Persistence:** Use a simple JSON file in the user's app-data directory for
meta-progression and saved editor tracks. On mobile web (pygbag), use browser
`localStorage` via a Python-JS bridge; provide a fallback in-memory profile if
storage is unavailable.

---

## 9. Clarification Questions (Claude Must Ask the User)

Before starting **Milestone 1**, Claude must ask the following. Group them
naturally; do not dump all at once.

### 9.1 Platform and controls

1. **Mobile target:** Android only, or iOS as well? (This affects whether
   pygbag/WebView or Godot is the better long-term path.)
2. **Touch controls:** Do you want on-screen buttons (left/right/A/B), **tilt
   steering** using the device accelerometer, or a **swipe-based lane shift**?
   The original uses discrete lane changes; tilt would be an approximation.
3. **Screen orientation:** Landscape only (recommended for a side-scroller), or
   should portrait be supported?

### 9.2 Visual fidelity

4. **Art direction:** Do you want **pixel-perfect NES sprites** (using ripped
   sheets locally), **redrawn sprites at higher resolution in the same style**,
   or a **modernized pixel look** (same proportions, new palette/detail)?
5. **Screen scaling:** Integer scaling with black bars (crisp pixels), or smooth
   scaling to fill the screen?

### 9.3 Roguelike depth

6. **Run length:** How many heats should a full run be? (Suggested: 5–8. Shorter
   = more retries; longer = more build momentum.)
7. **Upgrade agency:** Should upgrades be **random choices from three** (classic
   roguelike), or a **shop where you spend in-run currency** (more control)?
8. **Meta-progression tone:** Should permanent unlocks be **sidegrades and
   options** (recommended, preserves challenge) or **power increases** (easier,
   more "mobile progression" feel)?
9. **Failure forgiveness:** Should the player get **one crash forgiveness per
   run**, or is every crash potentially run-ending depending on time loss?

### 9.4 Map editor

10. **Editor scope:** Is the editor primarily for **you to author tracks**, or do
    you want it polished enough to **share tracks with friends** via codes?
11. **Editor complexity:** A simple tile-painter is straightforward. Do you want
    **advanced features** like layered tracks, checkpoints, or custom heat/coolant
    rates per tile?

### 9.5 Audio

12. **Audio direction:** **Original NES-style chiptune** (redrawn or newly
    composed in the same style), **modern synth/rock**, or **silent/minimal** for
    now?

### 9.6 Scope control

13. **MVP definition:** Which feature is the **first must-have** after the core
    game feels right? (Recommended order: procedural generation → run structure
    → meta-progression → editor. The editor is the largest single system and can
    come last.)

---

## 10. Milestones and Acceptance Criteria

Claude should execute these sequentially, pausing for user feedback after each.

### Milestone 1: Authentic Core

**Deliverable:** A playable build with the Wireframe code refactored to use the
documented physics constants. One static track. Lap timing. Crash on bad
landing. Temperature gauge.

**Acceptance:** User confirms the bike "feels like Excitebike."

### Milestone 2: Touch Controls and Mobile Packaging

**Deliverable:** Touch control overlay (buttons or chosen scheme), landscape
layout, and a pygbag build that runs in a mobile browser (or chosen mobile
path).

**Acceptance:** User can complete a lap on their phone.

### Milestone 3: Procedural Tracks

**Deliverable:** Segment-library generator with ghost-rider validation. Replace
the static track with generated tracks. Difficulty scaling stub.

**Acceptance:** Ten consecutive generated tracks are all completable and visibly
varied.

### Milestone 4: Roguelike Run Loop

**Deliverable:** Heat sequence, death/failure, between-heat upgrade choice (3
random options). Run HUD.

**Acceptance:** A full run can be started, won, or lost; upgrades visibly affect
bike behavior.

### Milestone 5: Meta-Progression

**Deliverable:** Persistent meta-currency, meta-shop with unlocks, profile
save/load.

**Acceptance:** Currency earned in a run survives app restart; at least one
unlock changes the starting experience.

### Milestone 6: Map Editor

**Deliverable:** Touch-first tile editor with save/load, share code, and
playtest.

**Acceptance:** User can build a track from scratch on mobile, save it, reload
it, and play it.

### Milestone 7: Polish

**Deliverable:** Audio pass, particle effects (dust, sparks), menu polish,
performance optimization for mobile.

---

## 11. Technical Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Pygame Zero performance on low-end mobile browsers | Profile early in Milestone 2; reduce per-frame allocations; consider pre-rendering track chunks. If unplayable, pivot to Godot (Option B in §2) at Milestone 3. |
| Procedural generation producing unfair tracks | Ghost-rider validation is mandatory, not optional. Tune segment entry requirements conservatively. |
| Touch controls feeling imprecise for a precision physics game | Offer both discrete buttons and a "lane swipe" mode; let the user choose in settings. |
| Ripped sprite assets causing repository issues | Keep ripped assets local only; provide a redraw_assets.md guide for replacing them if the project is ever shared. |
| Meta-progression trivializing the game | Cap permanent power increases; emphasize sidegrades and options. |

---

## 12. What Claude Should Do First

1. Read the Wireframe exitebike.py source from
   https://github.com/Wireframe-Magazine/Wireframe-66 (path:
   source-code-excitebike/).
2. Install Pygame Zero (pip3 install pgzero).
3. Run the original homage locally to understand its baseline.
4. **Ask the user the questions in §9**, starting with platform/controls and
   art direction, then proceeding to roguelike depth and editor scope.
5. Only after receiving answers, begin Milestone 1.

This document is the contract. If a requirement conflicts with what the user
asks for during clarification, the user's live answer overrides the document. If
a technical constraint makes a requirement infeasible, Claude must surface the
constraint and propose alternatives rather than silently descoping.