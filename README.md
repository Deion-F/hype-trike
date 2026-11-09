# Hype Trike

An original side-scrolling motocross roguelike for personal use: four lanes,
ramps, engine heat and landing angles, plus procedural tracks, 6-heat runs,
unlockable vehicles (including the trike) and a track editor with share codes.
All art and audio are generated in code. See `DECISIONS.md` for every confirmed
design decision and `PROJECT_SPEC.md` for the original brief.

## Play on desktop

```bash
cd hypetrike && ../.venv/bin/python main.py
```

| Action | Keys | Touch |
|---|---|---|
| Throttle (A) | `Z` / `J` / `Space` | **A** button |
| Turbo (B), heats the engine | `X` / `K` | **B** button |
| Lean back / forward (in the air) | `←` / `→` | **<** / **>** buttons |
| Change lane | `↑` / `↓` | swipe up/down (or lane buttons, see Settings) |
| Pause | `Esc` / `P` | **II** |

Land with the wheels matching the ground's slope. Nose-down landings crash you;
nose-high landings cost speed. Holding A keeps the engine at a safe 17, while
turbo climbs toward the overheat point (32). Coolant pads reset the temperature.

## Play on your Android phone (local Wi-Fi)

```bash
tools/serve_phone.sh
```

It builds the web version, serves it on port 8000 and prints the one-time
Windows commands needed under WSL2 (port-forward + firewall). Open
`http://<PC Wi-Fi IP>:8000/` on the phone. It needs internet, because the Python
runtime loads from the pygbag CDN. Use Chrome's "Add to Home screen" to launch
full-screen in landscape.

Build only: `tools/build_web.sh` → `hypetrike/build/web/` (a static site).

## Develop

```bash
.venv/bin/python -m pytest -q tests        # physics, generator, run, meta, editor
.venv/bin/python tools/shots.py OUT_DIR    # headless art sheet + screenshots
```

The setup used `uv venv .venv && uv pip install pygame-ce pygbag pytest`.

```
hypetrike/            pygbag app folder (main.py must stay at its root)
  main.py             async entry point, View (fixed 360 px tall logical canvas)
  config.py           feel-contract constants (speed, heat, gravity, landing)
  bike.py             physics; vehicle classes (dirt, trike, scrambler, sprinter)
  race.py             countdown, laps, CPU rivals
  audio.py            synthesized chiptune SFX, engine and music
  track/              tiles + Track model, generator, ghost-rider validator, static tracks
  run/                run manager (heats, targets, payout), upgrade pool
  meta/               profile persistence (file / localStorage / memory), shop
  editor/             editor UI, JSON + share-code I/O
  ui/                 rendering, HUD, input (touch/keys), menus, garage, run screens
tests/                pytest suite
tools/                build/serve scripts, screenshot harness
docs/art/             rendered art sheets and screenshots
```

Tuning lives in `hypetrike/config.py`. Vehicle stats are in `bike.VEHICLES`,
upgrades in `run/upgrades.py`, prices in `meta/shop.py`, and segments in
`track/generator.py`.

Saves go to `~/.local/share/hypetrike/` (Linux), `%APPDATA%\HypeTrike` (Windows)
or `~/Library/Application Support/HypeTrike` (macOS), and to browser
localStorage on the web. Editor tracks are also written as JSON to the
`tracks/` subfolder; JSON files you drop in there show up in the editor's Load list.
