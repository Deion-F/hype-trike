"""Race recordings: replays + tuning data.

A recording holds everything needed to re-simulate a race exactly (physics is
deterministic and rival AIs are seeded): the track (share-code compact form),
the player's stats, rival count/level, the race seed, the throttle mode, and the
player's controls for every simulation tick (run-length encoded). On top of that
it keeps what the tuning tools and the difficulty-tuner agent read without
re-simulating: an event log for the player and every rival, periodic state
samples, and an end-of-race summary.

Engine-agnostic: no pygame. Files are JSON, one per race, in recordings_dir():
  $HYPE_RECORDINGS_DIR, else $HYPE_DATA_DIR/recordings, else <repo>/recordings
  when running from a source checkout, else <user data dir>/recordings.
Tuning passes move them to recordings/archive/<stamp>/ (tools/tuning.py archive)
so the live folder only ever holds recordings nobody has tuned from yet.
On the web build nothing touches disk: the last few recordings stay in memory.
"""
import json
import os
import random
import sys
import time
from dataclasses import asdict

import config as C

VERSION = 1
SAMPLE_EVERY = 6           # player state sample period (ticks)
RIVAL_SAMPLE_EVERY = 30    # rival positions sample period (ticks)
WEB_KEEP = 5               # recordings kept in memory on the web build
CTL_BITS = ("a", "b", "left", "right", "lane_up", "lane_down", "ramp")   # new bits go last (old recordings read 0)
WEB = sys.platform == "emscripten"

# Events worth logging (bike.step / race.step event names).
LOGGED = {"perfect", "land", "rough", "bounce", "crash", "explode", "forgiven", "overheat",
          "cooled", "vent", "heatpad", "coolant", "splash", "lava", "bump", "recovered",
          "lap", "finish", "go"}


def recordings_dir():
    if os.environ.get("HYPE_RECORDINGS_DIR"):
        return os.environ["HYPE_RECORDINGS_DIR"]
    if os.environ.get("HYPE_DATA_DIR"):
        return os.path.join(os.environ["HYPE_DATA_DIR"], "recordings")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(repo, ".git")):
        return os.path.join(repo, "recordings")
    from meta.profile import data_dir
    return os.path.join(data_dir(), "recordings")


def ctl_bits(ctl):
    v = 0
    for i, name in enumerate(CTL_BITS):
        if getattr(ctl, name):
            v |= 1 << i
    return v


def bits_ctl(v):
    from bike import Controls
    return Controls(**{name: bool(v >> i & 1) for i, name in enumerate(CTL_BITS)})


def rle(values):
    out = []
    for v in values:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def unrle(pairs):
    out = []
    for v, n in pairs:
        out.extend([v] * n)
    return out


def _r(v, nd=2):
    return round(float(v), nd)


class Recorder:
    """Attach to a race; call tick() after every race.step(), finish() at the end."""

    def __init__(self, race, livery="flame", context=None, settings=None):
        from editor.io import to_compact
        self.race = race
        tr = race.track
        b = race.bike
        self.data = {
            "v": VERSION,
            "id": time.strftime("%Y%m%d-%H%M%S") + f"-{random.randrange(16 ** 4):04x}",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "context": dict(context or {"kind": "race"}),
            "settings": {k: (settings or {}).get(k) for k in
                         ("throttle_mode", "mouse_steer", "mouse_lanes", "mouse_wheelie", "lane_mode")},
            "track": {**to_compact(tr), "meta": {k: v for k, v in tr.meta.items() if k != "segments"},
                      "segments": tr.meta.get("segments")},
            "race": {"stats": asdict(b.stats), "one_button": b.one_button, "livery": livery,
                     "rivals": len(race.rivals), "rival_level": race.rival_level, "boss": race.boss,
                     "seed": race.seed, "countdown": race.countdown_start},
            "inputs": [],
            "events": [],
            "samples": {"every": SAMPLE_EVERY, "player": [],
                        "rival_every": RIVAL_SAMPLE_EVERY, "rivals": []},
        }
        self._inputs = []
        self._tick = 0
        self._boost = [0, 0, 0]       # ticks at boost level 0/1/2 while riding
        self._air = 0
        self._max_temp = 0.0
        self._speed_sum = 0.0
        self._ride = 0

    @property
    def id(self):
        return self.data["id"]

    def tick(self, ctl, events):
        """One race.step: ctl given to it, events it returned (player's)."""
        race, b = self.race, self.race.bike
        t = self._tick
        self._inputs.append(ctl_bits(ctl))
        tr = race.track
        for e in events:
            if e[0] in LOGGED:
                self.data["events"].append([t, 0, e[0], tr.col_at(b.x) if e[0] != "go" else 0,
                                            *[x for x in e[1:] if isinstance(x, (int, float, str))]])
        for i, ev in race.last_rival_events:
            rb = race.rivals[i]
            for e in ev:
                if e[0] in LOGGED and e[0] not in ("lap", "recovered"):
                    self.data["events"].append([t, i + 1, e[0], tr.col_at(rb.x),
                                                *[x for x in e[1:] if isinstance(x, (int, float, str))]])
        if race.started:
            if b.state == "ride":
                self._boost[b.boost_level] += 1
                self._speed_sum += b.speed
                self._ride += 1
                self._air += b.airborne
            self._max_temp = max(self._max_temp, b.temp)
            if t % SAMPLE_EVERY == 0:
                self.data["samples"]["player"].append(
                    [t, _r(b.x, 1), _r(b.lane_pos), _r(b.speed, 1), _r(b.temp), _r(b.angle, 1),
                     int(b.airborne), b.boost_level, b.state])
            if race.rivals and t % RIVAL_SAMPLE_EVERY == 0:
                self.data["samples"]["rivals"].append([t, [_r(rb.x, 1) for rb in race.rivals]])
        self._tick += 1

    def finish(self, result=None):
        """Close the recording with the race result (RaceScene result dict)."""
        race, b = self.race, self.race.bike
        self.data["inputs"] = rle(self._inputs)
        ev = self.data["events"]
        mine = [e for e in ev if e[1] == 0]
        count = lambda k, who=0: sum(1 for e in ev if e[1] == who and e[2] == k)   # noqa: E731
        crash_reasons = {}
        for e in mine:
            if e[2] == "crash":
                r = e[4] if len(e) > 4 else "?"
                crash_reasons[r] = crash_reasons.get(r, 0) + 1
        rivals = []
        for i, rb in enumerate(race.rivals):
            st = rb.stats
            rivals.append({"finish": race.rival_finish[i], "x": _r(rb.x, 1),
                           "kit": dict(race.rival_kits[i]) if i < len(race.rival_kits) else {},
                           "stats": {"max_speed_a": _r(st.max_speed_a, 1), "max_speed_b": _r(st.max_speed_b, 1),
                                     "land_tolerance": _r(st.land_tolerance, 1),
                                     "pitch_rate": _r(st.pitch_rate, 2)},
                           "crashes": count("crash", i + 1), "explodes": count("explode", i + 1),
                           "overheats": count("overheat", i + 1), "perfect": count("perfect", i + 1)})
        landings = sum(count(k) for k in ("perfect", "land", "rough")) + crash_reasons.get("nose", 0) \
            + crash_reasons.get("loop", 0)
        ride = max(1, self._ride)
        res = dict(result or {})
        self.data["summary"] = {
            "ticks": self._tick,
            "finished": bool(res.get("finished", race.finished)),
            "forfeit": bool(res.get("forfeit", False)),
            "time": race.clock,
            "laps": list(race.lap_times),
            "position": race.position(),
            "field": len(race.rivals) + 1,
            "target_met": res.get("target_met"),
            "distance": _r(max(0.0, b.x - C.START_X), 1),
            "crashes": crash_reasons,
            "explodes": count("explode"),
            "overheats": count("overheat"),
            "forgiven": count("forgiven"),
            "vents": count("vent"),
            "landings": landings,
            "perfect": count("perfect"),
            "rough": count("rough"),
            "bounces": count("bounce"),
            "pads": count("heatpad") + count("coolant"),
            "splashes": count("splash"),
            "lava": count("lava"),
            "boost_share": [_r(n / ride, 3) for n in self._boost],
            "air_share": _r(self._air / ride, 3),
            "avg_speed": _r(self._speed_sum / ride, 1),
            "max_temp": _r(self._max_temp, 1),
            "rivals": rivals,
        }
        return self.data


# --- storage ----------------------------------------------------------------------------
_web_mem = []


def save(data, folder=None):
    """Write a finished recording. Returns its path (or "memory:<id>" on the web)."""
    if WEB:
        _web_mem.append(data)
        del _web_mem[:-WEB_KEEP]
        return "memory:" + data["id"]
    folder = folder or recordings_dir()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"race-{data['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return path


def list_recordings(folder=None):
    """Live (not archived) recordings, newest first: [(path_or_key, data)]."""
    if WEB:
        return [("memory:" + d["id"], d) for d in reversed(_web_mem)]
    folder = folder or recordings_dir()
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder), reverse=True):
        if name.startswith("race-") and name.endswith(".json"):
            p = os.path.join(folder, name)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    out.append((p, json.load(f)))
            except (OSError, ValueError):
                continue
    return out


# --- re-simulation ------------------------------------------------------------------------------
def rebuild(data):
    """(track, stats, race_kwargs, one_button, livery, controls list) from a recording."""
    from bike import BikeStats
    from editor.io import from_compact
    tr_d = data["track"]
    track = from_compact({k: tr_d[k] for k in ("n", "l", "t", "g", "s", "m")})
    track.meta.update(tr_d.get("meta") or {})
    if tr_d.get("segments"):
        track.meta["segments"] = tr_d["segments"]
    rd = data["race"]
    st = dict(rd["stats"])
    st["grip"] = {int(k): v for k, v in st["grip"].items()}
    stats = BikeStats(**st)
    kwargs = dict(rivals=rd["rivals"], rival_level=rd["rival_level"], seed=rd["seed"], boss=rd.get("boss"))
    return track, stats, kwargs, rd["one_button"], rd.get("livery", "flame"), unrle(data["inputs"])


def resimulate(data):
    """Re-run a recording headless; returns the Race at the end (for checks/tools)."""
    from race import Race
    track, stats, kw, one, _, ctl = rebuild(data)
    race = Race(track, stats, countdown=data["race"].get("countdown", True) != 0, **kw)
    race.bike.one_button = one
    for v in ctl:
        race.step(bits_ctl(v))
    return race
