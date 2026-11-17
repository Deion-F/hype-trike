"""Biome bosses: a giant rig you chase down and wreck.

A boss race is a chase, not a race to a line. The boss is a huge vehicle that
fills all four lanes (BossChase.x is its rear; RIG_LEN long), so you can never
pass it. You see it at the start, it roars off, and you have to catch it on
normal track. Fall LOSE_GAP behind and it gets away (you lose). Catch it and
hit its weak point HP times to wreck it (you win).

The boss lays the track as it goes (Paver): each column appears under its body,
so everything behind it is track it laid and ahead of it is bare ground. While you're far behind it lays normal
track: whole segments copied from the race's generated, validated track (the
"reel"). Once you're close (engaged) it lays its own themed pieces, from
PIECES: obstacles that make driving harder, and every so often a helper
piece that sets up its weak point. When the helper is behind it, it brakes for
a short window, so a good approach lands the hit.

Weak points (BOSSES[...]["weak"]), each testing a skill the run has taught:
  hatch      Mud Baron     ram the hatch in its lane while the shield is lifted (lane + timing)
  roof       Dune Raider   ram it high in the air, above the line (it lays big ramps)
  soul       Phantom       every lane's lantern burns alike (decoys) until it douses its lights;
                           ram the one still burning in the dark (timing + lane in the dark;
                           after the first hit it hops lanes once mid-dark)
  spotlight  Showstopper   land a PERFECT, then ram it while the spotlight's on you
  core       Inferno       ram it while overheating (heat)
Ramming it anywhere else bonks you back with a speed loss. A hit makes it surge
away and throw out more minions, so each hit is a fresh chase.

Minions: the boss drops crew riders behind it (and a few line up with you at
the start). They are slower than you and leave a weak trail of the boss's kind;
ride into one from behind in its lane and you're bumped back, so pass them in
another lane or jump them.

Everything is seeded from the race seed and driven by the race state, so
replays re-simulate exactly. Trail kinds (bike.Bike reacts; k = strength):
  mud    caps your speed            sand   your heat builds slower
  oil    you wobble (no accel)      smoke  cools your heat (classic: drag)
  fire   heats you fast
"""
import random
from collections import deque

import config as C

TILE = C.TILE_W

BOSSES = {
    "valley": dict(
        pace=0.985,
        name="MUD BARON", rig="Mud Hauler", weak="hatch", trail="mud", boost="toxic", glow=(150, 200, 60),
        body=(112, 92, 58), dark=(58, 46, 32), trim=(150, 200, 60), attack="mud",
        intro=[("Weak point", "the glowing hatch on its tailgate: get in that lane, ram it when the shield lifts"),
               ("Lays", "mud, ramps and muddy mesas; a clear lane to its hatch"),
               ("Attack", "Mud Bomb: mud lobbed into your lane (watch the shadow)")]),
    "desert": dict(
        pace=0.965,
        name="DUNE RAIDER", rig="Sand Crawler", weak="roof", trail="sand", boost="gold", glow=(255, 200, 90),
        body=(214, 176, 112), dark=(120, 92, 58), trim=(255, 200, 90), attack="devil",
        intro=[("Weak point", "the vent up top: fly off its ramps and hit it above the line"),
               ("Lays", "big ramps, dunes, sand and barriers"),
               ("Attack", "Dust Devil: a whirlwind hops lanes and shoves you aside")]),
    "night": dict(
        pace=0.985,
        name="PHANTOM", rig="Ghost Train", weak="soul", trail="oil", boost="plasma", glow=(170, 90, 255),
        body=(40, 34, 62), dark=(20, 16, 32), trim=(170, 90, 255), attack="wisp",
        intro=[("Weak point", "its lanterns are decoys until it douses the lights: ram the one still burning"),
               ("Lays", "split bridges, broken spans and a dark straight before each lights-out"),
               ("Attack", "Wisps: ghost lights rise in your lane and the next; touch one and you go cold")]),
    "stadium": dict(
        pace=0.98,
        name="SHOWSTOPPER", rig="Parade Float", weak="spotlight", trail="smoke", boost="neon",
        glow=(255, 215, 60), body=(190, 40, 60), dark=(90, 20, 36), trim=(255, 215, 60), attack="pyro",
        intro=[("Weak point", "land a PERFECT, then ram it while the spotlight's on you"),
               ("Lays", "fins, tabletops and step-ups to land on"),
               ("Attack", "Pyro Cannons: fire jets on marked lanes add heat")]),
    "lava": dict(
        pace=0.935,
        name="INFERNO", rig="Magma Tanker", weak="core", trail="fire", boost="flame", glow=(255, 90, 30),
        body=(70, 30, 26), dark=(34, 16, 14), trim=(255, 90, 30), attack="lava",
        intro=[("Weak point", "its core only cracks if you ram it OVERHEATING"),
               ("Lays", "lava pits to heat you up, canyons and barriers"),
               ("Attack", "Eruption: lava bursts in your lane")]),
}

# -- the rig -------------------------------------------------------------------------
RIG_LEN = int(2.6 * TILE)       # px, rear to front
HP = 3                          # weak-point hits to wreck it
START_GAP = 2.2 * TILE          # rig rear this far ahead of the start line
INTRO_TICKS = 240               # it roars off at INTRO_SPEED this long after GO
INTRO_SPEED = 64                # (and after a bonk): well clear of any bike
# Cruising speed = BOSSES[...]["pace"] x your vehicle's stock warm-band top speed
# (max_speed_b before upgrades), so it suits each vehicle and upgrades help. The paces sit between what a rider averages over that
# biome's track riding hot and riding overheating (measured: jumps, landings and
# mud cost a lot of top speed), so up close the warm band loses ground and only
# overheating (or its braking windows) reels it in.
ENGAGE_GAP = 6 * TILE           # rear within this of you: engaged (themed track, attacks, windows)
DISENGAGE_GAP = 9 * TILE        # ... until it's this far ahead again
ENGAGED_DROP = 0                # speed it gives up while engaged
FAR_FROM, FAR_SPAN, FAR_SLOW = 7 * TILE, 10 * TILE, 6     # far ahead: it eases off up to FAR_SLOW ...
# (a warm-band rider settles ~12 sections back: you have to ride hot to close in)
VFAR_FROM, VFAR_SPAN, VFAR_SLOW = 16 * TILE, 14 * TILE, 8  # ... and much more when very far (after a crash)
WARN_GAP = 30 * TILE            # "escaping!" warning from here
LOSE_GAP = 40 * TILE            # ... and it's gone at this gap
MAX_TICKS = 60 * 240            # it gets away after 4 minutes whatever happens
SPEED_UP, SPEED_DOWN = 0.5, 1.0 # its speed change per tick
INTRO_SPEED_UP = 1.5            # ... flooring it off the line
SURGE_TICKS, SURGE_EXTRA = 240, 16     # after a hit it surges away this long, this much faster
WINDOW_EVERY = 330              # engaged ticks between helper pieces
WINDOW_TICKS = 150              # braking window once a helper is behind it ...
WINDOW_K = 0.4                  # ... at this share of its cruising speed
SHIELD_WARN = 40                # hatch shield: first ticks of a window it only flashes
RECOVER_TICKS = 180             # you crashed / stalled: it holds back until this long after you ride again ...
RECOVER_K = 0.55                # ... at this share of its cruising speed (once it's off screen)
DOUSE_WARN = 45                 # soul: its lights flicker this long before they die (window's first ticks)
SOUL_HOP_HP = 2                 # ... from this many hits left, the soul hops lanes once mid-dark ...
SOUL_HOP_WARN = 30              # ... and its next lane blinks this long first
SPOT_TICKS = 240                # spotlight lasts this long after a PERFECT
ROOF_MIN = 14                   # roof: at least this high above the ground when you hit
CONTACT = 14                    # px behind its rear where you touch it
BONK_PUSH, BONK_KEEP = 26, 0.7  # a bonk throws you back this far, keeping this much speed ...
FLEE_GAP = 7 * TILE             # ... and it floors it like at the start until it's this far ahead
FLEE_MAX = 240                  # ... (at most this long), giving you time to build speed again
HIT_PUSH = 40
ATTACK_EVERY = {"mud": 300, "devil": 360, "wisp": 360, "pyro": 420, "lava": 400}

# -- minions --------------------------------------------------------------------------
MINION_EVERY = 420              # ticks between drops (+/- 90)
MINION_MAX = 3                  # riding at once
MINION_DESPAWN = 1400           # px behind you: gone
MINION_K = 0.4                  # their trail strength ...
MINION_LIFE = 30                # ... and how long a trail point lasts
MINION_BUMP = 20                # px: ride into one from behind and you're stopped here
TRAIL_EVERY = 3                 # ticks between trail points
TRAIL_LIFE = 150                # (default trail point life)
TRAIL_REACH = 12                # px either side of a point that counts as "in it"
TRAIL_HEAT = {"fire": 0.32, "smoke": -0.3}      # heat per tick in the trail (x strength)
TRAIL_DRAG_EVERY = 6                            # classic smoke: -1 speed this often
WISP_CHILL = 2.5                                # wisp: heat bars it takes ...
WISP_KEEP = 0.85                                # ... and the speed you keep

PAD = 12                        # flat columns kept beyond the laid track


def cruise_speed(biome, vehicle):
    """Its cruising speed: a share of your vehicle's stock warm top speed (upgrades
    don't speed it up, so they help you catch it)."""
    from bike import base_stats
    return BOSSES[biome]["pace"] * base_stats(vehicle).max_speed_b


def minion_setup(level):
    """(stats tweaks, GhostAI settings, (keep, band) heat plan) for a minion: never
    boosts and tops out well under you, so you can always pass it."""
    lv = max(0.0, min(1.0, level))
    stats = dict(max_speed_a=36 + 4 * lv, max_speed_b=37 + 4 * lv, accel_interval=C.ACCEL_INTERVAL + 0.5)
    ai = dict(turbo=False, turbo_temp=C.ONE_BOOST_AT - 0.2, skill=0.5 + 0.4 * lv, blunder=0.05, miss=0.2)
    return stats, ai, (C.ONE_BOOST_AT - 0.2, 0.5)


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
    """A boss attack on the track: warns first, then is live in one lane.
    kind: mud | devil (hops across lanes) | wisp | pyro | lava."""

    def __init__(self, kind, x, lane, start, warn, life, rng=None):
        self.kind, self.x, self.lane = kind, x, lane
        self.start, self.warn, self.life = start, warn, life
        self.dir = 1 if (rng and rng.random() < 0.5) else -1
        self.used = False          # one-shot hazards (devil, wisp, pyro, lava) hit once

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


# -- themed track pieces ------------------------------------------------------------------
class Piece:
    """A boss's own track piece. terrain: TERRAIN_CHARS string; hazards:
    (col offset, surface kind, lanes min, lanes max) like generator segments
    (one lane is always left free); material for every column; runway: clear
    columns it needs before it."""

    def __init__(self, terrain, hazards=(), material=None, runway=0, corridor=False):
        self.terrain, self.hazards, self.material = terrain, hazards, material
        self.runway, self.corridor = runway, corridor


def _pieces():
    from track.tiles import MUD, DEBRIS, WATER, PAD_S, PAD_L, COOLANT, SAND
    P = Piece
    return {
        "valley": dict(
            helper=[P("........", corridor=True)],     # mud in every lane but the hatch's, a pad in it
            obstacle=[P("......", ((1, MUD, 1, 2), (2, MUD, 1, 2), (3, MUD, 2, 3))),
                      P("..utttttd...", ((3, MUD, 1, 2), (5, MUD, 1, 2))),
                      P("....L.g....", ((0, MUD, 2, 3), (1, MUD, 2, 3)), runway=2),
                      P("..s...s...", ((4, MUD, 1, 2),))]),
        "desert": dict(
            helper=[P("....L.....", runway=2)],                       # a big ramp up to the roof vent
            obstacle=[P("..wwww...", material=SAND),
                      P("..utttd....", material=SAND),
                      P("......", ((2, DEBRIS, 1, 2), (4, DEBRIS, 1, 2)), material=SAND),
                      P("..L.gg.....", runway=4)]),
        "night": dict(
            helper=[P("..........")],                   # a clear straight to ride in the dark
            obstacle=[P("..obbbbbbe....", runway=3),
                      P("..oryyyZynbe....", runway=3),
                      P("..obbbbbKxbbbe....", runway=4),
                      P("........", ((1, DEBRIS, 1, 2), (4, DEBRIS, 1, 2), (7, DEBRIS, 1, 2)))]),
        "stadium": dict(
            helper=[P("..utttd.....", runway=2), P("..L.......", runway=2), P(".f.....f.....", runway=2)],
            obstacle=[P("..utttUTTDd...", runway=2),
                      P("..utkUTTDd....", runway=3),
                      P(".ff.....f......", runway=3),
                      P("..uUTDtUTDd....", runway=2)]),
        "lava": dict(
            helper=[P(".........", ((1, WATER, 1, 2), (3, WATER, 2, 3), (5, PAD_L, 1, 2), (6, PAD_S, 1, 2)))],
            obstacle=[P("..Lgg.....", runway=4),
                      P("..utttd.sg.....", runway=4),
                      P("......", ((1, DEBRIS, 1, 2), (3, WATER, 1, 2))),
                      P("..s...s...", ((2, WATER, 1, 2),))]),
    }


PIECES = None


def pieces(biome):
    global PIECES
    if PIECES is None:
        PIECES = _pieces()
    return PIECES[biome]


class Paver:
    """Lays the live track one column at a time as the rig's front reaches it.
    Far from you: the reel (the race's generated track) looped end to end, each
    live column mapping to a fixed reel column, so every lap is the same layout.
    Engaged: the boss's themed pieces over it, and a helper piece when asked."""

    OPENING = 6                 # columns of the reel the race starts on (start line + runway)

    def __init__(self, reel, live, biome, rng):
        from track.tiles import TERRAIN_CHARS
        self.T = TERRAIN_CHARS
        self.reel, self.live, self.biome, self.rng = reel, live, biome, rng
        self.built = self.OPENING               # next live column to lay
        self.queue = deque()                    # columns waiting: (terrain, [surface per lane], material)
        self.runway = 4
        self.want_helper = False
        self.helper_end = None                  # live column just after the last helper laid ...
        self.helper_start = None                # ... and its first column
        self._last_rc = self.OPENING - 1        # reel column of the last column laid from the loop
        self.lantern = None                     # Mud Baron's corridor: the hatch lane it keeps clear
        self._last_obstacle = None
        self.reel_hoops = {}
        for hx, hh, hl in reel.hoops:
            self.reel_hoops.setdefault(int(hx // TILE), []).append((hx % TILE, hh, hl))

    @staticmethod
    def live_track(reel):
        """The track a chase starts on: the reel's opening columns, then flat."""
        from track.tiles import Track
        n = Paver.OPENING
        tr = Track(reel.terrain[:n], [list(l[:n]) for l in reel.surface], list(reel.material[:n]), laps=1,
                   name=reel.name, theme=reel.theme,
                   meta={k: v for k, v in reel.meta.items() if k not in ("hoops", "segments")})
        tr.meta["hoops"] = [h for h in reel.hoops if h[0] < n * TILE]
        tr.append_flat(PAD + 8)
        return tr

    def lay_until(self, x, engaged):
        """Lay columns until the live track is built past x."""
        while self.built * TILE < x:
            if not self.queue:
                self._plan(engaged)
            terrain, surf, mat = self.queue.popleft()
            if self.live.ncols < self.built + PAD:
                self.live.append_flat(PAD)
            self.live.set_column(self.built, terrain, surf, mat)
            self.built += 1

    # -- planning ---------------------------------------------------------------------------
    def _plan(self, engaged):
        if self.want_helper:
            self.want_helper = False
            piece = self.rng.choice(pieces(self.biome)["helper"])
            if piece.runway > self.runway:          # (its run-up columns aren't the helper)
                self._themed(Piece("." * (piece.runway - self.runway)))
            self.helper_start = self.built + len(self.queue)
            self._themed(piece)
            self.helper_end = self.built + len(self.queue)
        elif engaged:
            if self.rng.random() < 0.3:
                self._themed(Piece("...."))
            else:
                opts = [p for p in pieces(self.biome)["obstacle"] if p is not self._last_obstacle]
                self._last_obstacle = p = self.rng.choice(opts)
                self._themed(p)
        else:
            self._from_reel()

    def _themed(self, piece):
        from track.tiles import NONE, DIRT, MUD, PAD_S, PADS
        if piece.runway > self.runway:
            self._push([("." , [NONE] * C.LANES, DIRT)] * (piece.runway - self.runway))
        cols = []
        for ch in piece.terrain:
            cols.append([ch, [NONE] * C.LANES, piece.material if piece.material is not None else DIRT])
        for off, kind, lo, hi in piece.hazards:
            k = self.rng.randint(lo, min(hi, C.LANES - 1))      # always leave a lane free
            for lane in self.rng.sample(range(C.LANES), k):
                cols[off][1][lane] = kind
        if piece.corridor and self.lantern is not None:
            for lane in range(C.LANES):
                if lane != self.lantern:
                    cols[2][1][lane] = cols[3][1][lane] = MUD
            cols[5][1][self.lantern] = PAD_S
        self._push([(c, s, m) for c, s, m in cols])
        self._runway_after(cols, lambda c: c[0] == "." and not any(x not in (NONE,) + PADS for x in c[1]))

    def _push(self, cols):
        self._last_rc = None                    # anything but the loop breaks its run
        for ch, surf, mat in cols:
            self.queue.append((self.T[ch] if isinstance(ch, str) else ch, list(surf), mat))

    def _runway_after(self, cols, clear):
        tail = 0
        for c in reversed(cols):
            if not clear(c):
                break
            tail += 1
        self.runway = tail if tail < len(cols) else self.runway + tail

    def reel_col(self, col):
        """The reel column a live column maps to: the live track is the reel looped
        end to end, so every lap has the same layout wherever the boss left it alone."""
        return col % self.reel.ncols

    def _seg_start(self, rc):
        """Does a reel segment (a whole generator piece) start at reel column rc?"""
        from track.tiles import edge_heights
        reel = self.reel
        if rc == 0:
            return True
        if edge_heights(reel.terrain[rc - 1])[1] != 0 or edge_heights(reel.terrain[rc])[0] != 0:
            return False
        segs = reel.meta.get("segments") or []
        if rc < len(segs):
            return segs[rc] != segs[rc - 1]
        return rc % 4 == 0                                # no names (hand-made tracks): every 4

    def _from_reel(self):
        """The reel's segment at this spot of the loop. Back from the boss's own
        pieces mid-segment: flat ground until the next segment starts (never half a
        structure)."""
        from track.tiles import FLAT, NONE, PADS, DIRT
        reel = self.reel
        rc = self.reel_col(self.built + len(self.queue))
        going = self._last_rc is not None and (self._last_rc + 1) % reel.ncols == rc
        if not self._seg_start(rc) and not going:
            self._push([(".", [NONE] * C.LANES, DIRT)])
            self.runway += 1
            return
        cols = [rc]
        c = rc + 1
        while c < reel.ncols and not self._seg_start(c):
            cols.append(c)
            c += 1
        self._last_rc = cols[-1]
        hoops = self.live.meta.setdefault("hoops", [])
        for rc in cols:
            col = self.built + len(self.queue)
            for lx, hh, hl in self.reel_hoops.get(rc, ()):
                hoops.append((round(col * TILE + lx, 1), hh, hl))
            self.queue.append((reel.terrain[rc], [reel.surface[l][rc] for l in range(C.LANES)],
                               reel.material[rc]))
        out = [(reel.terrain[rc], [reel.surface[l][rc] for l in range(C.LANES)]) for rc in cols]
        self._runway_after(out, lambda c: c[0] == FLAT and not any(x not in (NONE,) + PADS for x in c[1]))


# -- the chase --------------------------------------------------------------------------------
class BossChase:
    """The boss of one chase race: the rig's motion, its track laying, weak point,
    minions and attacks. Race.step calls before() ahead of the player's step and
    after() once everyone has moved. outcome: None, "won" or "escaped"."""

    def __init__(self, race, biome, reel, seed, level):
        self.biome = biome
        self.info = BOSSES[biome]
        self.weak = self.info["weak"]
        self.rng = random.Random(seed * 1013 + 7)
        self.cruise = cruise_speed(biome, race.bike.stats.vehicle)
        self.x = C.START_X + START_GAP          # rear of the rig
        self.speed = 0.0
        self.hp = HP
        self.hits = 0
        self.bonks = 0
        self.engaged = False
        self.outcome = None
        self.wrecked_at = None
        self.max_gap = 0.0
        self.surge_until = 0
        self.flee_until = 0                     # after a bonk: roaring off at INTRO_SPEED
        self.recover_until = 0                  # you crashed: it holds back till then
        self.window_from = self.window_until = 0
        self.next_window = INTRO_TICKS + 240
        self.next_minion = INTRO_TICKS + 120 + self.rng.randint(0, 90)
        self.next_attack = INTRO_TICKS + 300
        self.lantern = self.rng.randrange(C.LANES)
        self.lantern_next = None                # soul: the lane it's about to hop to (blinks)
        self.hop_at = None                      # ... and when
        self.spot_until = 0
        self.flash_at = -99                     # last hit (renderer flash)
        self.bonk_at = -99
        self._warned = False
        self.lap = 1                            # laps of the looped track you're on
        self.hazards = []                       # live attacks (Hazard)
        self.paver = Paver(reel, race.track, biome, self.rng)
        self.paver.lay_until(self.front - TILE, False)

    @property
    def front(self):
        return self.x + RIG_LEN

    # -- what the renderer / HUD read -------------------------------------------------------
    def window_warn(self):
        """Ticks at the start of a window before the weak point opens."""
        return {"hatch": SHIELD_WARN, "soul": DOUSE_WARN}.get(self.weak, 0)

    def shield(self, t):
        """Hatch shield / Phantom's lights: "closed", "warn" (about to lift / flickering)
        or "open" (lifted / dark)."""
        if self.window_from <= t < self.window_until:
            return "warn" if t < self.window_from + self.window_warn() else "open"
        return "closed"

    def in_window(self, t):
        return self.window_from <= t < self.window_until

    def spotlit(self, t):
        return t < self.spot_until

    def gap(self, bike):
        return self.x - bike.x

    def dark(self, t):
        """0 (normal) .. 1 (lights out) for the screen: the Phantom douses its lights
        for each braking window, flickering first."""
        if self.weak != "soul" or self.outcome is not None:
            return 0.0
        state = self.shield(t)
        if state == "warn":
            return 0.85 if (t - self.window_from) // 6 % 2 else 0.0
        return 1.0 if state == "open" else 0.0

    def weak_open(self, bike, t):
        """Would ramming the rig right now hit its weak point?"""
        w = self.weak
        if w == "roof":
            return bike.airborne and bike.h - bike.track.ground(bike.x, bike.lane_index) >= ROOF_MIN
        if w in ("hatch", "soul"):
            return bike.lane_index == self.lantern and self.shield(t) == "open"
        if w == "spotlight":
            return self.spotlit(t)
        return bike.heat_zone() == 3 if bike.one_button else bike.temp >= C.RED_AT

    def mud_under(self, bike, t):
        """A live mud bomb under the player this tick (rides like a mud patch)."""
        return any(hz.kind == "mud" and hz.live(t) and hz.touches(bike) for hz in self.hazards)

    # -- each tick ---------------------------------------------------------------------------
    def before(self, race):
        """Before the player moves: which trail / mud bomb they're riding in."""
        b = race.bike
        hit = [tr for tr in race.trails if tr.hits(b)]
        if self.mud_under(b, race.time_ticks):
            b.trail, b.trail_k = "mud", 1.0
        elif hit:
            strongest = max(hit, key=lambda tr: tr.k)
            b.trail, b.trail_k = strongest.kind, strongest.k
        else:
            b.trail, b.trail_k = None, 1.0

    def after(self, race, player_ev):
        """After everyone moved: drive the rig, lay track, resolve contact, minions,
        attacks, and the win / escape checks. Returns the player's new events."""
        t, b = race.time_ticks, race.bike
        out = []
        if any(e[0] == "perfect" for e in player_ev) and self.weak == "spotlight" and not self.outcome:
            self.spot_until = t + SPOT_TICKS
            out.append(("boss", "spotlight"))
        if b.state in ("crash", "overheat"):
            self.recover_until = t + RECOVER_TICKS
        gap = self.gap(b)
        if self.engaged and gap > DISENGAGE_GAP:
            self.engaged = False
        elif not self.engaged and gap < ENGAGE_GAP and t > INTRO_TICKS:
            self.engaged = True
        self._drive(t, gap)
        self.paver.lay_until(self.front - TILE, self.engaged)     # only ever under its body
        if self.outcome is None:
            self._windows(t, out)
            self._soul(t, out)
            self._contact(race, t, out)
            self._minions(race, t, out)
            self._attacks(race, t, out)
        else:
            if b.x > self.x - CONTACT:
                b.x = self.x - CONTACT
                b.speed = min(b.speed, self.speed)
        for tr in race.trails:
            tr.update(race.rivals[tr.owner], t)
        lap = int(b.x // (self.paver.reel.ncols * TILE)) + 1
        if lap > self.lap:
            self.lap = lap
            out.append(("boss", "lap", lap))
        gap = self.gap(b)
        self.max_gap = max(self.max_gap, gap)
        if self.outcome is None:
            if gap > WARN_GAP and not self._warned:
                self._warned = True
                out.append(("boss", "escaping"))
            elif gap < WARN_GAP - 2 * TILE:
                self._warned = False
            if gap > LOSE_GAP or t >= MAX_TICKS:
                self.outcome = "escaped"
                out.append(("boss", "escaped"))
        return out

    def _drive(self, t, gap):
        if t < self.flee_until and gap >= FLEE_GAP:
            self.flee_until = self.surge_until = t                  # out of sight: back to cruising
        if self.outcome == "won":
            target = 0.0
        elif self.outcome == "escaped":
            target = self.cruise + SURGE_EXTRA
        elif (t <= INTRO_TICKS or t < self.flee_until) and gap < FLEE_GAP:
            target = INTRO_SPEED
        elif t < self.surge_until:
            target = self.cruise + SURGE_EXTRA
        elif self.in_window(t):
            target = self.cruise * WINDOW_K
        else:
            far = max(0.0, min(1.0, (gap - FAR_FROM) / FAR_SPAN))
            vfar = max(0.0, min(1.0, (gap - VFAR_FROM) / VFAR_SPAN))
            target = self.cruise - (ENGAGED_DROP if self.engaged else 0) - FAR_SLOW * far - VFAR_SLOW * vfar
        if t < self.recover_until and self.outcome is None and gap >= FLEE_GAP:
            target = min(target, self.cruise * RECOVER_K)       # you're down: it doesn't run away
        if self.speed < target:
            fast = t <= INTRO_TICKS or t < self.flee_until
            self.speed = min(target, self.speed + (INTRO_SPEED_UP if fast else SPEED_UP))
        else:
            self.speed = max(target, self.speed - SPEED_DOWN)
        self.x += self.speed * C.SPEED_TO_PX

    def _windows(self, t, out):
        """Helper pieces and the braking window that follows each one."""
        pv = self.paver
        if self.engaged and t >= self.next_window and not pv.want_helper and pv.helper_end is None \
                and t >= self.surge_until:
            pv.want_helper = True
            if self.weak == "hatch":                      # a new hatch lights up for each window
                self.lantern = self.rng.choice([l for l in range(C.LANES) if l != self.lantern])
                out.append(("boss", "hatch"))
            pv.lantern = self.lantern
        # It brakes as the helper starts to show behind it, so the helper leads into it.
        if pv.helper_end is not None and self.x >= (pv.helper_start + 1) * TILE:
            pv.helper_end = None
            if self.engaged:
                self.window_from, self.window_until = t, t + WINDOW_TICKS + self.window_warn()
                if self.weak == "soul":                   # lights out: a new soul lantern, hidden till now
                    self.lantern = self.rng.choice([l for l in range(C.LANES) if l != self.lantern])
                    self.lantern_next = None
                    hop = self.hp <= SOUL_HOP_HP
                    self.hop_at = t + DOUSE_WARN + WINDOW_TICKS // 2 if hop else None
                    out.append(("boss", "douse"))
                else:
                    out.append(("boss", "window"))
            self.next_window = t + WINDOW_EVERY

    def _soul(self, t, out):
        """Phantom: from SOUL_HOP_HP hits left, the soul hops lanes once mid-dark,
        its next lane blinking first."""
        if self.hop_at is None:
            return
        if not self.in_window(t):
            self.hop_at, self.lantern_next = None, None
            return
        if self.lantern_next is None and t >= self.hop_at - SOUL_HOP_WARN:
            near = [l for l in (self.lantern - 1, self.lantern + 1) if 0 <= l < C.LANES]
            self.lantern_next = self.rng.choice(near)
        if t >= self.hop_at and self.lantern_next is not None:
            self.lantern, self.lantern_next, self.hop_at = self.lantern_next, None, None
            out.append(("boss", "soul_hop"))

    def _contact(self, race, t, out):
        b = race.bike
        if b.x <= self.x - CONTACT:
            return
        if b.state != "ride":                    # crashed / stalled into it: just stop there
            b.x = self.x - CONTACT
            b.speed = min(b.speed, self.speed)
            return
        if self.weak_open(b, t):
            self.hp -= 1
            self.hits += 1
            self.flash_at = t
            self.spot_until = 0
            b.x = self.x - HIT_PUSH
            b.speed = min(b.speed, self.speed)
            out.append(("boss", "hit", self.hp))
            self.window_until = t
            if self.hp <= 0:
                self.outcome = "won"
                self.wrecked_at = t
                out.append(("boss", "wrecked"))
                return
            self.flee_until = 0
            self.surge_until = t + SURGE_TICKS
            self.next_window = t + SURGE_TICKS + WINDOW_EVERY // 2
            self.paver.want_helper = False
            for lane in self.rng.sample([l for l in range(C.LANES) if l != b.lane_index], 2):
                self._drop(race, lane, out)
            return
        self.bonks += 1
        b.x = self.x - BONK_PUSH
        b.speed = min(b.speed, self.speed) * BONK_KEEP
        b.wobble = max(b.wobble, 14)
        if t - self.bonk_at > 40:
            hint = self.weak
            if hint == "hatch":
                hint = "hatch_lane" if b.lane_index != self.lantern else "hatch_shut"
            elif hint == "soul":                        # lights on: decoys; dark: wrong lane
                hint = "soul_lane" if self.shield(t) == "open" else "soul_shut"
            out.append(("boss", "bonk", hint))
        self.bonk_at = t
        # It roars off out of sight, like at the start: chase it down again.
        self.flee_until = t + FLEE_MAX
        self.surge_until = max(self.surge_until, self.flee_until)   # no windows or attacks meanwhile
        self.window_until = min(self.window_until, t)
        self.next_window = max(self.next_window, self.flee_until + WINDOW_EVERY // 2)

    def _minions(self, race, t, out):
        b = race.bike
        alive = 0
        for m in race.rivals:
            if m.state == "gone":
                continue
            if m.x < b.x - MINION_DESPAWN or m.x > self.x - 8:       # left behind / caught the rig
                m.state = "gone"
                continue
            alive += 1
            if (b.state == "ride" and m.state == "ride" and not b.airborne and not m.airborne
                    and abs(m.lane_pos - b.lane_pos) < 0.5 and 0 < m.x - b.x < MINION_BUMP
                    and b.speed > m.speed):
                b.x = m.x - MINION_BUMP
                b.speed = max(0.0, min(b.speed, m.speed) * 0.85)
                b.wobble = max(b.wobble, 10)
                out.append(("boss", "minion_bump"))
        if t >= self.next_minion and alive < MINION_MAX and not self.in_window(t):
            lanes = list(range(C.LANES))
            if self.gap(b) < 3 * TILE:
                lanes.remove(b.lane_index)               # never straight into your face
            self._drop(race, self.rng.choice(lanes), out)
            self.next_minion = t + MINION_EVERY + self.rng.randint(-90, 90)

    def _drop(self, race, lane, out):
        race.add_minion(lane, self.x - 24, min(self.speed, 40.0))
        out.append(("boss", "minion"))

    def _attacks(self, race, t, out):
        b, r = race.bike, self.rng
        if self.engaged and t >= self.next_attack and not self.in_window(t) and t >= self.surge_until:
            kind = self.info["attack"]
            if kind == "mud":
                self.hazards.append(Hazard("mud", b.x + 3 * TILE, b.lane_index, t, 50, 180))
                out.append(("boss", "bomb"))
            elif kind == "devil":
                self.hazards.append(Hazard("devil", b.x + 4 * TILE, r.randrange(C.LANES), t, 30, 240, r))
                out.append(("boss", "devil"))
            elif kind == "wisp":                      # your lane and one beside it
                near = [l for l in (b.lane_index - 1, b.lane_index + 1) if 0 <= l < C.LANES]
                for lane in sorted({b.lane_index, r.choice(near)}):
                    self.hazards.append(Hazard("wisp", b.x + 4.5 * TILE, lane, t, 45, 120))
                out.append(("boss", "wisp"))
            elif kind == "pyro":
                lanes = {b.lane_index if r.random() < 0.6 else r.randrange(C.LANES), r.randrange(C.LANES)}
                for lane in sorted(lanes):
                    self.hazards.append(Hazard("pyro", b.x + 4 * TILE, lane, t, 45, 50))
                out.append(("boss", "pyro"))
            else:
                self.hazards.append(Hazard("lava", b.x + 3.5 * TILE, b.lane_index, t, 50, 150))
                out.append(("boss", "eruption"))
            self.next_attack = t + ATTACK_EVERY[kind] + r.randint(-60, 60)
        for hz in self.hazards:
            hz.step(t)
            if hz.live(t) and not hz.used and hz.touches(b, low_air=30 if hz.kind in ("pyro", "wisp") else 0):
                out += self._hazard_hit(hz, b, out)
        self.hazards = [hz for hz in self.hazards if not hz.done(t)]

    @staticmethod
    def _hazard_hit(hz, b, ev):
        if hz.kind == "mud":
            return []                                        # handled as a mud patch (mud_under)
        hz.used = True
        if hz.kind == "devil":
            down = hz.dir > 0 if 0 < b.lane_index < C.LANES - 1 else b.lane_index == 0
            b.lane = max(0, min(C.LANES - 1, b.lane_index + (1 if down else -1)))
            b.speed *= 0.85
            b.wobble = max(b.wobble, 10)
            return [("boss", "shoved")]
        if hz.kind == "wisp":                                 # a ghost's chill: heat and speed
            b.external_heat(-WISP_CHILL * C.HEAT_BAR, ev)
            b.speed *= WISP_KEEP
            b.wobble = max(b.wobble, 8)
            return [("boss", "chilled")]
        if hz.kind == "pyro":
            b.external_heat(2 * C.HEAT_BAR, ev)
            return [("boss", "scorched")]
        b.speed += C.LAVA_PIT_SPEED                          # lava: a kick of speed, a lot of heat
        b.external_heat(C.LAVA_PIT_HEAT, ev)
        return [("boss", "lava")]


def hunter_controls(race, c):
    """Boss sense for AI players (sims, tests): steer to the lit hatch / the soul
    lantern once it's dark, hang back while the shield is shut or the lights are on,
    ride overheating into the Inferno. Rides the
    ordinary AI's controls otherwise."""
    ch = race.chase
    if ch is None or ch.outcome:
        return c
    b, t = race.bike, race.time_ticks
    if b.state != "ride":
        return c
    if not b.airborne and not (c.lane_up or c.lane_down):     # swing out round a minion ahead
        ahead = [m for m in race.rivals if m.state == "ride" and 0 < m.x - b.x < 1.6 * TILE]
        if any(abs(m.lane_pos - b.lane) < 0.5 for m in ahead) and b.speed > 20:
            busy = {m.lane_index for m in ahead}
            free = [l for l in (b.lane - 1, b.lane + 1) if 0 <= l < C.LANES and l not in busy]
            if free:
                c.lane_up, c.lane_down = free[0] < b.lane, free[0] > b.lane
    if ch.gap(b) > 5 * TILE or (ch.weak not in ("core", "hatch", "soul") and not ch.in_window(t)):
        if b.one_button and not b.airborne:                   # chasing: ride hot, it outruns the warm band
            c.a, c.b = b.temp < (C.ONE_OVERHEAT_AT + 0.5 if ch.gap(b) < 12 * TILE else C.ONE_HOT_AT + 3.5), False
        if ch.gap(b) > 5 * TILE:
            return c
    if not b.airborne and (ch.weak == "hatch" or (ch.weak == "soul" and ch.shield(t) == "open")):
        c.lane_up, c.lane_down = b.lane > ch.lantern, b.lane < ch.lantern
    if ch.weak in ("hatch", "soul") and ch.shield(t) != "open" and ch.gap(b) < 2.5 * TILE:
        c.a = c.b = False
    elif ch.weak == "core":
        if b.one_button:
            c.a, c.b = b.temp < C.TEMP_OVERHEAT - 4.5, False
        else:
            c.a, c.b = True, b.temp < C.TEMP_OVERHEAT - 2
    return c
