"""Upgrade pool and stacking (spec §6.2). Effects stack multiplicatively where
that makes sense; each upgrade has a stack cap. None of them repeats a Starter
Kit item (meta/kit.py): the kit is small permanent stat steps, the run pool is
mechanics.

Built around the two throttle modes (setting "throttle_mode"):
  "one"     (default) heat IS the throttle: warm up, ride the boost band, dip
            into overheating for extra speed, never reach the top (it blows up).
  "classic" A = throttle, B = turbo that builds heat toward an overheat stall.
Each upgrade lists the modes it is offered in; a few read differently per mode
(name_one / desc_one) because the same stat plays a different role there."""
import random
from dataclasses import dataclass

import config as C

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
    tier: str = "normal"          # "normal" (after a race) | "elite" (after a boss win)

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
_reg(Upgrade("supercharger", "Supercharger", "Engine", "More top speed while overheating: +1 at its edge, up to +4 near the top",
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
_reg(Upgrade("adrenaline", "Adrenaline", "Heat",
             "Perfect landings slow heating by 60% for 2 s while overheating: chain them to stay hot",
             max_stacks=1),
     _add("adrenaline_ticks", 2 * C.FPS))
_reg(Upgrade("blow_off", "Blow-Off Valve", "Heat",
             "Once per race, an overheat vents the engine instead of stalling",
             max_stacks=2, weight=0.8,
             desc_one="Once per race, a blow-up vents the engine back to boost instead"),
     _add("vent_charges", 1))
_reg(Upgrade("cryo_pads", "Cryo Pads", "Heat", "Coolant pads also freeze heat for 1.5 s",
             name_one="Pad Lock", desc_one="Heat pads lock your heat for 1.5 s: surf the boost"),
     _add("coolant_chill", 90))
_reg(Upgrade("slipstream", "Slipstream", "Engine",
             "+5% top speed while a rival is less than two sections ahead in your lane",
             max_stacks=2),
     _add("draft_bonus", 0.05))

# --- Air: jumps and landings ------------------------------------------------------------
_reg(Upgrade("hang_time", "Hang Time", "Air",
             "Clean landings turn airtime into speed: +2 per second in the air, past your top speed",
             max_stacks=2),
     _add("hang_kick", 2.0))
_reg(Upgrade("crumple_zone", "Crumple Zone", "Air",
             "Once per race, a landing that would crash you is only a rough landing", max_stacks=2,
             weight=0.8),
     _add("land_saves", 1))
_reg(Upgrade("steady_nose", "Steady Nose", "Air", "Nose drops 30% slower mid-air"),
     _mul("nose_drop", 0.7))
_reg(Upgrade("hype_landing", "Hype Landing", "Air", "Perfect landings cool the engine by 3",
             desc_one="Perfect landings add +3 heat (a speed kick, never a blow-up)"),
     _add("perfect_heat", 3.0))
_reg(Upgrade("plush_forks", "Plush Forks", "Air", "Rough landings cost half as much speed",
             max_stacks=2, desc_one="Rough landings dump half as much heat"),
     _mul("rough_loss_mult", 0.5))

# --- Handling: lanes and surfaces -----------------------------------------------------------
_reg(Upgrade("barrier_buster", "Barrier Buster", "Handling",
             "Once per race, smash straight through a barrier instead of crashing", max_stacks=2),
     _add("barrier_saves", 1))
_reg(Upgrade("mud_tires", "Mud Tyres", "Handling", "Mud slows you 30% less", max_stacks=2),
     _mul("mud_speed", 1.3))
_reg(Upgrade("line_choice", "Line Choice", "Handling",
             "Each lane change you finish kicks +1 speed past your top speed (once a second)",
             max_stacks=2),
     _add("lane_kick", 1.0))

# --- Recovery -------------------------------------------------------------------------------
_reg(Upgrade("comeback", "Comeback", "Recovery",
             "After a crash or blow-up, accelerate twice as fast for 3 s", max_stacks=1,
             desc_one="After a crash or blow-up, the cold engine heats twice as fast for 3 s"),
     _add("comeback_ticks", 3 * C.FPS))
_reg(Upgrade("second_wind", "Second Wind", "Recovery", "One crash forgiven this run", max_stacks=2,
             weight=0.7, desc_one="One crash forgiven this run (not a blow-up)"),
     _add("crash_forgives", 1))
_reg(Upgrade("pre_heater", "Pre-Heater", "Recovery",
             "Restart from a crash or blow-up with the engine warm, right below boost",
             max_stacks=1, modes=ONE),
     _add("respawn_heat", C.ONE_BOOST_AT * 0.9))

# --- Economy ----------------------------------------------------------------------------------
_reg(Upgrade("prize_money", "Prize Money", "Economy", "+15 coins for every race you win this run"),
     _add("prize_coins", 15))
_reg(Upgrade("style_points", "Style Points", "Economy", "25% chance of bonus coins per perfect landing"),
     _add("perfect_bonus_chance", 0.25))

# --- Elite: offered only after winning a biome's boss race ---------------------------------
# Each one is roughly two regular upgrades in one, and they stack with them.
ELITE = "elite"
_reg(Upgrade("works_engine", "Works Engine", "Engine", "+9% top speed in every heat band",
             max_stacks=2, tier=ELITE),
     _both(_mul("max_speed_a", 1.09), _mul("max_speed_b", 1.09)))
_reg(Upgrade("launch_control", "Launch Control", "Engine",
             "Accelerate 30% faster and +4% top speed", max_stacks=1, tier=ELITE,
             desc_one="Speed catches up to your heat 30% faster, and +4% top speed"),
     _both(_mul("accel_interval", 0.7), _mul("max_speed_a", 1.04), _mul("max_speed_b", 1.04)))
_reg(Upgrade("nitrous", "Nitrous Kit", "Engine", "Much more top speed while overheating: +2.5 at its edge, up to +10 near the top",
             max_stacks=1, modes=ONE, tier=ELITE),
     _add("super_extra", 5))
_reg(Upgrade("ceramic", "Ceramic Coating", "Heat", "Turbo builds 40% less heat", max_stacks=1, tier=ELITE,
             name_one="Ceramic Pistons", desc_one="Heat climbs 40% slower once boosting: much longer boosts"),
     _mul("heat_b", 0.6))
_reg(Upgrade("twin_radiators", "Twin Radiators", "Heat",
             "Twice per race, an overheat vents the engine instead of stalling",
             max_stacks=1, tier=ELITE,
             desc_one="Twice per race, a blow-up vents the engine back to boost instead"),
     _add("vent_charges", 2))
_reg(Upgrade("pro_suspension", "Pro Suspension", "Air",
             "Rough landings cost nothing, and twice per race a crash landing is only rough",
             max_stacks=1, tier=ELITE),
     _both(_mul("rough_loss_mult", 0.0), _add("land_saves", 2)))
_reg(Upgrade("flight_computer", "Flight Computer", "Air",
             "Nose drops 70% slower in the air, and clean landings turn airtime into speed (+3/s)",
             max_stacks=1, tier=ELITE),
     _both(_mul("nose_drop", 0.3), _add("hang_kick", 3.0)))
_reg(Upgrade("paddle_tyres", "Paddle Tyres", "Handling",
             "Mud slows you 60% less, smash one barrier per race, and lane changes kick +1 speed",
             max_stacks=1, tier=ELITE),
     _both(_mul("mud_speed", 1.6), _add("barrier_saves", 1), _add("lane_kick", 1.0)))
_reg(Upgrade("factory_rider", "Factory Rider", "Recovery",
             "Two more crashes forgiven this run, and accelerate twice as fast for 3 s after any crash",
             max_stacks=1, tier=ELITE,
             desc_one="Two more crashes forgiven (not blow-ups), and warm up twice as fast for 3 s after any crash"),
     _both(_add("crash_forgives", 2), _add("comeback_ticks", 3 * C.FPS)))
_reg(Upgrade("bounty_hunter", "Bounty Hunter", "Economy",
             "+60 coins for every boss you beat this run, this one included", max_stacks=1, weight=0.6,
             tier=ELITE),
     _add("boss_bounty", 60))

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


def offer(rng: random.Random, owned, n=3, mode="one", tier="normal"):
    """n distinct upgrades of this tier for this throttle mode, excluding ones at
    their stack cap. Elite upgrades are only offered after a boss win."""
    pool = [u for u in UPGRADES.values()
            if mode in u.modes and owned.count(u.id) < u.max_stacks and u.tier == tier]
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
