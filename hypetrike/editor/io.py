"""Editor save/load (JSON) and share codes (spec §7.1).

Share code format:  HT1-<urlsafe base64 of zlib(compact JSON)>
  compact JSON = {"n": name, "l": laps, "t": theme,
                  "g": terrain chars, "s": [4 lane chars], "m": material chars}
zlib's checksum catches typos and truncation; decode() then sanitises every
field, so a code from a friend can never crash the game.
"""
import base64
import json
import os
import re
import zlib

import config as C
from track.tiles import (Track, FLAT, RAMP_S, RAMP_L, START, GAP, WHOOPS,
                         COOLANT, MUD, DEBRIS, NONE, DIRT, GRASS, SAND)

PREFIX = "HT1-"
MIN_COLS, MAX_COLS = 8, 400
THEMES = ("valley", "desert", "night", "stadium")

TERRAIN_CH = {FLAT: ".", RAMP_S: "s", RAMP_L: "L", START: "S", GAP: "g", WHOOPS: "w"}
SURF_CH = {NONE: ".", COOLANT: "c", MUD: "m", DEBRIS: "d"}
MAT_CH = {DIRT: "d", GRASS: "g", SAND: "s"}
_inv = lambda d: {v: k for k, v in d.items()}  # noqa: E731
CH_TERRAIN, CH_SURF, CH_MAT = _inv(TERRAIN_CH), _inv(SURF_CH), _inv(MAT_CH)


class CodeError(ValueError):
    pass


def clean_name(name):
    name = re.sub(r"[^A-Za-z0-9 _\-'!.]", "", str(name or "")).strip()
    return (name or "Untitled")[:24]


def to_compact(track):
    return {
        "n": clean_name(track.name), "l": int(track.laps), "t": track.theme,
        "g": "".join(TERRAIN_CH[t] for t in track.terrain),
        "s": ["".join(SURF_CH.get(x, ".") for x in lane) for lane in track.surface],
        "m": "".join(MAT_CH.get(m, "d") for m in track.material),
    }


def from_compact(d):
    if not isinstance(d, dict):
        raise CodeError("not a track")
    g = str(d.get("g", ""))
    n = len(g)
    if not (MIN_COLS <= n <= MAX_COLS):
        raise CodeError(f"track must be {MIN_COLS}-{MAX_COLS} sections long")
    try:
        terrain = [CH_TERRAIN[c] for c in g]
    except KeyError:
        raise CodeError("unknown terrain tile")
    lanes = d.get("s") or []
    if len(lanes) != C.LANES or any(len(str(l)) != n for l in lanes):
        raise CodeError("lane data doesn't match track length")
    try:
        surface = [[CH_SURF[c] for c in str(l)] for l in lanes]
        material = [CH_MAT[c] for c in str(d.get("m", "d" * n))]
    except KeyError:
        raise CodeError("unknown lane or ground tile")
    if len(material) != n:
        raise CodeError("ground data doesn't match track length")
    terrain[0] = START                       # lap line is always column 0
    for i in range(1, n):
        if terrain[i] == START:
            terrain[i] = FLAT
    laps = d.get("l", 2)
    laps = max(1, min(9, int(laps))) if isinstance(laps, (int, float)) else 2
    theme = d.get("t") if d.get("t") in THEMES else "valley"
    return Track(terrain, surface, material, laps, clean_name(d.get("n")), theme)


def encode(track):
    raw = json.dumps(to_compact(track), separators=(",", ":")).encode()
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def decode(code):
    code = re.sub(r"\s+", "", str(code or ""))
    if not code.upper().startswith(PREFIX):
        raise CodeError("codes start with HT1-")
    body = code[len(PREFIX):]
    body += "=" * (-len(body) % 4)
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(body), bufsize=65536)
    except Exception:
        raise CodeError("code is damaged or incomplete")
    if len(raw) > 64_000:
        raise CodeError("code too large")
    try:
        d = json.loads(raw)
    except ValueError:
        raise CodeError("code is damaged")
    return from_compact(d)


# --- JSON files (desktop) + profile storage (all platforms) -----------------------
def to_json(track):
    return json.dumps(to_compact(track), indent=1)


def from_json(text):
    try:
        return from_compact(json.loads(text))
    except ValueError as e:
        if isinstance(e, CodeError):
            raise
        raise CodeError("not valid track JSON")


def tracks_dir():
    from meta.profile import data_dir
    return os.path.join(data_dir(), "tracks")


def _fname(name):
    return re.sub(r"[^A-Za-z0-9_\-]", "_", clean_name(name)) + ".json"


def save_track(profile, track):
    """Save to the profile (localStorage on web) and, on desktop, a JSON file."""
    track.name = clean_name(track.name)
    profile.save_track(track.name, to_compact(track))
    profile.save()
    path = None
    if profile.storage is not None and profile.storage.kind == "file":
        try:
            os.makedirs(tracks_dir(), exist_ok=True)
            path = os.path.join(tracks_dir(), _fname(track.name))
            with open(path, "w", encoding="utf-8") as f:
                f.write(to_json(track))
        except OSError:
            path = None
    return path


def list_tracks(profile):
    """Saved track names. On desktop, JSON files dropped into the tracks folder
    are imported too, so tracks can be shared as plain files."""
    if profile.storage is not None and profile.storage.kind == "file":
        try:
            for fn in sorted(os.listdir(tracks_dir())):
                if not fn.endswith(".json"):
                    continue
                with open(os.path.join(tracks_dir(), fn), encoding="utf-8") as f:
                    try:
                        t = from_json(f.read())
                    except CodeError:
                        continue
                if t.name not in profile.tracks:
                    profile.save_track(t.name, to_compact(t))
        except OSError:
            pass
    return sorted(profile.tracks.keys(), key=str.lower)


def load_track(profile, name):
    d = profile.tracks.get(name)
    if d is not None:
        return from_compact(d)
    raise CodeError("track not found")


def delete_track(profile, name):
    profile.delete_track(name)
    profile.save()
    try:
        os.remove(os.path.join(tracks_dir(), _fname(name)))
    except OSError:
        pass


def blank_track(ncols=40):
    t = Track([START] + [FLAT] * (ncols - 1), laps=2, name="My Track", theme="valley")
    return t
