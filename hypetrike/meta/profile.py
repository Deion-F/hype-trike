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
    "best_heat": 0,          # most races cleared in one run
    "best_biome": 0,         # most biomes cleared in one run
    "vehicles": ["dirt"],
    "liveries": ["flame"],
    "kit_levels": {},        # Starter Kit: {item id: level 0..5}
    "bike_levels": {},       # bike tuning, per vehicle: {vehicle: {stat: level 0..5}}
    "boosts": ["flame"],      # boost colour schemes owned
    "selected": {"vehicle": "dirt", "livery": "flame", "rider": "flame", "boost": "flame"},
    "settings": {"sound": True, "music": True, "smooth": False,
                 "lane_mode": "swipe", "button_scale": 1.0, "swap_sides": False,
                 "touch_ui": "auto", "mouse_steer": "button", "throttle_mode": "one",
                 "mouse_wheelie": "ramps", "heat_gauge": "both", "lane_guide": False,
                 "mouse_lanes": "hover", "record_races": True, "air_lane_lock": True,
                 "sfx_vol": 1.0, "music_vol": 1.0, "settings_v": 3},
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
        # v2: one-button throttle became the default; move older saves over once.
        saved_st = (data or {}).get("settings") or {}
        if saved_st and saved_st.get("settings_v", 1) < 2:
            st["throttle_mode"] = "one"
        # v3: the "button" mouse scheme became the default; move the old default over once.
        if saved_st and saved_st.get("settings_v", 1) < 3 and st.get("mouse_steer") == "angle":
            st["mouse_steer"] = "button"
        st["settings_v"] = 3
        # Theme packs are no longer sold (a run tours every biome): refund once.
        old = d.pop("themes", None) or []
        d.pop("theme_rotation", None)
        if old and not d.get("themes_refunded"):
            from meta.shop import OLD_THEME_PRICES
            d["currency"] += sum(OLD_THEME_PRICES.get(t, 0) for t in set(old))
        d["themes_refunded"] = True
        # The one-off starting upgrades became the levelled Starter Kit: refund once.
        old_kits = d.pop("start_upgrades", None) or []
        d["selected"].pop("start_upgrade", None)
        if old_kits and not d.get("kits_refunded"):
            from meta.shop import OLD_KIT_PRICES
            d["currency"] += sum(OLD_KIT_PRICES.get(k, 0) for k in set(old_kits))
        d["kits_refunded"] = True
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

    def player_livery(self):
        """Sprite key for the chosen bike paint + rider colours (ui.art.livery_key)."""
        from ui.art import livery_key
        sel = self.data["selected"]
        return livery_key(sel.get("livery", "flame"), sel.get("rider"))

    def bike_levels(self, vehicle=None):
        vehicle = vehicle or self.data["selected"]["vehicle"]
        return self.data.setdefault("bike_levels", {}).setdefault(vehicle, {})

    def player_stats(self, vehicle=None):
        """The chosen vehicle at the player's tuning levels (no run upgrades)."""
        from bike import base_stats
        from meta.bike_tune import apply_tune
        vehicle = vehicle or self.data["selected"]["vehicle"]
        return apply_tune(base_stats(vehicle), self.bike_levels(vehicle))

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
