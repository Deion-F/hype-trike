"""Upgrade pool and stacking (spec §6.2). Effects stack multiplicatively where
that makes sense; each upgrade has a stack cap.

Built around the two throttle modes (setting "throttle_mode"):
  "one"     (default) heat IS the throttle: warm up, ride the boost band, dip
            into the red for super boost, never reach the top (it blows up).
  "classic" A = throttle, B = turbo that builds heat toward an overheat stall.
Each upgrade lists the modes it is offered in; a few read differently per mode
(name_one / desc_one) because the same stat plays a different role there."""
import random
from dataclasses import dataclass

import config as C
from track.tiles import GRASS, SAND

MODES = ("one", "classic")


@dataclass(frozen=True)
class Upgrade:
    id: str
    name: str
    category: str
    desc: str
    max_stacks: int = 3
    weight: float = 1.0
    modes: tuple = MODES
    name_one: str = ""            # name in one-button mode, if it differs
    desc_one: str = ""            # description in one-button mode, if it differs

    def title(self, mode="one"):
        return self.name_one if mode == "one" and self.name_one else self.name

    def text(self, mode="one"):
        return self.desc_one if mode == "one" and self.desc_one else self.desc


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


ONE = ("one",)

# --- Engine: raw speed ------------------------------------------------------------
_reg(Upgrade("big_bore", "Big Bore", "Engine", "+4% top speed in every heat band"),
     _both(_mul("max_speed_a", 1.04), _mul("max_speed_b", 1.04)))
_reg(Upgrade("quick_shift", "Quick Shift", "Engine", "Accelerate 15% faster",
             desc_one="Speed catches up to your heat 15% faster"),
     _mul("accel_interval", 0.85))
_reg(Upgrade("supercharger", "Supercharger", "Engine", "+2 top speed in the red (super boost)",
             max_stacks=2, modes=ONE),
     _add("super_extra", 2))
_reg(Upgrade("turbo_tune", "Turbo Tune", "Engine", "Turbo builds 20% less heat",
             name_one="Long Boost", desc_one="Heat climbs 20% slower once boosting: longer boosts"),
     _mul("heat_b", 0.8))

# --- Heat: managing the gauge -------------------------------------------------------------
_reg(Upgrade("warm_up", "Quick Warm-Up", "Heat",
             "Cold engine heats 40% faster: boost sooner off the line and after crashes",
             max_stacks=2, modes=ONE),
     _mul("warmup_mult", 1.4))
_reg(Upgrade("heat_wrap", "Heat Wrap", "Heat",
             "Heat drains 35% slower when you let go: ease off and keep your speed",
             max_stacks=2, modes=ONE),
     _mul("cool_coast", 0.65))
_reg(Upgrade("cool_head", "Cool Head", "Heat",
             "Heat climbs 35% slower past 27: more turbo before overheating",
             max_stacks=2, desc_one="Heat climbs 35% slower in the red: longer super boosts"),
     _mul("red_heat_mult", 0.65))
_reg(Upgrade("radiator", "Radiator", "Heat",
             "Once per race, an overheat vents the engine instead of stalling",
             max_stacks=2, weight=0.8,
             desc_one="Once per race, a blow-up vents the engine back to boost instead"),
     _add("vent_charges", 1))
_reg(Upgrade("cryo_pads", "Cryo Pads", "Heat", "Coolant pads also freeze heat for 1.5 s",
             name_one="Pad Lock", desc_one="Heat pads lock your heat for 1.5 s: surf the boost"),
     _add("coolant_chill", 90))
_reg(Upgrade("heat_sink", "Heat Sink", "Heat", "Overheat stalls are 40% shorter", max_stacks=2,
             desc_one="Blow-ups cost 40% less time (a new bike drops in sooner)"),
     _both(_mul("overheat_ticks", 0.6), _mul("explode_ticks", 0.6)))

# --- Air: jumps and landings ------------------------------------------------------------
_reg(Upgrade("gyro", "Gyro Bars", "Air", "Rotate 20% faster in the air (mouse aims land sooner)"),
     _mul("pitch_rate", 1.2))
_reg(Upgrade("soft_shocks", "Soft Shocks", "Air", "Wider safe landing angle (+20%)"),
     _both(_mul("land_tolerance", 1.2), _mul("land_perfect", 1.15)))
_reg(Upgrade("steady_nose", "Steady Nose", "Air", "Nose drops 30% slower mid-air"),
     _mul("nose_drop", 0.7))
_reg(Upgrade("hype_landing", "Hype Landing", "Air", "Perfect landings cool the engine by 3",
             desc_one="Perfect landings add +3 heat (a speed kick, never a blow-up)"),
     _add("perfect_heat", 3.0))
_reg(Upgrade("plush_forks", "Plush Forks", "Air", "Rough landings cost half as much speed",
             max_stacks=2, desc_one="Rough landings dump half as much heat"),
     _mul("rough_loss_mult", 0.5))

# --- Handling: lanes and surfaces -----------------------------------------------------------
_reg(Upgrade("quick_steer", "Quick Steer", "Handling", "Lane changes 40% faster", max_stacks=2),
     _mul("lane_rate", 1.4))
_reg(Upgrade("mud_tires", "Mud Tyres", "Handling", "Mud slows you 30% less", max_stacks=2),
     _mul("mud_speed", 1.3))
_reg(Upgrade("all_terrain", "All-Terrain Kit", "Handling", "+8% grip on grass and sand", max_stacks=2),
     _all_terrain)

# --- Recovery -------------------------------------------------------------------------------
_reg(Upgrade("track_boots", "Track Boots", "Recovery", "Jog back 25% faster after a crash"),
     _mul("crash_ticks", 0.75))
_reg(Upgrade("second_wind", "Second Wind", "Recovery", "One crash forgiven this run", max_stacks=2,
             weight=0.7, desc_one="One crash forgiven this run (not a blow-up)"),
     _add("crash_forgives", 1))
_reg(Upgrade("pre_heater", "Pre-Heater", "Recovery",
             "Restart from a crash or blow-up with the engine warm, right below boost",
             max_stacks=1, modes=ONE),
     _add("respawn_heat", C.ONE_BOOST_AT * 0.9))

# --- Economy ----------------------------------------------------------------------------------
_reg(Upgrade("sponsor", "Sponsor Deal", "Economy", "+15% coins from this run"),
     _mul("currency_mult", 1.15))
_reg(Upgrade("style_points", "Style Points", "Economy", "25% chance of bonus coins per perfect landing"),
     _add("perfect_bonus_chance", 0.25))

CATEGORY_COLORS = {
    "Engine": (255, 120, 60), "Heat": (255, 86, 110), "Air": (190, 140, 255),
    "Handling": (64, 200, 255), "Recovery": (90, 220, 110), "Economy": (255, 196, 0),
}


def apply_upgrades(stats, ids):
    s = stats.copy()
    for uid in ids:
        if uid in EFFECTS:            # ids from older saves that no longer exist are skipped
            EFFECTS[uid](s)
    s.overheat_ticks = int(s.overheat_ticks)
    s.crash_ticks = int(s.crash_ticks)
    s.explode_ticks = int(s.explode_ticks)
    return s


def offer(rng: random.Random, owned, n=3, mode="one"):
    """n distinct upgrades for this throttle mode, excluding ones at their stack cap."""
    pool = [u for u in UPGRADES.values()
            if mode in u.modes and owned.count(u.id) < u.max_stacks]
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
