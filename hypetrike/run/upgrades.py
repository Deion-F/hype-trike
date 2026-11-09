"""Upgrade pool and stacking (spec §6.2). Effects stack multiplicatively where
that makes sense; each upgrade has a stack cap."""
import random
from dataclasses import dataclass

from track.tiles import GRASS, SAND


@dataclass(frozen=True)
class Upgrade:
    id: str
    name: str
    category: str
    desc: str
    max_stacks: int = 3
    weight: float = 1.0


def _mul(attr, k):
    def f(s):
        setattr(s, attr, getattr(s, attr) * k)
    return f


def _add(attr, v):
    def f(s):
        setattr(s, attr, getattr(s, attr) + v)
    return f


def _both(*fs):
    def f(s):
        for g in fs:
            g(s)
    return f


def _all_terrain(s):
    for m in (GRASS, SAND):
        s.grip[m] = min(1.0, s.grip[m] * 1.08)


UPGRADES = {}
EFFECTS = {}


def _reg(up, effect):
    UPGRADES[up.id] = up
    EFFECTS[up.id] = effect


# --- Engine ---------------------------------------------------------------------
_reg(Upgrade("big_bore", "Big Bore", "Engine", "+4% top speed (about +2)"),
     _both(_mul("max_speed_a", 1.04), _mul("max_speed_b", 1.04)))
_reg(Upgrade("cool_head", "Cool Head", "Engine", "Engine heats 15% slower"),
     _both(_mul("heat_a", 0.85), _mul("heat_b", 0.85)))
_reg(Upgrade("turbo_tune", "Turbo Tune", "Engine", "Turbo builds 20% less heat"),
     _mul("heat_b", 0.8))
_reg(Upgrade("quick_shift", "Quick Shift", "Engine", "Accelerate 15% faster"),
     _mul("accel_interval", 0.85))
# --- Cooling -------------------------------------------------------------------------
_reg(Upgrade("cryo_pads", "Cryo Pads", "Cooling", "Coolant pads also freeze heat for 1.5 s"),
     _add("coolant_chill", 90))
_reg(Upgrade("radiator", "Radiator", "Cooling", "Cool down faster while coasting"),
     _both(_add("passive_cool", 0.03), _mul("cool_coast", 1.3)))
_reg(Upgrade("heat_sink", "Heat Sink", "Cooling", "Overheat stalls are 40% shorter", max_stacks=2),
     _mul("overheat_ticks", 0.6))
# --- Air control ---------------------------------------------------------------------
_reg(Upgrade("gyro", "Gyro Bars", "Air", "Lean 20% faster in the air"),
     _mul("pitch_rate", 1.2))
_reg(Upgrade("soft_shocks", "Soft Shocks", "Air", "Wider safe landing angle (+20%)"),
     _both(_mul("land_tolerance", 1.2), _mul("land_perfect", 1.15)))
_reg(Upgrade("steady_nose", "Steady Nose", "Air", "Nose drops 30% slower mid-air"),
     _mul("nose_drop", 0.7))
# --- Recovery -------------------------------------------------------------------------
_reg(Upgrade("track_boots", "Track Boots", "Recovery", "Jog back 25% faster after a crash"),
     _mul("crash_ticks", 0.75))
_reg(Upgrade("second_wind", "Second Wind", "Recovery", "One crash forgiven this run", max_stacks=2, weight=0.7),
     _add("crash_forgives", 1))
_reg(Upgrade("mud_tires", "Mud Tyres", "Recovery", "Mud slows you 30% less", max_stacks=2),
     _mul("mud_speed", 1.3))
_reg(Upgrade("all_terrain", "All-Terrain Kit", "Recovery", "+8% grip on grass and sand", max_stacks=2),
     _all_terrain)
# --- Economy ----------------------------------------------------------------------------
_reg(Upgrade("sponsor", "Sponsor Deal", "Economy", "+15% coins from this run"),
     _mul("currency_mult", 1.15))
_reg(Upgrade("style_points", "Style Points", "Economy", "25% chance of bonus coins per perfect landing"),
     _add("perfect_bonus_chance", 0.25))

CATEGORY_COLORS = {
    "Engine": (255, 120, 60), "Cooling": (64, 200, 255), "Air": (190, 140, 255),
    "Recovery": (90, 220, 110), "Economy": (255, 196, 0),
}


def apply_upgrades(stats, ids):
    s = stats.copy()
    for uid in ids:
        EFFECTS[uid](s)
    s.overheat_ticks = int(s.overheat_ticks)
    s.crash_ticks = int(s.crash_ticks)
    return s


def offer(rng: random.Random, owned, n=3):
    """n distinct upgrades, excluding ones at their stack cap."""
    pool = [u for u in UPGRADES.values() if owned.count(u.id) < u.max_stacks]
    picks = []
    while pool and len(picks) < n:
        total = sum(u.weight for u in pool)
        r = rng.random() * total
        for u in pool:
            r -= u.weight
            if r <= 0:
                picks.append(u)
                pool.remove(u)
                break
    return picks
