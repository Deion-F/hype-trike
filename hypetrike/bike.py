"""Vehicle physics: speed, temperature, pitch, landings, crashes.

Engine-agnostic: no pygame imports. One call to Bike.step() = one 60 Hz tick.
The same code drives the player, CPU rivals and the ghost-rider validator.
"""
import math
from dataclasses import dataclass, field, replace

import config as C
from track.tiles import (GAP, COOLANT, MUD, DEBRIS, DIRT, GRASS, SAND)


@dataclass
class Controls:
    a: bool = False          # throttle
    b: bool = False          # turbo
    left: bool = False       # lean back / nose up
    right: bool = False      # lean forward / nose down
    lane_up: bool = False    # edge-triggered this tick
    lane_down: bool = False


@dataclass
class BikeStats:
    """Everything upgrades and vehicle classes can change."""
    vehicle: str = "dirt"
    max_speed_a: float = C.SPEED_MAX_A
    max_speed_b: float = C.SPEED_MAX_B
    accel_interval: float = C.ACCEL_INTERVAL
    heat_a: float = C.HEAT_A
    heat_b: float = C.HEAT_B
    cool_coast: float = C.COOL_COAST
    passive_cool: float = 0.0          # extra per-tick cooling while coasting
    coolant_reset: float = C.TEMP_START
    coolant_chill: int = 0             # ticks of no heat gain after a pad
    overheat_ticks: int = C.OVERHEAT_TICKS
    throttle_grace: int = C.THROTTLE_GRACE_TICKS
    pitch_rate: float = C.PITCH_RATE
    nose_drop: float = C.AIR_NOSE_DROP
    land_tolerance: float = C.LAND_TOLERANCE
    land_perfect: float = C.LAND_PERFECT
    crash_ticks: int = C.CRASH_TICKS
    crash_forgives: int = 0
    mud_speed: float = C.MUD_SPEED
    grip: dict = field(default_factory=lambda: {DIRT: 1.0, GRASS: 0.82, SAND: 0.72})
    currency_mult: float = 1.0
    perfect_bonus_chance: float = 0.0

    def copy(self):
        return replace(self, grip=dict(self.grip))


# Base vehicle classes. Unlockables are sidegrades (decision Q8 / 0.3 / 0.4).
VEHICLES = {
    "dirt": dict(name="Dirt Bike", wheels=2,
                 desc="Balanced. Best on dirt.",
                 stats=dict()),
    "trike": dict(name="Trike", wheels=3,
                  desc="Heavy and stable. Wide landings, strong on sand and grass, lower top speed.",
                  stats=dict(max_speed_a=43, max_speed_b=45, accel_interval=4.6,
                             heat_b=0.062, pitch_rate=1.7, land_tolerance=20,
                             land_perfect=6.5,
                             grip={DIRT: 0.94, GRASS: 0.98, SAND: 1.0})),
    "scrambler": dict(name="Scrambler", wheels=2,
                      desc="Grass specialist with knobby tyres. Runs hot on turbo.",
                      stats=dict(max_speed_a=45, max_speed_b=48, heat_b=0.082,
                                 pitch_rate=2.4,
                                 grip={DIRT: 0.96, GRASS: 1.0, SAND: 0.8})),
    "sprinter": dict(name="Sprinter", wheels=2,
                     desc="Light and fast. Hot engine, twitchy and unforgiving.",
                     stats=dict(max_speed_a=48, max_speed_b=51, accel_interval=3.5,
                                heat_a=0.07, heat_b=0.09, pitch_rate=2.7,
                                land_tolerance=11, land_perfect=4,
                                grip={DIRT: 1.0, GRASS: 0.85, SAND: 0.65})),
}


def base_stats(vehicle="dirt") -> BikeStats:
    s = BikeStats(vehicle=vehicle)
    for k, v in VEHICLES[vehicle]["stats"].items():
        setattr(s, k, dict(v) if isinstance(v, dict) else v)
    return s


class Bike:
    def __init__(self, track, stats=None, lane=1, x=C.START_X):
        self.track = track
        self.stats = stats or base_stats()
        self.x = float(x)
        self.lane = lane                 # target lane (int)
        self.lane_pos = float(lane)      # visual / physical lane (float)
        self.speed = 0.0
        self.temp = C.TEMP_START
        self.h = track.ground(self.x)
        self.vy = 0.0
        self.angle = 0.0                 # degrees, positive = nose up
        self.airborne = False
        self.air_ticks = 0
        self.state = "ride"              # ride | crash | overheat | done
        self.timer = 0
        self.crash_reason = ""
        self.forgives_left = self.stats.crash_forgives
        self.wobble = 0
        self.chill = 0
        self._accel_acc = 0.0
        self._grace = 0                  # ticks of throttle grace left after letting go
        self.in_grace = False
        self._one_button = False         # one-button throttle: heat drives speed (player option)
        self.boost_level = 0             # 0 none, 1 boost/turbo, 2 super boost (for effects/HUD)
        self.crash_total = self.stats.crash_ticks
        self._coast_acc = 0
        self._drag_acc = 0
        self._last_cool_col = -1
        self._last_debris_col = -1
        self.ticks = 0
        self.stats_counters = {"perfect": 0, "landings": 0, "crashes": 0, "rough": 0}

    # ------------------------------------------------------------------------
    @property
    def one_button(self):
        return self._one_button

    @one_button.setter
    def one_button(self, on):
        """In one-button mode heat is the throttle, so a fresh bike starts cold."""
        if on and not self._one_button and self.speed == 0 and self.ticks == 0:
            self.temp = 0.0
        self._one_button = bool(on)

    def heat_speed(self):
        """One-button mode: the top speed the current heat allows (before grip)."""
        s, t = self.stats, self.temp
        if t < C.ONE_BOOST_AT:
            return s.max_speed_a * max(0.0, t) / C.ONE_BOOST_AT
        if t < C.ONE_SUPER_AT:
            return s.max_speed_b
        return s.max_speed_b + C.SUPER_BOOST_EXTRA

    @property
    def vx(self):
        return self.speed * C.SPEED_TO_PX

    @property
    def lane_index(self):
        return int(round(self.lane_pos))

    def grip(self):
        return self.stats.grip.get(self.track.material_at(self.x), 1.0)

    def max_speed(self, turbo):
        m = self.stats.max_speed_b if turbo else self.stats.max_speed_a
        return m * self.grip()

    # ------------------------------------------------------------------------
    def step(self, ctl: Controls):
        """Advance one tick. Returns a list of event tuples."""
        ev = []
        self.ticks += 1
        if self.state == "done":
            self.speed = max(0.0, self.speed - 0.5)
            self._move_ground()
            return ev
        if self.state == "crash":
            self._step_crash(ev)
            return ev
        if self.state == "overheat":
            self._step_overheat(ev)
            return ev

        self._lanes(ctl)
        # Throttle grace: briefly after letting go, speed holds instead of coasting
        # down (e.g. while a mouse player re-anchors). Holds at the A cap, so tapping
        # turbo can't keep turbo speed for free, and temperature is frozen meanwhile
        # so tapping can't cool the engine either.
        # Classic mode only: one-button mode's sticky anchor moves without letting
        # go, and there heat should start falling the moment you release.
        if self.one_button:
            self.in_grace = False
        elif ctl.a or ctl.b:
            self._grace = self.stats.throttle_grace
            self.in_grace = False
        else:
            self.in_grace = self._grace > 0
            self._grace = max(0, self._grace - 1)
        self._throttle(ctl)
        self._temperature(ctl, ev)
        if self.state != "ride":
            return ev
        if self.airborne:
            self._air(ctl, ev)
        else:
            self._ground(ctl, ev)
        if self.state == "ride" and not self.airborne:
            self._surfaces(ev)
        if self.wobble > 0:
            self.wobble -= 1
        return ev

    # -- input-driven parts -----------------------------------------------------------
    def _lanes(self, ctl):
        if not self.airborne:
            if ctl.lane_up and self.lane > 0:
                self.lane -= 1
            if ctl.lane_down and self.lane < C.LANES - 1:
                self.lane += 1
        d = self.lane - self.lane_pos
        if abs(d) <= C.LANE_CHANGE_RATE:
            self.lane_pos = float(self.lane)
        else:
            self.lane_pos += math.copysign(C.LANE_CHANGE_RATE, d)

    def _boost_from(self, ctl):
        """0/1/2 boost level for this tick. One-button mode: from the heat alone."""
        if self.one_button:
            if self.temp >= C.ONE_SUPER_AT:
                return 2
            return 1 if self.temp >= C.ONE_BOOST_AT else 0
        if not (ctl.a or ctl.b):
            return 0
        return 1 if ctl.b else 0

    def _throttle(self, ctl):
        self.boost_level = self._boost_from(ctl)
        if self.one_button and not self.airborne:
            self._throttle_one()
            return
        if self.airborne:
            self._drag_acc += 1
            if self._drag_acc >= C.AIR_DRAG_INTERVAL:
                self._drag_acc = 0
                self.speed = max(0.0, self.speed - 1)
            return
        turbo = self.boost_level > 0
        held = ctl.a or ctl.b
        holding = held or self.in_grace
        cap = self.max_speed(turbo) if held else self.max_speed(False) if holding else 0
        if self.boost_level == 2:
            cap += C.SUPER_BOOST_EXTRA * self.grip()
        if self.track.surface_at(self.lane_index, self.x) == MUD:
            cap = min(cap, self.stats.mud_speed) if holding else 0
            mud = True
        else:
            mud = False
        if held and self.speed < cap and self.wobble == 0:
            self._accel_acc += self.grip() / self.stats.accel_interval
            if self._accel_acc >= 1.0:
                self._accel_acc -= 1.0
                self.speed = min(cap, self.speed + (2 if turbo else 1))
        elif self.speed > cap:
            self._coast_acc += 1
            interval = 2 if mud else (C.OVERSPEED_INTERVAL if holding else C.COAST_INTERVAL)
            if self._coast_acc >= interval:
                self._coast_acc = 0
                self.speed = max(cap, self.speed - 1)

    def _throttle_one(self):
        """One-button: speed chases the heat's speed, held or not. Keeping a heat
        level keeps that speed; letting go cools the engine and speed falls with it."""
        cap = self.heat_speed() * self.grip()
        if self.track.surface_at(self.lane_index, self.x) == MUD:
            cap = min(cap, self.stats.mud_speed)
        if self.speed < cap and self.wobble == 0:
            self._accel_acc += self.grip() / self.stats.accel_interval
            if self._accel_acc >= 1.0:
                self._accel_acc -= 1.0
                self.speed = min(cap, self.speed + 2)
        elif self.speed > cap:
            self._coast_acc += 1
            if self._coast_acc >= C.OVERSPEED_INTERVAL:
                self._coast_acc = 0
                self.speed = max(cap, self.speed - 1)

    def _temperature(self, ctl, ev):
        s = self.stats
        if self.in_grace:
            return
        if self.one_button:
            self._temperature_one(ctl, ev)
            return
        if self.chill > 0:
            self.chill -= 1
            if ctl.a or ctl.b:
                return
        if ctl.b and not self.airborne:
            self.temp += s.heat_b
        elif ctl.a or ctl.b:
            if self.temp < C.TEMP_STABLE_A:
                self.temp = min(C.TEMP_STABLE_A, self.temp + s.heat_a)
            else:
                self.temp = max(C.TEMP_STABLE_A, self.temp - C.COOL_A)
        else:
            self.temp = max(C.TEMP_START, self.temp - s.cool_coast - s.passive_cool)
        if self.temp >= C.TEMP_OVERHEAT:
            self.temp = C.TEMP_OVERHEAT
            self.state = "overheat"
            self.timer = s.overheat_ticks
            ev.append(("overheat",))

    def _temperature_one(self, ctl, ev):
        """One-button heat: holding heats (fast while cold, turbo rate in the boost
        band); letting go cools all the way down to cold, and speed follows."""
        s = self.stats
        if self.chill > 0:
            self.chill -= 1
            if ctl.a or ctl.b:
                return
        if ctl.a or ctl.b:
            self.temp += (s.heat_a * C.ONE_COLD_HEAT_MULT if self.temp < C.ONE_BOOST_AT
                          else s.heat_b)
        elif self.temp > 0:
            self.temp = max(0.0, self.temp - s.cool_coast - s.passive_cool)
        if self.temp >= C.TEMP_OVERHEAT:
            self.temp = C.TEMP_OVERHEAT
            self._explode(ev)

    def _explode(self, ev):
        """Pushed past the red window: the bike blows up. A long crash; no forgiveness."""
        self.stats_counters["crashes"] += 1
        self.state = "crash"
        self.crash_total = self.stats.crash_ticks + C.EXPLODE_EXTRA_TICKS
        self.timer = self.crash_total
        self.crash_reason = "explode"
        self.crash_speed = self.speed
        self.speed = 0.0
        self.airborne = False
        self.h = self.track.ground(self.x)
        self.vy = 0.0
        self.temp = 0.0
        self.boost_level = 0
        self._dropped = False
        ev.append(("explode",))

    def _ground(self, ctl, ev):
        new_x = self.x + self.vx
        new_g = self.track.ground(new_x)
        vy_ground = new_g - self.h
        if self.vx > 0 and vy_ground < self.vy - C.GRAVITY - 0.05:
            # The ground falls away faster than gravity: take off.
            self.airborne = True
            self.air_ticks = 0
            self.x = new_x
            self.vy -= C.GRAVITY
            self.h += self.vy
            ev.append(("takeoff",))
            return
        self.x = new_x
        self.h = new_g
        self.vy = vy_ground
        target = math.degrees(math.atan(self.track.slope(self.x)))
        if ctl.left and self.speed > 4:
            target += 14          # small wheelie (cosmetic + nose-up)
        self.angle += (target - self.angle) * C.GROUND_ANGLE_LERP

    def _air(self, ctl, ev):
        s = self.stats
        self.air_ticks += 1
        if ctl.left and not ctl.right:
            self.angle += s.pitch_rate
        elif ctl.right and not ctl.left:
            self.angle -= s.pitch_rate
        else:
            self.angle -= s.nose_drop
        self.angle = max(-85.0, min(85.0, self.angle))
        self.x += self.vx
        self.vy -= C.GRAVITY
        self.h += self.vy
        g = self.track.ground(self.x)
        if self.h <= g:
            self.h = g
            self.airborne = False
            self._land(ev)

    def _land(self, ev):
        s = self.stats
        self.stats_counters["landings"] += 1
        if self.track.terrain_at(self.x) == GAP:
            if self.h < -10:
                self._crash(ev, "pit")
                return
            # Caught the far lip: pop up onto the next column.
            self.x = (int(self.x // C.TILE_W) + 1) * C.TILE_W + 1
            self.h = self.track.ground(self.x)
        slope_deg = math.degrees(math.atan(self.track.slope(self.x)))
        err = self.angle - slope_deg
        if self.air_ticks < C.MICRO_HOP_TICKS:
            # Little hops (whoops, ramp lips): bad angle costs speed, not a crash.
            if abs(err) > s.land_tolerance:
                self.speed *= C.MICRO_HOP_SPEED_KEEP
                self.wobble = C.ROUGH_WOBBLE_TICKS // 3
                ev.append(("bounce",))
            self.angle = slope_deg
            self.vy = 0.0
            self.stats_counters["landings"] -= 1
            return
        if abs(err) <= s.land_perfect:
            self.stats_counters["perfect"] += 1
            ev.append(("perfect",))
        elif abs(err) <= s.land_tolerance:
            ev.append(("land",))
        elif 0 < err <= C.LAND_ROUGH:
            self.speed *= C.ROUGH_SPEED_KEEP
            self.wobble = C.ROUGH_WOBBLE_TICKS
            self.stats_counters["rough"] += 1
            if self.one_button:
                # heat is speed here: a sloppy landing dumps heat, so landing
                # well is how you keep your boost
                self.temp = max(0.0, self.temp - C.ONE_ROUGH_HEAT_LOSS)
            ev.append(("rough",))
        else:
            self._crash(ev, "nose" if err < 0 else "loop")
            return
        self.angle = slope_deg
        self.vy = 0.0

    def _surfaces(self, ev):
        col = self.track.col_at(self.x)
        surf = self.track.surface[self.lane_index][col]
        if surf != COOLANT:
            self._last_cool_col = -1
        if surf != DEBRIS:
            self._last_debris_col = -1
        if surf == COOLANT and col != self._last_cool_col:
            self._last_cool_col = col
            self.chill = self.stats.coolant_chill
            if self.one_button:
                # One-button: pads are heat pads. A burst of heat (speed) that can
                # push you into the red, or past it.
                self.temp += C.ONE_HEAT_PAD
                ev.append(("heatpad",))
            else:
                self.temp = min(self.temp, self.stats.coolant_reset)
                ev.append(("coolant",))
        elif surf == DEBRIS and col != self._last_debris_col:
            lx = self.x % C.TILE_W
            if 28 <= lx <= 52 and abs(self.lane_pos - self.lane_index) < 0.4:
                self._last_debris_col = col
                if self.speed > DEBRIS_SAFE:
                    self._crash(ev, "debris")
                else:
                    self.speed = 0
                    ev.append(("bump",))

    # -- crash / overheat --------------------------------------------------------------
    def _crash(self, ev, reason):
        if self.forgives_left > 0 and reason != "pit":
            self.forgives_left -= 1
            self.speed *= 0.6
            self.angle = 0
            self.vy = 0
            self.h = self.track.ground(self.x)
            self.airborne = False
            ev.append(("forgiven",))
            return
        self.stats_counters["crashes"] += 1
        self.state = "crash"
        self.crash_total = self.stats.crash_ticks
        self.timer = self.crash_total
        self.crash_reason = reason
        self.boost_level = 0
        if self.one_button:
            self.temp = 0.0          # heat is a resource in this mode: a crash loses it
        self.crash_speed = self.speed
        self.speed = 0.0
        self.airborne = False
        ev.append(("crash", reason))

    def _step_crash(self, ev):
        self.timer -= 1
        elapsed = self.crash_total - self.timer
        if self.crash_reason == "explode":
            if not self._dropped and elapsed >= self.crash_total * C.EXPLODE_DROP_AT:
                self._dropped = True
                ev.append(("bike_drop",))
        elif elapsed < 18 and self.crash_reason != "pit":
            self.x += max(0.0, 2.5 - elapsed * 0.14)   # bike tumbles a bit
        if self.timer <= 0:
            # Respawn on solid ground: walk out of a pit to the next column.
            if self.track.terrain_at(self.x) == GAP:
                self.x = (int(self.x // C.TILE_W) + 1) * C.TILE_W + 2
            self.h = self.track.ground(self.x)
            self.vy = 0.0
            self.angle = math.degrees(math.atan(self.track.slope(self.x)))
            self.state = "ride"
            self.wobble = 0
            ev.append(("recovered",))

    def _step_overheat(self, ev):
        self.timer -= 1
        if self.airborne:
            self._air(Controls(), ev)
        else:
            self.speed = max(0.0, self.speed - 1.5)
            self._move_ground()
        if self.timer <= 0 and not self.airborne:
            self.temp = C.TEMP_START
            self.state = "ride"
            ev.append(("cooled",))

    def _move_ground(self):
        self.x += self.vx
        if self.track.terrain_at(self.x) == GAP:
            # Rolled into a pit while stalled: hop to the far edge.
            self.x = (int(self.x // C.TILE_W) + 1) * C.TILE_W + 2
        self.h = self.track.ground(self.x)


DEBRIS_SAFE = C.DEBRIS_SAFE_SPEED
