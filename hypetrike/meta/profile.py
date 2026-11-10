"""Persistent profile: meta-currency, unlocks, settings, saved editor tracks.

Storage backends (spec §8 Persistence):
  * desktop: JSON file in the OS app-data directory
  * web (pygbag): browser localStorage through the JS bridge
  * fallback: in-memory only (profile still works, just not persisted)
"""
import json
import os
import sys

KEY = "hypetrike_profile_v1"
WEB = sys.platform == "emscripten"


def data_dir():
    if os.environ.get("HYPE_DATA_DIR"):
        return os.environ["HYPE_DATA_DIR"]
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "HypeTrike")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/HypeTrike")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "hypetrike")


class Storage:
    """get/set of one JSON string under KEY."""

    def __init__(self):
        self.kind = "memory"
        self._mem = None
        self._ls = None
        if WEB:
            try:
                import platform as _p
                self._ls = _p.window.localStorage
                self.kind = "localStorage"
            except Exception:
                self._ls = None
        else:
            try:
                os.makedirs(data_dir(), exist_ok=True)
                self.path = os.path.join(data_dir(), "profile.json")
                self.kind = "file"
            except OSError:
                self.kind = "memory"

    def read(self):
        try:
            if self.kind == "localStorage":
                v = self._ls.getItem(KEY)
                return None if v in (None, "null", "undefined") else str(v)
            if self.kind == "file":
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        return f.read()
                return None
        except Exception:
            self.kind = "memory"
        return self._mem

    def write(self, text):
        try:
            if self.kind == "localStorage":
                self._ls.setItem(KEY, text)
                return True
            if self.kind == "file":
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, self.path)
                return True
        except Exception:
            self.kind = "memory"
        self._mem = text
        return False


DEFAULTS = {
    "currency": 0,
    "lifetime_currency": 0,
    "runs": 0,
    "wins": 0,
    "best_heat": 0,
    "vehicles": ["dirt"],
    "liveries": ["flame"],
    "themes": ["valley"],
    "start_upgrades": [],
    "selected": {"vehicle": "dirt", "livery": "flame", "start_upgrade": None},
    "settings": {"sound": True, "music": True, "smooth": False,
                 "lane_mode": "swipe", "button_scale": 1.0, "swap_sides": False,
                 "touch_ui": "auto", "mouse_steer": "angle", "throttle_mode": "classic",
                 "sfx_vol": 1.0, "music_vol": 1.0},
    "tracks": {},
    "best_laps": {},
}


class Profile:
    def __init__(self, data=None, storage=None):
        self.storage = storage
        d = json.loads(json.dumps(DEFAULTS))
        if data:
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k].update(v)
                else:
                    d[k] = v
        # Older saves had On/Off toggles; the volume sliders replace them (0% = off).
        st = d["settings"]
        for flag, vol in (("sound", "sfx_vol"), ("music", "music_vol")):
            if not st.get(flag, True):
                st[vol] = 0.0
                st[flag] = True
        if st.get("mouse_steer") is True:      # old On/Off setting
            st["mouse_steer"] = "angle"
        self.data = d

    # convenience accessors
    def __getattr__(self, name):
        if name in ("data", "storage"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(name)

    @classmethod
    def load(cls, storage=None):
        storage = storage or Storage()
        raw = storage.read()
        data = None
        if raw:
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
        return cls(data, storage)

    def save(self):
        if self.storage is None:
            self.storage = Storage()
        return self.storage.write(json.dumps(self.data, separators=(",", ":")))

    # -- economy --------------------------------------------------------------
    def earn(self, amount):
        amount = int(amount)
        self.data["currency"] += amount
        self.data["lifetime_currency"] += amount

    def spend(self, amount):
        if self.data["currency"] < amount:
            return False
        self.data["currency"] -= amount
        return True

    def owns(self, kind, item):
        return item in self.data[kind]

    def unlock(self, kind, item):
        if item not in self.data[kind]:
            self.data[kind].append(item)

    # -- tracks -------------------------------------------------------------------
    def save_track(self, name, track_dict):
        self.data["tracks"][name] = track_dict

    def delete_track(self, name):
        self.data["tracks"].pop(name, None)

    def record_lap(self, name, ticks):
        best = self.data["best_laps"].get(name)
        if best is None or ticks < best:
            self.data["best_laps"][name] = ticks
            return True
        return False
