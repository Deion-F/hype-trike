"""Ghost-rider AI and solvability check (spec §5.3 step 4, §7.1).

GhostAI drives a Bike with the same physics as the player. The validator runs
it with the *base* dirt bike on throttle A only (no turbo), so a track that
passes is clearable by a new player without upgrades.
"""
import math
import random

import config as C
from bike import Bike, Controls, base_stats
from track.tiles import MUD, DEBRIS, WATER, PADS, PITS, DRAW, SPLITS, HIGH_LANES, draw_open


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
        self._bridge_col = None         # drawbridge being timed, and whether to ignore it
        self._bridge_blind = False

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
                    # botched jump: nose-down past the rough band (crash), or
                    # nose-high (rough/loop)
                    if self.rng.random() < 0.5:
                        self._jump_error = -self.rng.uniform(C.LAND_ROUGH_NOSE + 2, C.LAND_ROUGH_NOSE + 10)
                    else:
                        self._jump_error = self.rng.uniform(16, 34)
            self._was_air = True
            self._steer_air(bike, c)
            return c
        self._was_air = False
        if self.turbo and bike.temp < self.turbo_temp and bike.wobble == 0:
            c.b = True
        if self._wait_for_bridge(bike):
            c.a = c.b = False
        self._avoid(bike, c)
        return c

    def _wait_for_bridge(self, bike):
        """Drawbridge ahead: keep the throttle on if we'd cross while it's down,
        otherwise ease off as long as a later, safe crossing is still reachable
        by coasting (checked every tick, so it throttles back up in time)."""
        tr = bike.track
        col0 = tr.col_at(bike.x)
        for k in range(0, 15):
            col = (col0 + k) % tr.ncols
            if tr.tile(col, bike.lane_index) != DRAW:
                continue
            if col != self._bridge_col:
                self._bridge_col = col
                self._bridge_blind = self.rng.random() < self.miss * 1.5
            if self._bridge_blind:
                return False
            d = max(0.0, (bike.x // C.TILE_W + k) * C.TILE_W - bike.x)
            now = bike.ticks
            top = bike.max_speed(False)
            accel = max(1.0, bike.stats.accel_interval)

            def arrival(coast_for):
                """Ticks to reach the bridge and to clear it: coast for
                `coast_for` ticks, then full throttle (accelerating to top)."""
                x, v, t, t_in = 0.0, max(bike.speed, 1.0), 0, None
                while t < 420:
                    t += 1
                    if t <= coast_for:
                        v = max(0.0, v - 1.0 / C.COAST_INTERVAL)
                    else:
                        v = min(top, v + 1.0 / accel)
                    x += v * C.SPEED_TO_PX
                    if t_in is None and x >= d:
                        t_in = t
                    if x >= d + C.TILE_W:
                        return t_in, t
                return t_in or t, t

            def safe(coast_for):
                t_in, t_out = arrival(coast_for)
                return not any(draw_open(now + t, col) for t in range(t_in - 3, t_out + 4, 2))

            if safe(0):
                return False
            for wait in range(6, 240, 6):
                if safe(wait):
                    return True       # a coast now and throttle later gets across
            return False
        return False

    def _steer_air(self, bike, c):
        t, land_x = predict_landing(bike)
        lane = bike.lane_index
        if bike.track.terrain_at(land_x, lane) in PITS:
            base = 0.0            # heading for a pit: level out and hope
        else:
            base = math.degrees(math.atan(bike.track.slope(land_x, lane)))
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
        # A lane change takes ~1/lane_rate ticks; it can't climb onto higher ground.
        reach = [bike.x + k * bike.vx for k in range(0, int(1.0 / bike.stats.lane_rate) + 2, 2)]
        split_ahead = tr.has_split and any(
            tr.terrain[tr.col_at(bike.x + i * C.TILE_W)] in SPLITS for i in range(0, 4))

        def lane_cost(lane):
            if tr.has_split and any(tr.ground(x, lane) > tr.ground(x, bike.lane) + C.LANE_STEP_MAX
                                    for x in reach):
                return 1e9
            cost = 0.0
            if split_ahead and lane >= HIGH_LANES:
                cost += 6          # split bridge ahead: take the skyway over the drawbridge
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
    lane = bike.lane_index
    for t in range(1, max_ticks):
        x += vx
        vy -= C.GRAVITY
        h += vy
        if h <= tr.ground(x, lane):
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
