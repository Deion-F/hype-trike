"""Starter Kit: permanent meta-progression for runs.

Every kit item starts at level 0 and is bought up one small step at a time,
each level dearer than the last, to MAX_LEVEL. All owned levels apply to every
run (nothing to equip). The top level matches what the old one-off starting
upgrade gave. No kit item repeats a run upgrade (run/upgrades.py): the kit is
plain stat steps, the run pool is mechanics.
"""
from dataclasses import dataclass

from track.tiles import GRASS, SAND

MAX_LEVEL = 5
# Price of each level as a multiple of the item's base price: 1st .. 5th level.
COST_CURVE = (1.0, 2.0, 3.5, 5.5, 8.0)


@dataclass(frozen=True)
class KitItem:
    id: str
    name: str
    category: str
    per_level: float          # effect per level (a fraction, e.g. 0.04 = 4%)
    text: str                 # "{v}" is replaced by the effect at a level, in %
    base_price: int

    def price(self, level):
        """Coins for the next level after `level` (None when maxed)."""
        if level >= MAX_LEVEL:
            return None
        return int(round(self.base_price * COST_CURVE[level] / 5.0)) * 5

    def describe(self, level):
        return self.text.format(v=round(self.per_level * level * 100))


def _apply(item_id, s, level):
    k = KIT[item_id].per_level * level
    if item_id == "gyro":
        s.pitch_rate *= 1 + k
    elif item_id == "soft_shocks":
        s.land_tolerance *= 1 + k
        s.land_perfect *= 1 + k * 0.75
    elif item_id == "cool_head":
        s.red_heat_mult *= 1 - k
    elif item_id == "track_boots":
        s.crash_ticks = int(s.crash_ticks * (1 - k))
    elif item_id == "radiator":
        s.overheat_ticks = int(s.overheat_ticks * (1 - k))
        s.explode_ticks = int(s.explode_ticks * (1 - k))
    elif item_id == "quick_steer":
        s.lane_rate *= 1 + k
    elif item_id == "all_terrain":
        for m in (GRASS, SAND):
            s.grip[m] = min(1.0, s.grip[m] * (1 + k))
    elif item_id == "sponsor":
        s.currency_mult *= 1 + k


KIT = {it.id: it for it in (
    KitItem("gyro", "Gyro Bars", "Air", 0.04, "+{v}% rotation speed in the air", 40),
    KitItem("soft_shocks", "Soft Shocks", "Air", 0.04, "+{v}% safe landing angle", 50),
    KitItem("cool_head", "Cool Head", "Heat", 0.07, "Heat climbs {v}% slower in the red", 40),
    KitItem("radiator", "Radiator", "Heat", 0.06, "Blow-ups and overheat stalls {v}% shorter", 35),
    KitItem("track_boots", "Track Boots", "Recovery", 0.05, "Jog back {v}% faster after a crash", 30),
    KitItem("quick_steer", "Quick Steer", "Handling", 0.08, "Lane changes {v}% faster", 40),
    KitItem("all_terrain", "All-Terrain Kit", "Handling", 0.016, "+{v}% grip on grass and sand", 45),
    KitItem("sponsor", "Sponsor Deal", "Economy", 0.03, "+{v}% coins from every run", 55),
)}


def apply_kit(stats, levels):
    """A copy of `stats` with the Starter Kit levels {item_id: level} applied."""
    s = stats.copy()
    for item_id, level in (levels or {}).items():
        if item_id in KIT and level > 0:
            _apply(item_id, s, min(MAX_LEVEL, int(level)))
    return s
