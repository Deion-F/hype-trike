"""Run state (spec §6.1): heat sequence, targets, upgrades, permadeath, payout.

Decisions: 6 heats (Q6), pick 1 of 3 random upgrades (Q7), crashes only cost
time (Q9). Failing a heat target ends the run. Runs are never saved mid-run.
"""
import random

import config as C
from bike import base_stats
from race import fmt_time
from run.upgrades import apply_upgrades, offer
from track.generator import generate

RUN_HEATS = 6

MODIFIERS = {
    "no_coolant": ("No Coolant", "No coolant pads on this track"),
    "double_heat": ("Hot Engine", "Engine heats twice as fast"),
    "fragile": ("Stiff Forks", "Landing window 30% narrower"),
    "sticky": ("Mud Season", "Mud everywhere: half the lanes are boggy"),
}


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
        self.seed = seed
        self.target = target
        self.rivals = rivals
        self.rival_level = rival_level     # 0..1 rival difficulty (race.rival_setup)
        self.track = None


class RunState:
    def __init__(self, seed=None, vehicle="dirt", livery="flame", start_upgrades=(), themes=None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.vehicle = vehicle
        self.livery = livery
        self.upgrades = list(start_upgrades)
        self.themes = list(themes) if themes else None
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
        last = i == RUN_HEATS - 1
        # Every heat is a race against rivals (solo clock runs live in Time
        # Trial). Heats 3 and 5 add a track modifier on top.
        if last:
            target = Target("place", 1)
        elif i in (2, 4):
            target = Target("place", 2, self.rng.choice(list(MODIFIERS)))
        else:
            target = Target("place", 3 if i < 2 else 2)
        rivals = 3
        # Rivals start beatable and get faster and cleaner every round.
        # TODO (TO_DO.md): try higher-tier upgrades pushing this up faster.
        return Heat(i, seed, target, rivals, rival_level=i / (RUN_HEATS - 1))

    @property
    def heat(self):
        return self.heats[self.heat_i]

    def base_vehicle_stats(self):
        return base_stats(self.vehicle)

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
        g = generate(h.seed, depth=h.index, modifiers=tuple(mods),
                     validate_with=[self.base_vehicle_stats()])
        h.track = g.track
        if self.themes:
            h.track.theme = self.themes[h.index % len(self.themes)]
        if h.target.kind in ("time", "survive"):
            # Par from the ghost's time with the player's current setup.
            from track.validator import validate
            ghost = validate(h.track, st)
            base = ghost["ticks"] if ghost["finished"] else g.validation["ticks"]
            slack = 1.22 - h.index * 0.025
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
            self.pending_offer = offer(self.rng, self.upgrades, 3)
        return met

    def choose(self, upgrade_id):
        self.upgrades.append(upgrade_id)
        self.pending_offer = None
        self.heat_i += 1

    def heats_cleared(self):
        return sum(1 for r in self.results if r["met"])

    def payout(self):
        """Meta-currency for this run (spec §6.3): distance, heats, perfects."""
        mult = apply_upgrades(self.base_vehicle_stats(), self.upgrades).currency_mult
        parts = {
            "distance": int(self.distance_cols / 8),
            "heats": sum(20 + 8 * r["heat"] for r in self.results if r["met"]),
            "perfect": self.perfect + self.bonus_coins,
            "victory": 60 if self.status == "won" else 0,
        }
        total = int(sum(parts.values()) * mult)
        return total, parts, mult
