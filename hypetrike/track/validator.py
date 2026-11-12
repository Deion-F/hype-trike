"""Ghost-rider AI and solvability check (spec §5.3 step 4, §7.1).

GhostAI drives a Bike with the same physics as the player. The validator runs
it with the *base* dirt bike on throttle A only (no turbo), so a track that
passes is clearable by a new player without upgrades.
"""
import math
import random

import config as C
from bike import Bike, Controls, base_stats
from track.tiles import MUD, DEBRIS, GAP, WATER, PADS


class GhostAI:
    def __init__(self, turbo=False, turbo_temp=24.0, skill=1.0, seed=0, blunder=0.0, miss=0.0):
        """skill: landing aim precision. blunder: chance a jump's aim is badly off
        (rough landing or crash). miss: chance of not dodging a hazard ahead.
        The validator ghost uses the defaults (perfect, never blunders)."""
        self.turbo = turbo
        self.turbo_temp = turbo_temp
        self.skill = skill
        self.blunder = blunder
        self.miss = miss
        self.rng = random.Random(seed)
        self._blind_until = -1.0        # x until which a missed hazard is ignored
        self._jump_error = 0.0
        self._was_air = False
        self._lane_cooldown = 0

    # ------------------------------------------------------------------------
    def controls(self, bike: Bike) -> Controls:
        c = Controls(a=True)
        if bike.state != "ride":
            return c
        if bike.airborne:
            if not self._was_air:
                # New jump: pick this jump's aiming error from skill.
                spread = (1.0 - self.skill) * 22.0
                self._jump_error = self.rng.uniform(-spread, spread * 0.6)
                if self.rng.random() < self.blunder:
                    # botched jump: way off, nose-down (crash) or nose-high (rough/loop)
                    self._jump_error = self.rng.choice((-1, 1)) * self.rng.uniform(16, 34)
            self._was_air = True
            self._steer_air(bike, c)
            return c
        self._was_air = False
        if self.turbo and bike.temp < self.turbo_temp and bike.wobble == 0:
            c.b = True
        self._avoid(bike, c)
        return c

    def _steer_air(self, bike, c):
        t, land_x = predict_landing(bike)
        if bike.track.terrain_at(land_x) == GAP:
            base = 0.0            # heading for a pit: level out and hope
        else:
            base = math.degrees(math.atan(bike.track.slope(land_x)))
        target = max(-35.0, min(35.0, base)) + self._jump_error
        desired_now = target + bike.stats.nose_drop * t
        err = bike.angle - desired_now
        band = max(1.0, bike.stats.pitch_rate * 0.6)
        if err > band:
            c.right = True
        elif err < -band:
            c.left = True

    def _avoid(self, bike, c):
        if self._lane_cooldown > 0:
            self._lane_cooldown -= 1
            return
        if bike.lane != bike.lane_index or abs(bike.lane_pos - bike.lane) > 0.01:
            return
        tr = bike.track
        look = [bike.x + i * C.TILE_W * 0.5 for i in range(0, 5)]

        def lane_cost(lane):
            cost = 0.0
            for i, x in enumerate(look):
                s = tr.surface[lane][tr.col_at(x)]
                if s == DEBRIS:
                    cost += 100 - i * 5
                elif s == MUD:
                    cost += 10
                elif s == WATER:
                    cost += 8          # a puddle costs speed; a lava pit, a lot of heat
                elif s in PADS and self.turbo:
                    cost -= 3
            return cost + abs(lane - bike.lane) * 0.5

        here = lane_cost(bike.lane)
        if here <= 0.5:
            return
        if bike.x < self._blind_until:
            return                      # didn't see this one coming
        if self.miss and self.rng.random() < self.miss:
            self._blind_until = bike.x + 3 * C.TILE_W
            return
        best = min(range(C.LANES), key=lane_cost)
        if lane_cost(best) < here:
            if best < bike.lane:
                c.lane_up = True
            elif best > bike.lane:
                c.lane_down = True
            self._lane_cooldown = 4


def predict_landing(bike, max_ticks=240):
    """Ticks until touchdown and the landing x, assuming no input."""
    x, h, vy = bike.x, bike.h, bike.vy
    vx = bike.vx
    tr = bike.track
    for t in range(1, max_ticks):
        x += vx
        vy -= C.GRAVITY
        h += vy
        if h <= tr.ground(x):
            return t, x
    return max_ticks, x


def validate(track, stats=None, laps=None, seed=0, max_seconds=None):
    """Run the ghost rider. Returns a dict with ok / time / crashes / reason."""
    from race import Race
    stats = stats or base_stats("dirt")
    tr = track.copy()
    if laps is not None:
        tr.laps = laps
    race = Race(tr, stats, rivals=0, countdown=False)
    ai = GhostAI(turbo=False, skill=1.0, seed=seed)
    limit = int((max_seconds or (tr.length * tr.laps / 3.0 / C.FPS + 30)) * C.FPS)
    crash_reasons = []
    for _ in range(limit):
        ev = race.step(ai.controls(race.bike))
        for e in ev:
            if e[0] == "crash":
                crash_reasons.append((e[1], race.track.col_at(race.bike.x)))
        if race.finished:
            break
    return {
        "ok": race.finished and not crash_reasons,
        "finished": race.finished,
        "ticks": race.time_ticks,
        "crashes": crash_reasons,
        "perfect": race.bike.stats_counters["perfect"],
    }
