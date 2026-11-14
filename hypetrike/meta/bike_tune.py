"""Bike tuning: every vehicle's own stats, levelled like the Starter Kit.

A bike starts below its full stats (level 0, still rideable) and each tunable
stat is bought up one level at a time, each level dearer, to MAX_LEVEL where it
reaches the vehicle's full value (bike.VEHICLES). Levels are kept per vehicle,
so tuning the dirt bike does nothing for the sprinter. Grip is the vehicle's
identity and isn't tunable. Rivals always ride full-stat bikes.
"""
from dataclasses import dataclass

from meta.kit import COST_CURVE, MAX_LEVEL


@dataclass(frozen=True)
class TuneStat:
    id: str
    name: str
    fields: tuple          # BikeStats fields it scales
    start: float           # multiplier at level 0 (full value = 1.0 at MAX_LEVEL)
    text: str              # what a level does, "{v}" = % of the full value
    base_price: int

    def mult(self, level):
        level = max(0, min(MAX_LEVEL, int(level)))
        return self.start + (1.0 - self.start) * level / MAX_LEVEL

    def describe(self, level):
        m = self.mult(level)
        if self.start > 1.0:      # lower is better (intervals, heat rates): show how much worse
            return self.text.format(v=round((m - 1.0) * 100))
        return self.text.format(v=round(m * 100))


TUNE = {t.id: t for t in (
    TuneStat("top_speed", "Top Speed", ("max_speed_a", "max_speed_b"), 0.92,
             "{v}% of full top speed", 35),
    TuneStat("accel", "Acceleration", ("accel_interval",), 1.30,
             "{v}% slower to pick up speed than full", 30),
    TuneStat("cooling", "Engine Heat", ("heat_a", "heat_b"), 1.25,
             "Heats {v}% faster than full", 30),
    TuneStat("air", "Air Control", ("pitch_rate",), 0.80, "{v}% of full air rotation", 25),
    TuneStat("landing", "Landing", ("land_tolerance", "land_perfect"), 0.80,
             "{v}% of the full safe landing angle", 25),
)}

# Dearer bikes cost more to tune.
VEHICLE_TIER = {"dirt": 1.0, "trike": 1.15, "scrambler": 1.3, "sprinter": 1.5}


def price(vehicle, stat_id, level):
    """Coins for the next level after `level` (None when maxed)."""
    if level >= MAX_LEVEL:
        return None
    base = TUNE[stat_id].base_price * VEHICLE_TIER.get(vehicle, 1.0)
    return int(round(base * COST_CURVE[level] / 5.0)) * 5


def apply_tune(stats, levels):
    """A copy of a vehicle's full stats at the given tuning levels {stat: level}
    (missing stats are level 0). levels None = full stats (rivals, tests, sims)."""
    if levels is None:
        return stats.copy()
    s = stats.copy()
    for t in TUNE.values():
        m = t.mult(levels.get(t.id, 0))
        for f in t.fields:
            setattr(s, f, getattr(s, f) * m)
    return s
