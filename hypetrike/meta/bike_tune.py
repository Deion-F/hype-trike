"""Bike upgrades: each vehicle's own levels, paid for with that bike's XP.

Every race a bike rides in a run earns that bike XP (deeper races earn more,
see xp_for_race), and the XP is spent on that bike's upgrades, one level at a
time, each level dearer, up to MAX_LEVEL. Levels and XP are kept per vehicle,
so upgrading the dirt bike does nothing for the sprinter. Coins never buy
power: they only unlock cosmetics (meta/shop.py).

A fresh bike sits a little below its catalogue stats (bike.VEHICLES) on the
first five upgrades and reaches them about half way; level 5 goes past them.
Each upgrade moves exactly one stat bar in the garage (STAT_ROWS), so a level
bought reads straight off the bars. Rivals ride catalogue bikes plus their own
Starter Kit spread (race.rival_kit), unaffected by any of this.
"""
from dataclasses import dataclass

from track.tiles import GRASS, SAND

MAX_LEVEL = 5
# Price of each level as a multiple of the upgrade's base price: 1st .. 5th level.
COST_CURVE = (1.0, 2.0, 3.5, 5.5, 8.0)


@dataclass(frozen=True)
class BikeUpgrade:
    id: str
    name: str
    stat: str              # the stat bar it raises (STAT_ROWS label)
    effects: tuple         # (BikeStats field, multiplier at level 0, multiplier at MAX_LEVEL)
    text: str              # what it does at a level; "{v}" = signed % vs the catalogue bike
    base_price: int        # XP for the first level

    def mult(self, start, end, level):
        level = max(0, min(MAX_LEVEL, int(level)))
        return start + (end - start) * level / MAX_LEVEL

    def describe(self, level):
        """'Top speed +4%': the first effect's change vs the catalogue bike."""
        f, a, b = self.effects[0]
        pct = round((self.mult(a, b, level) - 1.0) * 100)
        return self.text.format(v=f"{pct:+d}")


UPGRADES = {u.id: u for u in (
    BikeUpgrade("top_speed", "Engine", "Top speed",
                (("max_speed_a", 0.92, 1.04), ("max_speed_b", 0.92, 1.04)),
                "Top speed {v}%", 30),
    BikeUpgrade("accel", "Gearing", "Acceleration", (("accel_interval", 1.25, 0.88),),
                "Time to pick up speed {v}%", 25),
    BikeUpgrade("cooling", "Cooling", "Cooling", (("heat_a", 1.20, 0.9), ("heat_b", 1.20, 0.9)),
                "Heat build-up {v}%", 25),
    BikeUpgrade("radiator", "Radiator", "Heat tolerance",
                (("red_heat_mult", 1.0, 0.72), ("overheat_ticks", 1.0, 0.7), ("explode_ticks", 1.0, 0.7)),
                "Heat climb when hot {v}%, shorter blow-ups", 30),
    BikeUpgrade("air", "Gyro Bars", "Air control", (("pitch_rate", 0.85, 1.2),),
                "Air rotation {v}%", 25),
    BikeUpgrade("landing", "Soft Shocks", "Landing",
                (("land_tolerance", 0.85, 1.2), ("land_perfect", 0.85, 1.15)),
                "Safe landing angle {v}%", 30),
    BikeUpgrade("steering", "Quick Steer", "Steering", (("lane_rate", 1.0, 1.4),),
                "Lane change speed {v}%", 20),
    BikeUpgrade("grip", "Knobby Tyres", "Off-road grip", (("offroad_grip", 1.0, 1.08),),
                "Grass and sand grip {v}%", 25),
    BikeUpgrade("recovery", "Track Boots", "Recovery", (("crash_ticks", 1.0, 0.75),),
                "Crash recovery time {v}%", 20),
)}
# Old name, still used by the garage and tests.
TUNE = UPGRADES

# Dearer bikes cost more XP to upgrade.
VEHICLE_TIER = {"dirt": 1.0, "trike": 1.15, "scrambler": 1.3, "sprinter": 1.5}

INT_FIELDS = ("overheat_ticks", "explode_ticks", "crash_ticks")


def price(vehicle, up_id, level):
    """XP for the next level after `level` (None when maxed)."""
    if level >= MAX_LEVEL:
        return None
    base = UPGRADES[up_id].base_price * VEHICLE_TIER.get(vehicle, 1.0)
    return int(round(base * COST_CURVE[level] / 5.0)) * 5


def apply_tune(stats, levels):
    """A copy of a vehicle's catalogue stats at the given upgrade levels {id: level}
    (missing ids are level 0). levels None = catalogue stats (rivals, tests, sims)."""
    s = stats.copy()
    if levels is None:
        return s
    for u in UPGRADES.values():
        lv = levels.get(u.id, 0)
        for f, a, b in u.effects:
            m = u.mult(a, b, lv)
            if f == "offroad_grip":
                for mat in (GRASS, SAND):
                    s.grip[mat] = min(1.0, s.grip[mat] * m)
            else:
                v = getattr(s, f) * m
                setattr(s, f, int(v) if f in INT_FIELDS else v)
    return s


# -- XP ----------------------------------------------------------------------------
XP_BASE = 20               # XP for a race at depth 0 ...
XP_PER_DEPTH = 15          # ... plus this per generator depth (deeper races pay more)
XP_BOSS_MULT = 1.5         # boss races
XP_MISSED_MULT = 0.5       # a race whose target you missed still teaches the bike something


def xp_for_race(depth, boss=False, met=True, finished=True):
    """XP a bike earns for one run race."""
    if not finished:
        return 0
    xp = (XP_BASE + XP_PER_DEPTH * depth) * (XP_BOSS_MULT if boss else 1.0)
    return int(round(xp * (1.0 if met else XP_MISSED_MULT)))


# -- stat bars ----------------------------------------------------------------------
def _grip(s):
    return (s.grip[GRASS] + s.grip[SAND]) / 2


# (upgrade id, label, 0..1 bar fill from the stats). Ranges cover every vehicle from
# level 0 to level 5, so each level moves its bar a visible step.
STAT_ROWS = (
    ("top_speed", "Top speed", lambda s: (s.max_speed_b - 38) / 18),
    ("accel", "Accel", lambda s: (1 / s.accel_interval - 0.12) / 0.2),
    ("cooling", "Cooling", lambda s: (0.13 - s.heat_b) / 0.085),
    ("radiator", "Heat tolerance", lambda s: (1.1 - s.red_heat_mult) / 0.45),
    ("air", "Air control", lambda s: (s.pitch_rate - 1.0) / 2.4),
    ("landing", "Landing", lambda s: (s.land_tolerance - 6) / 20),
    ("steering", "Steering", lambda s: (s.lane_rate - 0.08) / 0.11),
    ("grip", "Off-road grip", lambda s: (_grip(s) - 0.55) / 0.5),
    ("recovery", "Recovery", lambda s: (190 - s.crash_ticks) / 110),
)


def stat_bars(stats):
    """[(upgrade id, label, fill 0..1)] for the garage's stat bars."""
    return [(uid, label, max(0.0, min(1.0, f(stats)))) for uid, label, f in STAT_ROWS]


def migrate_levels(tune, kit):
    """Old saves: per-bike tuning (5 levels from 'start' to the catalogue stat) and the
    global Starter Kit -> the new per-bike levels, matched on the stat they produced."""
    old_start = {"top_speed": 0.92, "accel": 1.30, "cooling": 1.25, "air": 0.80, "landing": 0.80}
    kit_k = {"air": ("gyro", 0.04), "landing": ("soft_shocks", 0.04)}
    out = {}
    for uid, u in UPGRADES.items():
        f, a, b = u.effects[0]
        if uid in old_start:
            st = old_start[uid]
            m = st + (1.0 - st) * min(MAX_LEVEL, tune.get(uid, 0)) / MAX_LEVEL
        else:
            m = a
        if uid in kit_k:
            item, per = kit_k[uid]
            m *= 1 + per * min(MAX_LEVEL, kit.get(item, 0))
        elif uid in ("radiator", "steering", "grip", "recovery"):
            item = {"radiator": "cool_head", "steering": "quick_steer", "grip": "all_terrain",
                    "recovery": "track_boots"}[uid]
            lv = min(MAX_LEVEL, kit.get(item, 0))
            if uid == "radiator":
                lv = max(lv, min(MAX_LEVEL, kit.get("radiator", 0)))
            m = a + (b - a) * lv / MAX_LEVEL
        level = round((m - a) / (b - a) * MAX_LEVEL) if b != a else 0
        level = max(0, min(MAX_LEVEL, level))
        if level:
            out[uid] = level
    return out
