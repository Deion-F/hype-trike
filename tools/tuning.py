"""Race-recording review + difficulty tuning tool.

  python tools/tuning.py summary            one line per live recording
  python tools/tuning.py report [--json]    aggregate difficulty report (by run heat / depth)
  python tools/tuning.py show ID            timeline of one recording (ID prefix is enough)
  python tools/tuning.py sim [--seeds N] [--mode one|classic|both]
                                            simulated runs with AI players of several skill
                                            tiers -> target-met rate per heat (the curve)
  python tools/tuning.py mods [--json]      how hard each modifier (disadvantage) made the
                                            recorded heats vs unmodified heats nearby
  python tools/tuning.py modsim [--seeds N] [--mode one|classic]
                                            AI players race the modifier heats with each
                                            modifier forced -> measured hardness + a suggested
                                            run/manager.py MODIFIER_HARDNESS
  python tools/tuning.py archive --note "what was tuned" [ID ...]
                                            move recordings (all, or the given IDs) to
                                            recordings/archive/<stamp>/ with a NOTE.md

Recordings live in recordings_dir() (hypetrike/replay.py): <repo>/recordings when
running from the checkout. Only live (unarchived) recordings are read, so once a
tuning pass has used them, archive them so they don't count twice.
"""
import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hypetrike")
sys.path.insert(0, ROOT)

import config as C  # noqa: E402
import replay as rp  # noqa: E402

# What a healthy curve looks like: share of attempts that meet each run heat's
# target, for an average player who keeps improving and picks upgrades. Early
# heats should be comfortable, the final a real fight. Used to flag heats in
# the report and the sim; tune the game toward it, not the other way round.
TARGET_CURVE = [0.95, 0.88, 0.78, 0.68, 0.58, 0.45]
CURVE_SLACK = 0.12


def secs(ticks):
    return f"{ticks / C.FPS:.1f}s" if ticks is not None else "-"


def group_key(d):
    c = d.get("context", {})
    if c.get("kind") == "run":
        return ("run", c.get("heat", 0))
    return (c.get("kind", "race"), (d["track"].get("meta") or {}).get("depth", c.get("depth")))


def load(folder=None):
    return rp.list_recordings(folder)


# --- summary / show ----------------------------------------------------------------------------
def cmd_summary(args):
    items = load(args.dir)
    if not items:
        print("no live recordings in", args.dir or rp.recordings_dir())
        return
    for path, d in items:
        s, c = d.get("summary", {}), d.get("context", {})
        what = f"run h{c.get('heat', 0) + 1}" if c.get("kind") == "run" else c.get("kind", "?")
        res = "quit" if s.get("forfeit") else ("DNF" if not s.get("finished") else
                                              f"P{s.get('position')}/{s.get('field')} {secs(s.get('time'))}")
        crashes = sum((s.get("crashes") or {}).values())
        print(f"{d['id']}  {what:<11} {d['track'].get('t', '?'):<8} {d['race']['stats']['vehicle']:<9} "
              f"{'one' if d['race']['one_button'] else 'classic':<7} {res:<16} "
              f"crash {crashes} boom {s.get('explodes', 0)} perfect {s.get('perfect', 0)}/{s.get('landings', 0)} "
              f"target {s.get('target_met')}")


def cmd_show(args):
    items = [(p, d) for p, d in load(args.dir) if d["id"].startswith(args.id)]
    if not items:
        sys.exit(f"no recording matching {args.id}")
    path, d = items[0]
    segs = d["track"].get("segments") or []
    print(f"{d['id']}  {path}")
    print("context:", json.dumps(d.get("context")))
    print("track:", d["track"].get("n"), d["track"].get("t"), "meta", json.dumps(d["track"].get("meta")))
    print("race:", {k: v for k, v in d["race"].items() if k != "stats"})
    print("summary:", json.dumps(d.get("summary"), indent=1))
    print("\nevents (t, who 0=player, kind, column/segment, extra):")
    for t, who, kind, col, *extra in d["events"]:
        if who and not args.rivals and kind not in ("crash", "explode", "finish"):
            continue
        seg = segs[col] if 0 <= col < len(segs) else ""
        print(f"  {secs(t):>7} {'YOU' if who == 0 else f'cpu{who}':<4} {kind:<9} col {col:<3} {seg:<14} "
              f"{' '.join(map(str, extra))}")


# --- report -----------------------------------------------------------------------------------------
def aggregate(items):
    groups = defaultdict(list)
    for _, d in items:
        if "summary" in d:
            groups[group_key(d)].append(d)
    rows = []
    crash_segs = Counter()
    for key in sorted(groups, key=lambda k: (k[0] != "run", str(k[0]), k[1] if k[1] is not None else -1)):
        ds = groups[key]
        n = len(ds)
        S = [d["summary"] for d in ds]
        fin = [s for s in S if s.get("finished")]
        met = [s.get("target_met") for s in S if s.get("target_met") is not None]
        gaps = []
        for s in fin:
            rf = [r["finish"] for r in s.get("rivals", []) if r.get("finish") is not None]
            if rf:
                gaps.append(s["time"] - min(rf))         # >0: behind the best rival
        reasons = Counter()
        for s in S:
            reasons.update(s.get("crashes") or {})
        for d in ds:
            segs = d["track"].get("segments") or []
            for t, who, kind, col, *_ in d["events"]:
                if who == 0 and kind in ("crash", "explode") and 0 <= col < len(segs):
                    crash_segs[(segs[col], kind)] += 1
        land = sum(s.get("landings", 0) for s in S) or 1
        rows.append({
            "group": f"{key[0]} heat {key[1] + 1}" if key[0] == "run" else f"{key[0]} depth {key[1]}",
            "races": n,
            "finished": round(len(fin) / n, 2),
            "target_met": round(sum(met) / len(met), 2) if met else None,
            "curve_goal": TARGET_CURVE[key[1]] if key[0] == "run" and key[1] is not None and key[1] < len(TARGET_CURVE) else None,
            "avg_position": round(sum(s.get("position", 0) for s in S) / n, 2),
            "avg_gap_to_best_rival_s": round(sum(gaps) / len(gaps) / C.FPS, 2) if gaps else None,
            "crashes_per_race": round(sum(reasons.values()) / n, 2),
            "crash_reasons": dict(reasons),
            "explodes_per_race": round(sum(s.get("explodes", 0) for s in S) / n, 2),
            "overheats_per_race": round(sum(s.get("overheats", 0) for s in S) / n, 2),
            "perfect_rate": round(sum(s.get("perfect", 0) for s in S) / land, 2),
            "rough_rate": round(sum(s.get("rough", 0) for s in S) / land, 2),
            "boost_share": round(sum(s.get("boost_share", [0, 0, 0])[1] for s in S) / n, 2),
            "super_share": round(sum(s.get("boost_share", [0, 0, 0])[2] for s in S) / n, 2),
            "avg_speed": round(sum(s.get("avg_speed", 0) for s in S) / n, 1),
            "rival_crashes_per_race": round(sum(sum(r.get("crashes", 0) + r.get("explodes", 0)
                                                    for r in s.get("rivals", [])) for s in S) / n, 2),
            "upgrades": round(sum(len(d.get("context", {}).get("upgrades") or []) for d in ds) / n, 1),
            "quits": sum(1 for s in S if s.get("forfeit")),
        })
    return rows, crash_segs


def cmd_report(args):
    items = load(args.dir)
    rows, segs = aggregate(items)
    if args.json:
        print(json.dumps({"recordings": len(items), "groups": rows,
                          "crash_segments": [[s, k, n] for (s, k), n in segs.most_common()]}, indent=1))
        return
    print(f"# Difficulty report - {len(items)} live recordings ({args.dir or rp.recordings_dir()})\n")
    if not rows:
        print("No recordings yet. Play some races (recordings are on by default), then run this again.")
        return
    for r in rows:
        flag = ""
        if r["curve_goal"] is not None and r["target_met"] is not None:
            d = r["target_met"] - r["curve_goal"]
            flag = "  <-- TOO HARD" if d < -CURVE_SLACK else "  <-- TOO EASY" if d > CURVE_SLACK else "  (on curve)"
        print(f"## {r['group']}  ({r['races']} races){flag}")
        for k, v in r.items():
            if k not in ("group", "races"):
                print(f"- {k}: {v}")
        print()
    print("## Where the player crashes (segment, kind, count)")
    for (seg, kind), n in segs.most_common(12):
        print(f"- {seg}: {kind} x{n}")
    if len(items) < 6:
        print("\nNote: few recordings - treat these numbers as hints, back them with `sim`.")


# --- sim -----------------------------------------------------------------------------------------------
TIERS = {   # AI stand-ins for players: (skill, blunder, miss)
    "novice": (0.5, 0.12, 0.30),
    "average": (0.75, 0.05, 0.12),
    "good": (0.95, 0.01, 0.03),
}


class OneButtonPilot:
    """Drives one-button mode with a GhostAI's lean/lanes: holds the button to
    climb to a target heat, lets go above it (into the red only when daring)."""

    def __init__(self, ai, keep):
        self.ai, self.keep, self._hold = ai, keep, True

    def controls(self, bike):
        c = self.ai.controls(bike)
        if bike.temp >= self.keep:
            self._hold = False
        elif bike.temp < self.keep - 1.5:
            self._hold = True
        c.a, c.b = self._hold, False
        return c


def sim_run(seed, tier, mode, learning=False):
    """Play every heat of a run (even after a miss) with an AI player that picks
    the first upgrade offered. learning: the player goes novice -> good."""
    from race import Race
    from run.manager import RunState, RUN_HEATS
    from run.upgrades import offer
    from track.validator import GhostAI
    r = RunState(seed=seed, mode=mode)
    out = []
    for i in range(RUN_HEATS):
        r.heat_i = i
        h = r.prepare_heat()
        st = r.stats_for_heat(h)
        if learning:
            k = i / (RUN_HEATS - 1)
            a, b = TIERS["novice"], TIERS["good"]
            skill, blunder, miss = (a[j] + (b[j] - a[j]) * k for j in range(3))
        else:
            skill, blunder, miss = TIERS[tier]
        ai = GhostAI(turbo=True, turbo_temp=24, skill=skill, blunder=blunder, miss=miss, seed=seed * 7 + i)
        race = Race(h.track, st, rivals=h.rivals, rival_level=h.rival_level, seed=h.seed, countdown=False)
        race.bike.one_button = mode == "one"
        pilot = OneButtonPilot(ai, C.ONE_SUPER_AT - 1 + 2 * skill) if mode == "one" else ai
        while not race.finished and race.time_ticks < 60 * 300:
            race.step(pilot.controls(race.bike))
        res = {"finished": race.finished, "time": race.time_ticks, "position": race.position(),
               "perfect": race.bike.stats_counters["perfect"], "distance": race.bike.x}
        out.append({"heat": i, "met": h.target.check(res), "position": res["position"],
                    "crashes": race.bike.stats_counters["crashes"]})
        o = offer(r.rng, r.upgrades, 3, mode)
        if o:
            r.upgrades.append(o[0].id)
    return out


def cmd_sim(args):
    from run.manager import RUN_HEATS
    modes = ["one", "classic"] if args.mode == "both" else [args.mode]
    tiers = list(TIERS) + ["learning"]
    t0 = time.time()
    result = {}
    for mode in modes:
        for tier in tiers:
            per = [[] for _ in range(RUN_HEATS)]
            for seed in range(args.seeds):
                for h in sim_run(1000 + seed, tier, mode, learning=tier == "learning"):
                    per[h["heat"]].append(h)
            result[(mode, tier)] = per
    if args.json:
        print(json.dumps({f"{m}/{t}": [{"met": round(sum(x["met"] for x in p) / len(p), 2),
                                         "pos": round(sum(x["position"] for x in p) / len(p), 2),
                                         "crashes": round(sum(x["crashes"] for x in p) / len(p), 2)}
                                        for p in per] for (m, t), per in result.items()}, indent=1))
        return
    print(f"# Simulated difficulty curve - {args.seeds} runs per row ({time.time() - t0:.0f}s)")
    print("target met % per heat (avg place); goal for 'learning':",
          " ".join(f"{int(g * 100)}" for g in TARGET_CURVE), "\n")
    for (mode, tier), per in result.items():
        cells = []
        for i, p in enumerate(per):
            met = sum(x["met"] for x in p) / len(p)
            pos = sum(x["position"] for x in p) / len(p)
            mark = ""
            if tier == "learning":
                d = met - TARGET_CURVE[i]
                mark = "!" if abs(d) > CURVE_SLACK else ""
            cells.append(f"{int(met * 100):>3}%{mark:<1}({pos:.1f})")
        print(f"{mode:<7} {tier:<9} " + "  ".join(cells))
    print("\n! = more than", int(CURVE_SLACK * 100), "points off the goal curve")


# --- modifiers (disadvantages) ------------------------------------------------------------------
def _race_score(s):
    """0..1 how well a recorded race went (target met, place, crashes)."""
    met = 1.0 if s.get("target_met") else 0.0
    field = max(1, s.get("field") or 4)
    place = 1.0 - ((s.get("position") or field) - 1) / max(1, field - 1)
    return met, place, sum((s.get("crashes") or {}).values()) + s.get("explodes", 0)


def cmd_mods(args):
    """Per modifier: target-met, place, crashes in recorded run heats, against
    unmodified run heats at the same or a neighbouring heat index."""
    from run.manager import MODIFIERS, MODIFIER_HARDNESS
    by_mod, base = defaultdict(list), defaultdict(list)
    for _, d in load(args.dir):
        c, s = d.get("context", {}), d.get("summary")
        if c.get("kind") != "run" or not s or s.get("forfeit"):
            continue
        row = (c.get("heat", 0), *_race_score(s), s.get("explodes", 0))
        (by_mod[c["modifier"]] if c.get("modifier") else base[c.get("heat", 0)]).append(row)
    out = {}
    for m in MODIFIERS:
        rows = by_mod.get(m, [])
        if not rows:
            out[m] = {"races": 0}
            continue
        ref = [r for h, *_ in rows for r in base.get(h, []) + base.get(h - 1, []) + base.get(h + 1, [])]
        avg = lambda rs, k: round(sum(r[k] for r in rs) / len(rs), 2) if rs else None  # noqa: E731
        out[m] = {"races": len(rows), "baseline_races": len(ref),
                  "target_met": avg(rows, 1), "baseline_target_met": avg(ref, 1),
                  "place_score": avg(rows, 2), "baseline_place_score": avg(ref, 2),
                  "crashes": avg(rows, 3), "baseline_crashes": avg(ref, 3),
                  "explodes": avg(rows, 4),
                  "current_hardness": MODIFIER_HARDNESS.get(m)}
        if ref:
            out[m]["met_drop"] = round(out[m]["baseline_target_met"] - out[m]["target_met"], 2)
    if args.json:
        print(json.dumps(out, indent=1))
        return
    print("# Modifiers in recorded run heats (vs unmodified heats at the same +-1 heat)\n")
    for m, r in out.items():
        name = MODIFIERS[m][0]
        if not r["races"]:
            print(f"- {m} ({name}): no recordings")
            continue
        print(f"- {m} ({name}): {r['races']} races, target met {r['target_met']} vs {r['baseline_target_met']}, "
              f"place {r['place_score']} vs {r['baseline_place_score']}, crashes {r['crashes']} vs "
              f"{r['baseline_crashes']}, blow-ups {r['explodes']}  [hardness now {r['current_hardness']}]")
    print("\nRecorded modifier heats are rare (2 per run): back any change with `modsim`.")


def modsim(seeds, mode="one", tiers=("average", "learning")):
    """Race the modifier heats of `seeds` runs once per modifier (and once with
    none), same tracks seeds and upgrades. Returns {mod: {met, place, crashes}}."""
    from race import Race
    from run.manager import RunState, MODIFIERS, MODIFIER_HEATS, RUN_HEATS
    from run.upgrades import offer
    from track.validator import GhostAI
    res = {m: {"met": [], "place": [], "crashes": []} for m in [None] + list(MODIFIERS)}
    for seed in range(seeds):
        for tier in tiers:
            for slot in MODIFIER_HEATS:
                for m in res:
                    r = RunState(seed=2000 + seed, mode=mode)
                    for _ in range(slot):                   # the upgrades you'd have by then
                        o = offer(r.rng, r.upgrades, 3, mode)
                        if o:
                            r.upgrades.append(o[0].id)
                    r.heat_i = slot
                    h = r.heat
                    h.target.modifier = m
                    h.track = None
                    r.prepare_heat()
                    st = r.stats_for_heat(h)
                    if tier == "learning":
                        k = slot / (RUN_HEATS - 1)
                        a, b = TIERS["novice"], TIERS["good"]
                        skill, blunder, miss = (a[j] + (b[j] - a[j]) * k for j in range(3))
                    else:
                        skill, blunder, miss = TIERS[tier]
                    ai = GhostAI(turbo=True, turbo_temp=24, skill=skill, blunder=blunder, miss=miss,
                                 seed=seed * 7 + slot)
                    race = Race(h.track, st, rivals=h.rivals, rival_level=h.rival_level, seed=h.seed,
                                countdown=False)
                    race.bike.one_button = mode == "one"
                    pilot = OneButtonPilot(ai, C.ONE_SUPER_AT - 1 + 2 * skill) if mode == "one" else ai
                    while not race.finished and race.time_ticks < 60 * 300:
                        race.step(pilot.controls(race.bike))
                    out = {"finished": race.finished, "time": race.time_ticks, "position": race.position()}
                    res[m]["met"].append(1.0 if h.target.check(out) else 0.0)
                    res[m]["place"].append(1.0 - (out["position"] - 1) / max(1, h.rivals))
                    res[m]["crashes"].append(race.bike.stats_counters["crashes"])
    return {m: {k: round(sum(v) / len(v), 3) for k, v in d.items()} for m, d in res.items()}


def suggest_hardness(sim):
    """Hardness 0..1 from how much each modifier lowers the target-met rate and
    the place score vs no modifier (min-max scaled across the modifiers)."""
    base = sim[None]
    hurt = {m: (base["met"] - r["met"]) + 0.5 * (base["place"] - r["place"])
            for m, r in sim.items() if m is not None}
    lo, hi = min(hurt.values()), max(hurt.values())
    span = hi - lo
    return hurt, {m: round(0.5 if span < 0.02 else 0.1 + 0.8 * (h - lo) / span, 2) for m, h in hurt.items()}


def cmd_modsim(args):
    from run.manager import MODIFIERS, MODIFIER_HARDNESS
    t0 = time.time()
    sim = modsim(args.seeds, args.mode)
    hurt, sug = suggest_hardness(sim)
    if args.json:
        print(json.dumps({"sim": {str(k): v for k, v in sim.items()}, "hurt": hurt, "suggested": sug,
                          "current": MODIFIER_HARDNESS}, indent=1))
        return
    print(f"# Modifier sim - {args.seeds} runs x (average, learning) x heats 3 and 5, mode {args.mode} "
          f"({time.time() - t0:.0f}s)\n")
    b = sim[None]
    print(f"{'(none)':<12} met {b['met']:.2f}  place {b['place']:.2f}  crashes {b['crashes']:.2f}")
    for m in sorted(hurt, key=hurt.get, reverse=True):
        r = sim[m]
        print(f"{m:<12} met {r['met']:.2f}  place {r['place']:.2f}  crashes {r['crashes']:.2f}  "
              f"hurt {hurt[m]:+.2f}  -> hardness {sug[m]} (now {MODIFIER_HARDNESS.get(m)})  {MODIFIERS[m][0]}")
    print("\nSuggested MODIFIER_HARDNESS =", json.dumps(sug))
    print("Hardest first. Only adopt a value whose 'hurt' is clearly apart from its neighbours"
          " (rerun with more --seeds if two are within ~0.05).")


# --- archive ------------------------------------------------------------------------------------------------
def cmd_archive(args):
    folder = args.dir or rp.recordings_dir()
    items = load(args.dir)
    if args.ids:
        items = [(p, d) for p, d in items if any(d["id"].startswith(i) for i in args.ids)]
    if not items:
        print("nothing to archive")
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(folder, "archive", stamp)
    os.makedirs(dest, exist_ok=True)
    lines = [f"# Tuning pass {stamp}", "", args.note or "(no note)", "", "## Recordings used", ""]
    for p, d in items:
        s = d.get("summary", {})
        lines.append(f"- {os.path.basename(p)}: {d.get('context', {}).get('kind')} "
                     f"P{s.get('position')}/{s.get('field')} target {s.get('target_met')}")
        shutil.move(p, os.path.join(dest, os.path.basename(p)))
    with open(os.path.join(dest, "NOTE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"archived {len(items)} recordings to {dest}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="recordings folder (default: replay.recordings_dir())")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    p = sub.add_parser("report"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("show"); p.add_argument("id"); p.add_argument("--rivals", action="store_true")
    p = sub.add_parser("sim"); p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--mode", default="one", choices=["one", "classic", "both"]); p.add_argument("--json", action="store_true")
    p = sub.add_parser("archive"); p.add_argument("--note", default=""); p.add_argument("ids", nargs="*")
    p = sub.add_parser("mods"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("modsim"); p.add_argument("--seeds", type=int, default=4)
    p.add_argument("--mode", default="one", choices=["one", "classic"]); p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    {"summary": cmd_summary, "report": cmd_report, "show": cmd_show, "sim": cmd_sim,
     "archive": cmd_archive, "mods": cmd_mods, "modsim": cmd_modsim}[args.cmd](args)


if __name__ == "__main__":
    main()
