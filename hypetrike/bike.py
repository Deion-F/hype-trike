"""Vehicle physics: speed, temperature, pitch, landings, crashes.

Engine-agnostic: no pygame imports. One call to Bike.step() = one 60 Hz tick.
The same code drives the player, CPU rivals and the ghost-rider validator.
"""
import math
from dataclasses import dataclass, field, replace

import config as C
from track.tiles import (GAP, MUD, DEBRIS, WATER, DIRT, GRASS, SAND, PADS, PAD_BARS, RAMPS,
                         PITS, DECK_GAP, DRAW, draw_open, edge_heights)


@dataclass
class Controls:
    a: bool = False          # throttle
    b: bool = False          # turbo
    left: bool = False       # lean back / nose up
    right: bool = False      # lean forward / nose down
    lane_up: bool = False    # edge-triggered this tick
    lane_down: bool = False
    ramp: bool = False       # mouse "button" scheme, mid-air: pitch builds with hold time -
                             # nose-down (right) starts gentle, and with no lean the nose
                             # lifts faster the longer it's free (releasing leans back)


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
    # heat / handling levers (run upgrades)
    super_extra: float = C.SUPER_BOOST_EXTRA   # top speed over turbo in the red (one-button)
    warmup_mult: float = 1.0           # one-button: cold-engine heating rate multiplier
    red_heat_mult: float = 1.0         # heating rate in the red zone (past RED_AT)
    vent_charges: int = 0              # per race: an overheat / blow-up vents instead
    explode_ticks: int = C.EXPLODE_EXTRA_TICKS  # extra crash time for a blow-up
    perfect_heat: float = 0.0          # perfect landing: +heat (one-button) / -heat (classic)
    rough_loss_mult: float = 1.0       # share of the rough-landing speed / heat loss taken
    lane_rate: float = C.LANE_CHANGE_RATE
    respawn_heat: float = 0.0          # one-button: heat after recovering from a crash
    # run-upgrade mechanics (see run/upgrades.py)
    hang_kick: float = 0.0             # Hang Time: speed per second airborne on a clean landing
    land_saves: int = 0                # Crumple Zone: crash landings turned rough, per race
    adrenaline_ticks: int = 0          # Adrenaline: red zone heats slower for this long after a perfect
    comeback_ticks: int = 0            # Comeback: double acceleration this long after remounting
    draft_bonus: float = 0.0           # Slipstream: top-speed share while a rival is just ahead
    lane_kick: float = 0.0             # Line Choice: speed kick per finished lane change
    barrier_saves: int = 0             # Barrier Buster: barriers smashed instead of crashing, per race
    prize_coins: int = 0               # Prize Money: coins per race won this run
    boss_bounty: int = 0               # Bounty Hunter: coins per boss beaten this run

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
                                land_tolerance=12, land_perfect=4,
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
        self.h = track.ground(self.x, self.lane_index)
        self.vy = 0.0
        self.angle = 0.0                 # degrees, positive = nose up
        self.airborne = False
        self.air_ticks = 0
        self.free_ticks = 0              # ticks the button has been up mid-air (Controls.ramp)
        self.press_ticks = 0             # ticks the button has pushed the nose down (Controls.ramp)
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
        self._last_water_col = -1
        self.ticks = 0
        self.vents_left = self.stats.vent_charges
        self.land_saves_left = self.stats.land_saves
        self._perfect_grace = 0          # ticks left of "was lined up for a PERFECT just now"
        self.barrier_saves_left = self.stats.barrier_saves
        self.adrenaline = 0              # ticks of Adrenaline left
        self.comeback = 0                # ticks of Comeback left
        self.drafting = False            # set by the race: a rival is just ahead in this lane
        self.trail = None                # set by the race: the boss trail kind we're riding in ...
        self.trail_k = 1.0               # ... and its strength (minions 0.5)
        self.heat_aura = 0.0             # boss aura: heat per tick (Heat Wave +, Sandblast -)
        self.land_mult = 1.0             # boss aura: landing windows scaled (Hex 0.7)
        self._kick_cd = 0                # Line Choice cooldown
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
            return s.max_speed_b * self._draft()
        return (s.max_speed_b + s.super_extra) * self._draft()

    def climbing(self):
        """On the ground going up a ramp / rise: the engine doesn't heat here, so
        carry your speed in and never fear blowing up on the climb."""
        return not self.airborne and self.track.slope(self.x, self.lane_index) > C.CLIMB_SLOPE

    def _draft(self):
        return 1.0 + self.stats.draft_bonus if self.drafting else 1.0

    def _accel_interval(self):
        """Comeback: double acceleration for a while after remounting."""
        return self.stats.accel_interval * (0.5 if self.comeback > 0 else 1.0)

    def _red_mult(self):
        """Heating rate multiplier in the red; Adrenaline slows it after a perfect landing."""
        return self.stats.red_heat_mult * (0.4 if self.adrenaline > 0 else 1.0)

    @property
    def vx(self):
        return self.speed * C.SPEED_TO_PX

    @property
    def lane_index(self):
        return int(round(self.lane_pos))

    @property
    def on_lava(self):
        """Volcano theme: hot air (faster heat, slower cooling), lava pits."""
        return self.track.theme == C.LAVA_THEME

    def _env(self):
        """(heat gain, cooling) multipliers from the level."""
        return (C.LAVA_HEAT_MULT, C.LAVA_COOL_MULT) if self.on_lava else (1.0, 1.0)

    def predicted_landing(self, max_ticks=240):
        """(ticks until touchdown, landing x) on the current arc with no input."""
        x, h, vy, vx = self.x, self.h, self.vy, self.vx
        for t in range(1, max_ticks):
            x += vx
            vy -= C.GRAVITY
            h += vy
            if h <= self.track.ground(x, self.lane_index):
                return t, x
        return max_ticks, x

    def perfect_aligned(self):
        """Mid-air on a real jump, with the nose already matching the landing
        slope closely enough for a PERFECT if it touched down like this."""
        if not self.airborne or self.state != "ride":
            return False
        t, x = self.predicted_landing()
        if self.air_ticks + t < C.MICRO_HOP_TICKS or self.track.terrain_at(x, self.lane_index) in PITS:
            return False
        slope = math.degrees(math.atan(self.track.slope(x, self.lane_index)))
        # the nose keeps dropping until touchdown: judge the angle it will land at
        land_angle = max(-85.0, self.angle - self.stats.nose_drop * t)
        return abs(land_angle - slope) <= self.stats.land_perfect * self.land_mult

    def grip(self):
        return self.stats.grip.get(self.track.material_at(self.x), 1.0)

    def max_speed(self, turbo):
        m = self.stats.max_speed_b if turbo else self.stats.max_speed_a
        return m * self.grip() * self._draft()

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

        if self.adrenaline > 0:
            self.adrenaline -= 1
        if self.comeback > 0:
            self.comeback -= 1
        if self._kick_cd > 0:
            self._kick_cd -= 1
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
        if self.state == "ride" and (self.trail or self.heat_aura):
            self._trail_effects(ev)
        if self.state != "ride":
            return ev
        if self.airborne:
            self._air(ctl, ev)
        else:
            self._ground(ctl, ev)
        if self.state == "ride" and not self.airborne and self._over_open_bridge():
            self._fall_through(ev)
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
        old = self.lane_index
        d = self.lane - self.lane_pos
        rate = self.stats.lane_rate
        if abs(d) <= rate:
            if d and self.stats.lane_kick and not self.airborne and self._kick_cd == 0:
                # Line Choice: finishing a lane change kicks a little speed past the cap
                self.speed += self.stats.lane_kick
                self._kick_cd = C.FPS
            self.lane_pos = float(self.lane)
        else:
            self.lane_pos += math.copysign(rate, d)
        new = self.lane_index
        if new != old and self.track.has_split and self.track.ground(self.x, new) > self.h + C.LANE_STEP_MAX:
            # The lane next door is higher here (the skyway beside a split
            # bridge's deck): you can drop off it, not climb onto it sideways.
            self.lane = old
            self.lane_pos = float(old)
            self.wobble = max(self.wobble, 8)

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
            cap += self.stats.super_extra * self.grip()
        if self.track.surface_at(self.lane_index, self.x) == MUD or self.trail == "mud":
            cap = min(cap, self._mud_cap()) if holding else 0
            mud = True
        else:
            mud = False
        if held and self.speed < cap and self.wobble == 0:
            self._accel_acc += self.grip() / self._accel_interval()
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
        if self.track.surface_at(self.lane_index, self.x) == MUD or self.trail == "mud":
            cap = min(cap, self._mud_cap())
        if self.speed < cap and self.wobble == 0:
            self._accel_acc += self.grip() / self._accel_interval()
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
        hot, cool = self._env()
        if (self.airborne or self.climbing() or self._sand_stall()) and (ctl.a or ctl.b):
            pass                     # no heat gained in the air or up a ramp (letting go still cools)
        elif ctl.b:
            self.temp += s.heat_b * hot * (self._red_mult() if self.temp >= C.RED_AT else 1.0)
        elif ctl.a or ctl.b:
            if self.temp < C.TEMP_STABLE_A:
                self.temp = min(C.TEMP_STABLE_A, self.temp + s.heat_a * hot)
            else:
                self.temp = max(C.TEMP_STABLE_A, self.temp - C.COOL_A * cool)
        else:
            self.temp = max(C.TEMP_START, self.temp - (s.cool_coast + s.passive_cool) * cool)
        if self.temp >= C.TEMP_OVERHEAT and self._vent(ev, C.TEMP_STABLE_A):
            return
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
        hot, cool = self._env()
        if (self.airborne or self.climbing() or self._sand_stall()) and (ctl.a or ctl.b):
            pass                     # holding in the air or up a ramp keeps your heat, never adds to it
        elif ctl.a or ctl.b:
            if self.temp < C.ONE_BOOST_AT:
                comeback = 2.0 if self.comeback > 0 else 1.0     # Comeback: warm up fast after a crash
                self.temp += s.heat_a * C.ONE_COLD_HEAT_MULT * s.warmup_mult * hot * comeback
            else:
                self.temp += s.heat_b * hot * (self._red_mult() if self.temp >= C.ONE_SUPER_AT else 1.0)
        elif self.temp > 0:
            self.temp = max(0.0, self.temp - (s.cool_coast + s.passive_cool) * cool)
        self._check_blowup(ev)

    def _check_blowup(self, ev):
        """One-button: at the top of the gauge the bike blows, unless a vent is left."""
        if self.temp >= C.TEMP_OVERHEAT and not self._vent(ev, C.ONE_SUPER_AT - C.VENT_DROP):
            self.temp = C.TEMP_OVERHEAT
            self._explode(ev)

    def _mud_cap(self):
        """Mud speed limit; a weaker (minion) mud trail lets more speed through."""
        k = self.trail_k if self.trail == "mud" else 1.0
        return self.stats.mud_speed / max(0.2, k)

    def _sand_stall(self):
        """A full-strength sandstorm stops heat building (a minion's halves it,
        every other tick)."""
        if self.trail != "sand":
            return False
        return self.trail_k >= 1.0 or self.ticks % 2 == 0

    def _trail_effects(self, ev):
        """Boss trails and auras (bosses.py), scaled by strength: oil wobbles you,
        smoke cools you, fire and Heat Wave heat you, Sandblast drains you (mud and
        sand act in the throttle / heat code)."""
        from bosses import TRAIL_HEAT, TRAIL_DRAG_EVERY
        k = self.trail_k
        heat = self.heat_aura
        if self.trail == "oil":
            self.wobble = max(self.wobble, max(1, round(4 * k)))
        elif self.trail in TRAIL_HEAT:
            heat += TRAIL_HEAT[self.trail] * k
        if heat < 0 and not self.one_button:
            # classic: cooling would help, so smoke / Sandblast drag your speed instead
            if self.ticks % max(1, round(TRAIL_DRAG_EVERY * 0.3 / -heat)) == 0:
                self.speed = max(0.0, self.speed - 1)
        elif heat:
            self.external_heat(heat, ev)

    def external_heat(self, amount, ev):
        """Heat from outside the engine (boss trails, auras, pyro, lava): can blow
        you up (one-button) or stall you (classic), like riding too hot."""
        floor = 0.0 if self.one_button else C.TEMP_START
        self.temp = max(floor, self.temp + amount)
        if self.state != "ride":
            return
        if self.one_button:
            self._check_blowup(ev)
        elif self.temp >= C.TEMP_OVERHEAT and not self._vent(ev, C.TEMP_STABLE_A):
            self.temp = C.TEMP_OVERHEAT
            self.state = "overheat"
            self.timer = self.stats.overheat_ticks
            ev.append(("overheat",))

    def _vent(self, ev, to):
        """Radiator upgrade: spend a vent charge to drop the heat instead of blowing."""
        if self.vents_left <= 0:
            return False
        self.vents_left -= 1
        self.temp = to
        ev.append(("vent",))
        return True

    def _explode(self, ev):
        """Pushed past the red window: the bike blows up. A long crash; no forgiveness."""
        self.stats_counters["crashes"] += 1
        self.state = "crash"
        self.crash_total = self.stats.crash_ticks + self.stats.explode_ticks
        self.timer = self.crash_total
        self.crash_reason = "explode"
        self.crash_speed = self.speed
        self.speed = 0.0
        self.airborne = False
        self.h = self.track.ground(self.x, self.lane_index)
        self.vy = 0.0
        self.temp = 0.0
        self.boost_level = 0
        self._dropped = False
        ev.append(("explode",))

    def _ground(self, ctl, ev):
        self.free_ticks = self.press_ticks = 0
        new_x = self.x + self.vx
        new_g = self.track.ground(new_x, self.lane_index)
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
        target = math.degrees(math.atan(self.track.slope(self.x, self.lane_index)))
        if ctl.left and self.speed > 4:
            target += 14          # small wheelie (cosmetic + nose-up)
        self.angle += (target - self.angle) * C.GROUND_ANGLE_LERP

    def _air(self, ctl, ev):
        s = self.stats
        self.air_ticks += 1
        if ctl.ramp and ctl.right and not ctl.left:
            # Mouse button scheme, button held: push the nose down. A tap is a
            # nudge, a hold winds up to the full pitch rate.
            self.press_ticks += 1
            self.free_ticks = 0
            self.angle -= s.pitch_rate * min(1.0, C.PRESS_START + self.press_ticks * C.PRESS_GROW)
            return self._air_move(ev)
        self.press_ticks = 0
        if ctl.left and not ctl.right:
            self.angle += s.pitch_rate
            self.free_ticks = 0
        elif ctl.right and not ctl.left:
            self.angle -= s.pitch_rate
            self.free_ticks = 0
        elif ctl.ramp:
            # Mouse button scheme, button up: the nose lifts, starting at the
            # drift rate and speeding up towards the full pitch rate, so a short
            # release nudges it and a long one swings it up as hard as leaning back.
            self.free_ticks += 1
            self.angle += s.nose_drop + s.pitch_rate * min(C.RELEASE_MAX, self.free_ticks * C.RELEASE_GROW)
        else:
            self.free_ticks = 0
            self.angle -= s.nose_drop
        self._air_move(ev)

    def _air_move(self, ev):
        self.angle = max(-85.0, min(85.0, self.angle))
        self.x += self.vx
        self.vy -= C.GRAVITY
        self.h += self.vy
        g = self.track.ground(self.x, self.lane_index)
        if self.h > g:
            # Grace: lined up for a PERFECT just above the ground counts for a few
            # ticks, so a tiny last-moment twitch doesn't throw it away.
            slope_deg = math.degrees(math.atan(self.track.slope(self.x, self.lane_index)))
            if self.h - g <= C.PERFECT_GRACE_PX and \
                    abs(self.angle - slope_deg) <= self.stats.land_perfect * self.land_mult:
                self._perfect_grace = C.PERFECT_GRACE_TICKS
            elif self._perfect_grace > 0:
                self._perfect_grace -= 1
        if self.h <= g:
            if g - self.h > C.WALL_CATCH and self.track.terrain_at(self.x - C.TILE_W * 0.5, self.lane_index) in (DECK_GAP, DRAW):
                # Came up short of a broken span / open drawbridge: hit the far
                # wall and drop into the hole.
                self.x = (int(self.x // C.TILE_W)) * C.TILE_W - 6
                self.h = min(self.h, g)
                self._crash(ev, "pit")
                return
            self.h = g
            self.airborne = False
            self._land(ev)
            if self.state == "ride" and self._over_open_bridge():
                self._fall_through(ev)

    def _over_open_bridge(self):
        col = self.track.col_at(self.x)
        return self.track.tile(col, self.lane_index) == DRAW and draw_open(self.ticks, col)

    def _fall_through(self, ev):
        """Rode (or landed) onto a lifted drawbridge: straight into the hole."""
        self.h = self.track.ground(self.x, self.lane_index) - 40
        self._crash(ev, "pit")

    def _land(self, ev):
        s = self.stats
        tol, per = s.land_tolerance * self.land_mult, s.land_perfect * self.land_mult   # Hex aura
        self.stats_counters["landings"] += 1
        here = self.track.terrain_at(self.x, self.lane_index)
        if here in PITS:
            if self.h < edge_heights(here)[1] - 10:
                self._crash(ev, "pit")
                return
            # Caught the far lip: pop up onto the next column.
            self.x = (int(self.x // C.TILE_W) + 1) * C.TILE_W + 1
            self.h = self.track.ground(self.x, self.lane_index)
        slope_deg = math.degrees(math.atan(self.track.slope(self.x, self.lane_index)))
        err = self.angle - slope_deg
        if self.air_ticks < C.MICRO_HOP_TICKS:
            # Little hops (whoops, ramp lips): bad angle costs speed, not a crash.
            if abs(err) > tol:
                self.speed *= C.MICRO_HOP_SPEED_KEEP
                self.wobble = C.ROUGH_WOBBLE_TICKS // 3
                ev.append(("bounce",))
            self.angle = slope_deg
            self.vy = 0.0
            self.stats_counters["landings"] -= 1
            return
        if abs(err) > tol and not -C.LAND_ROUGH_NOSE <= err <= C.LAND_ROUGH \
                and self.land_saves_left > 0:
            # Crumple Zone: this crash landing folds into a rough one
            self.land_saves_left -= 1
            err = max(-C.LAND_ROUGH_NOSE, min(C.LAND_ROUGH, err))
            ev.append(("saved",))
        if abs(err) <= tol and s.hang_kick:
            # Hang Time: a clean landing turns airtime into speed past the cap
            self.speed += min(3 * s.hang_kick, s.hang_kick * self.air_ticks / C.FPS)
        graced = self._perfect_grace > 0 and abs(err) <= tol
        self._perfect_grace = 0
        if abs(err) <= per or graced:
            self.stats_counters["perfect"] += 1
            self.adrenaline = max(self.adrenaline, s.adrenaline_ticks)
            if s.perfect_heat:
                # Hype Landing: a heat kick in one-button mode (never past the top),
                # a cool-down in classic mode.
                if self.one_button:
                    self.temp = max(self.temp, min(C.TEMP_OVERHEAT - 1.0, self.temp + s.perfect_heat))
                else:
                    self.temp = max(C.TEMP_START, self.temp - s.perfect_heat)
            ev.append(("perfect",))
        elif abs(err) <= tol:
            ev.append(("land",))
        elif -C.LAND_ROUGH_NOSE <= err <= C.LAND_ROUGH:
            self.speed *= 1.0 - (1.0 - C.ROUGH_SPEED_KEEP) * s.rough_loss_mult
            self.wobble = C.ROUGH_WOBBLE_TICKS
            self.stats_counters["rough"] += 1
            if self.one_button:
                # heat is speed here: a sloppy landing dumps heat, so landing
                # well is how you keep your boost
                self.temp = max(0.0, self.temp - C.ONE_ROUGH_HEAT_LOSS * s.rough_loss_mult)
            ev.append(("rough",))
        else:
            self._crash(ev, "nose" if err < 0 else "loop")
            return
        self.angle = slope_deg
        self.vy = 0.0

    def _surfaces(self, ev):
        col = self.track.col_at(self.x)
        surf = self.track.surface[self.lane_index][col]
        if surf not in PADS:
            self._last_cool_col = -1
        if surf != DEBRIS:
            self._last_debris_col = -1
        if surf != WATER:
            self._last_water_col = -1
        if surf == WATER and col != self._last_water_col:
            self._last_water_col = col
            self._splash(ev)
            return
        if surf in PADS and col != self._last_cool_col:
            self._last_cool_col = col
            self.chill = self.stats.coolant_chill
            if self.one_button:
                # One-button: pads are heat pads, +1/+2/+3 bars by size. A burst
                # of heat (speed) that can push you into the red, or past it.
                bars = PAD_BARS[surf]
                self.temp += bars * C.HEAT_BAR
                ev.append(("heatpad", bars))
                self._check_blowup(ev)
            else:
                self.temp = min(self.temp, self.stats.coolant_reset)
                ev.append(("coolant",))
        elif surf == DEBRIS and col != self._last_debris_col:
            lx = self.x % C.TILE_W
            if 28 <= lx <= 52 and abs(self.lane_pos - self.lane_index) < 0.4:
                self._last_debris_col = col
                if self.speed > DEBRIS_SAFE and self.barrier_saves_left > 0:
                    self.barrier_saves_left -= 1          # Barrier Buster: smash through it
                    self.speed *= 0.85
                    ev.append(("smash",))
                elif self.speed > DEBRIS_SAFE:
                    self._crash(ev, "debris")
                else:
                    self.speed = 0
                    ev.append(("bump",))

    def _splash(self, ev):
        """Water puddle: cools the engine and costs speed. On the Volcano theme the
        puddle is a lava pit: a speed kick past the cap and a lot of heat."""
        if self.on_lava:
            self.temp += C.LAVA_PIT_HEAT
            self.speed += C.LAVA_PIT_SPEED
            ev.append(("lava",))
            if self.one_button:
                self._check_blowup(ev)
            return
        floor = 0.0 if self.one_button else C.TEMP_START
        self.temp = max(floor, self.temp - C.WATER_COOL)
        self.speed *= C.WATER_SPEED_KEEP
        ev.append(("splash",))

    # -- crash / overheat --------------------------------------------------------------
    def _crash(self, ev, reason):
        if self.forgives_left > 0 and reason != "pit":
            self.forgives_left -= 1
            self.speed *= 0.6
            self.angle = 0
            self.vy = 0
            self.h = self.track.ground(self.x, self.lane_index)
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
            # Respawn on solid ground with a clear run-up: past any hazard just ahead.
            self.x = self._safe_respawn_x()
            self.h = self.track.ground(self.x, self.lane_index)
            self.vy = 0.0
            self.angle = math.degrees(math.atan(self.track.slope(self.x, self.lane_index)))
            self.state = "ride"
            self.wobble = 0
            if self.one_button:
                self.temp = self.stats.respawn_heat     # Pre-Heater: restart warm
            self.comeback = self.stats.comeback_ticks
            ev.append(("recovered",))

    def _respawn_hazard(self, col):
        """Something a rider starting from a standstill can't get past: a pit, a
        broken span, a drawbridge (open or not), a barrier, water / lava, or a
        launch ramp straight into a pit (the jump needs speed)."""
        lane, tr = self.lane_index, self.track
        n = tr.ncols
        tile = tr.tile(col % n, lane)
        if tile in PITS + (DRAW,) or tr.surface[lane][col % n] in (DEBRIS, WATER):
            return True
        return tile in RAMPS and any(tr.tile((col + k) % n, lane) in PITS + (DRAW,) for k in (1, 2))

    def _safe_respawn_x(self):
        """Where to respawn: the crash spot, unless a hazard lies within
        RESPAWN_CLEAR_COLS tiles ahead (or under it). Then just past that hazard,
        repeating for hazards that follow, at most RESPAWN_MAX_SKIP tiles on."""
        start = int(self.x // C.TILE_W)
        col = start
        while col - start < C.RESPAWN_MAX_SKIP:
            ahead = [c for c in range(col, col + C.RESPAWN_CLEAR_COLS + 1)
                     if self._respawn_hazard(c)]
            if not ahead:
                break
            col = ahead[-1] + 1
        if col == start:
            return self.x
        col = min(col, start + C.RESPAWN_MAX_SKIP)
        for _ in range(self.track.ncols):    # capped mid-cluster: still never in a hole
            if not self._respawn_hazard(col):
                break
            col += 1
        return col * C.TILE_W + 2

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
        if self.track.terrain_at(self.x, self.lane_index) in PITS or self._over_open_bridge():
            # Rolled into a pit while stalled: hop to the far edge.
            self.x = (int(self.x // C.TILE_W) + 1) * C.TILE_W + 2
        self.h = self.track.ground(self.x, self.lane_index)


DEBRIS_SAFE = C.DEBRIS_SAFE_SPEED
