"""Run state (spec §6.1): biomes, races, targets, upgrades, permadeath, payout.

A run is a tour of the five biomes, easiest to hardest (BIOMES). Each biome is
two normal races and a boss race: win the boss to move on to the next biome,
and pick an elite upgrade (a stronger tier) on the way. Normal races offer 1 of
3 regular upgrades (Q7). Crashes only cost time (Q9). Missing a race's target
ends the run. Runs are never saved mid-run.
"""
import random

import config as C
from bike import base_stats
from race import fmt_time
from meta.bike_tune import apply_tune
from meta.kit import apply_kit
from run.upgrades import apply_upgrades, offer
from track.generator import generate

# Biome order, easiest first. Only the Volcano has its own physics (hot air:
# heat rises faster, cools slower; puddles are lava pits), so it closes the
# run. The others differ in how readable they are (bright Valley and Desert,
# dark Night, busy Stadium) and, through the generator depth below, in which
# structures they get: Valley's normal races have no complex structures (its
# boss brings the first step-ups, fins and overpasses), Night adds the broken
# bridge, drawbridge and twin peaks, Stadium the summit, stair kicker and mesa
# canyon, and the Volcano boss rides the deepest tracks.
BIOMES = ("valley", "desert", "night", "stadium", "lava")
RACES_PER_BIOME = 3                      # two normal races, then the boss
RUN_HEATS = len(BIOMES) * RACES_PER_BIOME

# Rival level (race.rival_setup, 0..1) at each generator depth. A biome's
# normal races ride its own depth, the boss rides the next one up.
DEPTH_RIVAL_LEVELS = [0.0, 0.15, 0.32, 0.68, 0.92, 1.0]
# How far the second normal race sits between the biome's level and the boss's.
SECOND_RACE_STEP = 0.3


def biome_of(i):
    return i // RACES_PER_BIOME


def is_boss(i):
    return i % RACES_PER_BIOME == RACES_PER_BIOME - 1


def depth_for(i):
    """Generator depth (structures, length, ground materials) for race i."""
    return biome_of(i) + (1 if is_boss(i) else 0)


def _rival_level(i):
    b, k = biome_of(i), i % RACES_PER_BIOME
    lo, hi = DEPTH_RIVAL_LEVELS[b], DEPTH_RIVAL_LEVELS[b + 1]
    return (lo, lo + (hi - lo) * SECOND_RACE_STEP, hi)[k]


RIVAL_LEVELS = [_rival_level(i) for i in range(RUN_HEATS)]

MODIFIERS = {
    "no_coolant": ("No Coolant", "No coolant pads on this track"),
    "double_heat": ("Hot Engine", "Engine heats twice as fast"),
    "fragile": ("Stiff Forks", "Landing window 30% narrower"),
    "sticky": ("Mud Season", "Mud everywhere: half the lanes are boggy"),
}

# Races (0-based) that carry a modifier, earliest first: the second normal
# race of Night and of Stadium (bosses are hard enough already).
MODIFIER_HEATS = (7, 10)

# How hard each modifier makes a heat, 0 (barely matters) .. 1 (the hardest).
# Measured, not guessed: the difficulty tuner sets these from
# `tools/tuning.py mods` (recordings) and `tools/tuning.py modsim` (AI players
# racing the same heats with each modifier forced). See docs/tuning_log.md.
# 2026-11-13 (modsim 12 seeds, one-button): Mud Season clearly hardest; Stiff
# Forks neutral; Hot Engine and No Coolant slightly *help* AI pilots (heat is
# speed in one-button). Hot Engine nudged up from 0.27: the 2 recorded human
# heats with it averaged a blow-up per race.
MODIFIER_HARDNESS = {
    "no_coolant": 0.1,
    "double_heat": 0.35,
    "fragile": 0.5,
    "sticky": 0.9,
}
# How strongly later modifier heats prefer the harder modifiers (and earlier
# ones the easier). 0 = uniform pick; 0.8 gives weights between 0.2 and 1.8.
MODIFIER_SKEW = 0.8


def modifier_weights(i):
    """{modifier: pick weight} for heat i. The first modifier heat leans to the
    easier modifiers, the last to the harder ones."""
    slots = MODIFIER_HEATS
    p = slots.index(i) / max(1, len(slots) - 1) if i in slots else 0.5
    return {m: max(0.05, 1.0 + MODIFIER_SKEW * (2 * p - 1) * (2 * MODIFIER_HARDNESS.get(m, 0.5) - 1))
            for m in MODIFIERS}


def pick_modifier(rng, i):
    w = modifier_weights(i)
    r = rng.random() * sum(w.values())
    for m, x in w.items():
        r -= x
        if r <= 0:
            return m
    return m


class Target:
    def __init__(self, kind, value=None, modifier=None):
        self.kind = kind          # "time" | "place" | "survive"
        self.value = value        # ticks for time/survive, place for place
        self.modifier = modifier

    def describe(self):
        if self.kind == "time":
            return f"TARGET: finish under {fmt_time(self.value)}"
        if self.kind == "place":
            goal = "win the race" if self.value == 1 else f"finish top {self.value}"
            if self.modifier:
                return f"{MODIFIERS[self.modifier][0].upper()}: {goal}"
            return f"TARGET: {goal}"
        name = MODIFIERS[self.modifier][0]
        return f"SURVIVE ({name}): under {fmt_time(self.value)}"

    def check(self, result):
        if not result or not result.get("finished"):
            return False
        if self.kind == "place":
            return result["position"] <= self.value
        return result["time"] <= self.value

    def to_dict(self):
        return {"kind": self.kind, "value": self.value, "modifier": self.modifier}


class Heat:
    def __init__(self, index, seed, target, rivals, rival_level):
        self.index = index
        self.biome = BIOMES[biome_of(index)]
        self.boss = is_boss(index)
        self.depth = depth_for(index)
        self.seed = seed
        self.target = target
        self.rivals = rivals
        self.rival_level = rival_level     # 0..1 rival difficulty (race.rival_setup)
        self.track = None


class RunState:
    def __init__(self, seed=None, vehicle="dirt", livery="flame", start_upgrades=(), mode="one",
                 kit_levels=None, bike_levels=None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.vehicle = vehicle
        self.livery = livery
        self.mode = mode               # throttle mode the run was started in ("one" | "classic")
        self.upgrades = list(start_upgrades)
        self.kit_levels = dict(kit_levels or {})   # Starter Kit (meta/kit.py), every heat
        # bike tuning for this vehicle (meta/bike_tune.py); None = full stats (sims, tests)
        self.bike_levels = dict(bike_levels) if bike_levels is not None else None
        self.heat_i = 0
        self.status = "active"         # active | won | lost
        self.results = []
        self.perfect = 0
        self.distance_cols = 0.0
        self.bonus_coins = 0
        self.forgives_used = 0
        self.pending_offer = None
        self.heats = [self._plan_heat(i) for i in range(RUN_HEATS)]

    # -- planning -----------------------------------------------------------------
    def _plan_heat(self, i):
        seed = (self.seed * 31 + i * 7_919) & 0x3FFFFFFF
        # Every race is against rivals (solo clock runs live in Time Trial).
        # Bosses must be won; the early biomes only ask for a podium.
        if is_boss(i):
            target = Target("place", 1)
        elif i in MODIFIER_HEATS:
            target = Target("place", 2, pick_modifier(self.rng, i))
        else:
            target = Target("place", 3 if biome_of(i) < 2 else 2)
        return Heat(i, seed, target, rivals=3, rival_level=RIVAL_LEVELS[i])

    @property
    def heat(self):
        return self.heats[self.heat_i]

    def base_vehicle_stats(self):
        """The vehicle at its tuning levels with the Starter Kit fitted (before run upgrades)."""
        return apply_kit(apply_tune(base_stats(self.vehicle), self.bike_levels), self.kit_levels)

    def stats_for_heat(self, heat=None):
        heat = heat or self.heat
        s = apply_upgrades(self.base_vehicle_stats(), self.upgrades)
        s.crash_forgives = max(0, s.crash_forgives - self.forgives_used)
        mod = heat.target.modifier
        if mod == "double_heat":
            s.heat_a *= 2
            s.heat_b *= 2
        elif mod == "fragile":
            s.land_tolerance *= 0.7
            s.land_perfect *= 0.7
        return s

    def prepare_heat(self):
        """Generate + validate this heat's track and fill in time targets."""
        h = self.heat
        if h.track is not None:
            return h
        mods = []
        if h.target.modifier in ("no_coolant", "sticky"):
            mods.append(h.target.modifier)
        st = self.stats_for_heat(h)
        g = generate(h.seed, depth=h.depth, modifiers=tuple(mods),
                     validate_with=[self.base_vehicle_stats()])
        h.track = g.track
        h.track.theme = h.biome
        if h.boss:
            h.track.name = "Boss: " + h.track.name
        if h.target.kind in ("time", "survive"):
            # Par from the ghost's time with the player's current setup.
            from track.validator import validate
            ghost = validate(h.track, st)
            base = ghost["ticks"] if ghost["finished"] else g.validation["ticks"]
            slack = 1.22 - h.depth * 0.025
            if h.target.kind == "survive":
                slack += 0.25
            h.target.value = int(base * slack)
        return h

    # -- results -------------------------------------------------------------------
    def record(self, result, stats_used):
        h = self.heat
        met = h.target.check(result)
        self.results.append({"heat": h.index, "met": met, **(result or {})})
        if result:
            self.perfect += result.get("perfect", 0)
            self.distance_cols += result.get("distance", 0) / C.TILE_W
            if stats_used.perfect_bonus_chance > 0:
                r = random.Random(self.seed + h.index)
                for _ in range(result.get("perfect", 0)):
                    if r.random() < stats_used.perfect_bonus_chance:
                        self.bonus_coins += 3
            self.forgives_used += result.get("forgiven", 0)
        if not met:
            self.status = "lost"
        elif self.heat_i == RUN_HEATS - 1:
            self.status = "won"
        else:
            self.pending_offer = self.offer_after(h.index)
        return met

    def offer_after(self, i):
        """The upgrade pick after clearing race i: elite after a boss."""
        tier = "elite" if is_boss(i) else "normal"
        return offer(self.rng, self.upgrades, 3, self.mode, tier=tier)

    @property
    def biome_i(self):
        return biome_of(self.heat_i)

    def biomes_cleared(self):
        return sum(1 for r in self.results if r["met"] and is_boss(r["heat"]))

    def choose(self, upgrade_id):
        self.upgrades.append(upgrade_id)
        self.pending_offer = None
        self.heat_i += 1

    def heats_cleared(self):
        return sum(1 for r in self.results if r["met"])

    def payout(self):
        """Meta-currency for this run (spec §6.3): distance, heats, perfects."""
        s = apply_upgrades(self.base_vehicle_stats(), self.upgrades)
        mult = s.currency_mult
        won = [r for r in self.results if r["met"] and r.get("position") == 1]
        prizes = s.prize_coins * len(won) + s.boss_bounty * sum(1 for r in won if is_boss(r["heat"]))
        parts = {
            "distance": int(self.distance_cols / 8),
            "heats": sum(race_coins(r["heat"]) for r in self.results if r["met"]) + prizes,
            "perfect": self.perfect + self.bonus_coins,
            "victory": 100 if self.status == "won" else 0,
        }
        total = int(sum(parts.values()) * mult)
        return total, parts, mult


def race_coins(i):
    """Coins for clearing race i: bosses pay most, later biomes more."""
    b = biome_of(i)
    return 20 + 8 * b if is_boss(i) else 6 + 3 * b
