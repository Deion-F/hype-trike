"""Biome bosses and their minions.

In a boss race the rival with the best setup is promoted to the biome's boss:
a themed bike + rider (ui/art.py), always boosting, with a trail and two
powers that test a skill the player has learned by then (lanes, jumps,
landings, heat). The other rivals become its minions: the boss's colours and a
half-strength, shorter-lived trail. Everything here only affects the player
and is driven from the race seed, so replays match.

Trail kinds (bike.Bike reacts; strength k scales them, minions 0.5):
  mud    caps your speed            sand   your heat builds slower (none at k=1)
  oil    you wobble (no accel)      smoke  cools your heat (classic: drag)
  fire   heats you fast
"""
import random
from collections import deque

import config as C

TILE = C.TILE_W

BOSSES = {
    "valley": dict(
        name="MUD BARON", vehicle="trike", trail="mud", boost="toxic", glow=(150, 200, 60),
        powers=[("Mud Bomb", "lobs mud into your lane ahead: watch the shadow, change lanes"),
                ("Quake", "big landings shake you up close: give the Baron room"),
                ("Mud trail", "mud behind it bogs you down: pass in another lane")]),
    "desert": dict(
        name="DUNE RAIDER", vehicle="scrambler", trail="sand", boost="gold", glow=(255, 200, 90),
        powers=[("Sandblast", "chasing close behind you drains your heat: jump or get 2 lanes away"),
                ("Dust Devil", "a whirlwind hops lanes and shoves you aside: jump over it"),
                ("Sand trail", "your heat can't build in its sandstorm")]),
    "night": dict(
        name="PHANTOM", vehicle="sprinter", trail="oil", boost="plasma", glow=(170, 90, 255),
        powers=[("Blackout", "the lights die for 2 s (it flickers first): know the track"),
                ("Hex", "landing windows are 30% tighter near it: land clean"),
                ("Oil trail", "its slick wobbles you: no speed while you're in it")]),
    "stadium": dict(
        name="SHOWSTOPPER", vehicle="dirt", trail="smoke", boost="neon", glow=(255, 215, 60),
        powers=[("Crowd Favourite", "its PERFECTs give it a burst: land PERFECT near it to steal one"),
                ("Pyro Cannons", "fire jets on marked lanes add heat: dodge them while overheating"),
                ("Smoke trail", "pyro smoke behind it cools your engine")]),
    "lava": dict(
        name="INFERNO", vehicle="sprinter", trail="fire", boost="flame", glow=(255, 90, 30),
        powers=[("Heat Wave", "your heat climbs near it: pass it cool, never overheating"),
                ("Eruption", "lava bursts in your lane: dodge it, or hit it cold for speed"),
                ("Fire trail", "its trail overheats you fast: never ride behind it")]),
}

TRAIL_EVERY = 3          # ticks between trail points
TRAIL_LIFE = 150         # ticks a boss trail point lasts (2.5 s)
MINION_LIFE = 70         # ... and a minion's
MINION_K = 0.5           # minion trail strength
TRAIL_REACH = 12         # px either side of a point that counts as "in it"
TRAIL_HEAT = {"fire": 0.32, "smoke": -0.3}      # heat per tick in the trail (x strength)
TRAIL_DRAG_EVERY = 6                            # classic smoke: -1 speed this often
BLACKOUT_FLICKER = 45                           # ticks of warning flicker before the dark
BLACKOUT_DARK = 120                             # ticks of darkness


def boss_score(stats, kit):
    """How strong a rival's setup is: top speed first, then its Starter Kit."""
    return stats.max_speed_b + 0.25 * sum(kit.values()) + 0.1 * stats.land_tolerance


class BossTrail:
    """A trail of (x, lane, tick) points dropped by one rider on the ground."""

    def __init__(self, kind, owner=None, life=TRAIL_LIFE, k=1.0):
        self.kind, self.owner, self.life, self.k = kind, owner, life, k
        self.points = deque()

    def update(self, rider, tick):
        while self.points and tick - self.points[0][2] > self.life:
            self.points.popleft()
        if tick % TRAIL_EVERY == 0 and rider.state == "ride" and not rider.airborne and rider.speed > 5:
            self.points.append((rider.x - 14, rider.lane_index, tick))

    def hits(self, bike):
        if bike.airborne or bike.state != "ride":
            return False
        lane = bike.lane_index
        return any(l == lane and abs(bike.x - x) < TRAIL_REACH for x, l, _ in self.points)


class Hazard:
    """A boss power on the track: warns first, then is live in one lane.
    kind: mud | devil (hops across lanes) | pyro | lava."""

    def __init__(self, kind, x, lane, start, warn, life, rng=None):
        self.kind, self.x, self.lane = kind, x, lane
        self.start, self.warn, self.life = start, warn, life
        self.dir = 1 if (rng and rng.random() < 0.5) else -1
        self.used = False          # one-shot hazards (devil, pyro, lava) hit once

    def live(self, t):
        return self.start + self.warn <= t < self.start + self.warn + self.life

    def done(self, t):
        return t >= self.start + self.warn + self.life

    def step(self, t):
        if self.kind == "devil" and self.live(t) and (t - self.start) % 25 == 0:
            if not 0 <= self.lane + self.dir < C.LANES:
                self.dir = -self.dir
            self.lane += self.dir

    def touches(self, bike, low_air=0):
        if bike.state != "ride" or bike.lane_index != self.lane:
            return False
        if bike.airborne and bike.h - bike.track.ground(bike.x, bike.lane_index) > low_air:
            return False
        w = 20 if self.kind == "devil" else TILE / 2
        return abs(bike.x - self.x) < w


class BossBrain:
    """Runs a boss's powers each tick. Reads the race, changes only the player.
    Exposes what the renderer needs: hazards, blackout state, aura flag."""

    COOLDOWN = {"valley": 300, "desert": 360, "night": 480, "stadium": 420, "lava": 420}

    def __init__(self, biome, seed):
        self.biome = biome
        self.rng = random.Random(seed * 1013 + 7)
        self.hazards = []
        self.next_power = 240 + self.rng.randint(0, 120)    # first power a few seconds in
        self.blackout = (0, 0)                              # (flicker from, dark until)
        self.aura_on = False                                # player inside the boss's aura now
        self._boss_air = 0

    # -- before the player moves: auras that change how the bike rides --------------
    def player_mods(self, race, boss):
        b = race.bike
        b.land_mult, b.heat_aura = 1.0, 0.0
        self.aura_on = False
        if boss.state != "ride" or b.state != "ride":
            return
        dx = b.x - boss.x
        if self.biome == "night" and abs(dx) < 3 * TILE:
            b.land_mult = 0.7                                # Hex
            self.aura_on = True
        elif self.biome == "lava" and abs(dx) < 2 * TILE:
            b.heat_aura = 0.08                               # Heat Wave
            self.aura_on = True
        elif self.biome == "desert" and 0 < dx < 3 * TILE and abs(b.lane_index - boss.lane_index) <= 1 \
                and not b.airborne:
            b.heat_aura = -0.12                              # Sandblast (it's right behind you)
            self.aura_on = True

    # -- after everyone moved: spawn and resolve powers; returns events -------------
    def update(self, race, boss, player_ev, boss_ev):
        t, b = race.time_ticks, race.bike
        out = []
        if t >= self.next_power and boss.state == "ride" and abs(b.x - boss.x) < 8 * TILE \
                and not race.finished:
            out += self._fire(race, t)
            self.next_power = t + self.COOLDOWN[self.biome] + self.rng.randint(-60, 60)
        for hz in self.hazards:
            hz.step(t)
            if hz.live(t) and not hz.used and hz.touches(b, low_air=30 if hz.kind == "pyro" else 0):
                out += self._hit(hz, b, out)
        self.hazards = [hz for hz in self.hazards if not hz.done(t)]
        landed = any(e[0] in ("land", "perfect", "rough") for e in boss_ev)
        if self.biome == "valley" and landed and self._boss_air >= 20:
            if abs(b.x - boss.x) < 2 * TILE and not b.airborne and b.state == "ride":
                b.wobble = max(b.wobble, 18)                 # Quake
                b.speed *= 0.85
                out.append(("boss", "quake"))
        self._boss_air = boss.air_ticks if boss.airborne else 0
        if self.biome == "stadium":                          # Crowd Favourite
            if any(e[0] == "perfect" for e in boss_ev):
                boss.speed += 6
                out.append(("boss", "crowd_boss"))
            if any(e[0] == "perfect" for e in player_ev) and abs(b.x - boss.x) < 5 * TILE:
                b.speed += 5
                out.append(("boss", "crowd_you"))
        return out

    def mud_under(self, bike, t):
        """A live mud bomb under the player this tick (rides like a mud patch)."""
        return any(hz.kind == "mud" and hz.live(t) and hz.touches(bike) for hz in self.hazards)

    def _fire(self, race, t):
        b, r = race.bike, self.rng
        if self.biome == "valley":
            self.hazards.append(Hazard("mud", b.x + 3 * TILE, b.lane_index, t, 50, 180))
            return [("boss", "bomb")]
        if self.biome == "desert":
            self.hazards.append(Hazard("devil", b.x + 4 * TILE, r.randrange(C.LANES), t, 30, 240, r))
            return [("boss", "devil")]
        if self.biome == "night":
            self.blackout = (t, t + BLACKOUT_FLICKER + BLACKOUT_DARK)
            return [("boss", "blackout")]
        if self.biome == "stadium":
            lanes = {b.lane_index if r.random() < 0.6 else r.randrange(C.LANES), r.randrange(C.LANES)}
            for lane in sorted(lanes):
                self.hazards.append(Hazard("pyro", b.x + 4 * TILE, lane, t, 45, 50))
            return [("boss", "pyro")]
        self.hazards.append(Hazard("lava", b.x + 3.5 * TILE, b.lane_index, t, 50, 150))
        return [("boss", "eruption")]

    def _hit(self, hz, b, ev):
        if hz.kind == "mud":
            return []                                        # handled as a mud patch (mud_under)
        hz.used = True
        if hz.kind == "devil":
            down = hz.dir > 0 if 0 < b.lane_index < C.LANES - 1 else b.lane_index == 0
            b.lane = max(0, min(C.LANES - 1, b.lane_index + (1 if down else -1)))
            b.speed *= 0.85
            b.wobble = max(b.wobble, 10)
            return [("boss", "shoved")]
        if hz.kind == "pyro":
            b.external_heat(2 * C.HEAT_BAR, ev)
            return [("boss", "scorched")]
        b.speed += C.LAVA_PIT_SPEED                          # lava: a kick of speed, a lot of heat
        b.external_heat(C.LAVA_PIT_HEAT, ev)
        return [("boss", "lava")]

    def dark(self, t):
        """0 (normal) .. 1 (blackout) for the screen, with a flicker warning first."""
        start, until = self.blackout
        if not start <= t < until:
            return 0.0
        if t < start + BLACKOUT_FLICKER:
            return 0.85 if (t - start) // 6 % 2 else 0.0
        return 1.0
