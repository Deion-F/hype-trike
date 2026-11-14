"""Tile vocabulary (spec §5.2), ground materials, and the Track model.

A track is a list of columns, each TILE_W pixels wide.
  * terrain[col]   - column-wide shape tile (flat, ramps, gap, whoops, start)
  * surface[l][col]- per-lane surface tile (coolant, mud, debris, water) or NONE
  * material[col]  - ground material (dirt, grass, sand) for vehicle grip
Height profiles are precomputed per pixel so physics lookups are cheap and the
simulation stays deterministic.
"""
import math

from config import TILE_W, LANES

# --- tile IDs (spec §5.2) ------------------------------------------------------
FLAT, RAMP_S, RAMP_L, COOLANT, MUD, DEBRIS, START, GAP, WHOOPS, WATER, PAD_S, PAD_L = range(12)
# Elevated structures (plateaus / step-ups / spikes). Unlike the ramps above,
# these carry height across column boundaries, so they must be chained so the
# exit height of one column matches the entry height of the next (see
# edge_heights). Two plateau levels: LO and HI.
UP_LO, TOP_LO, DOWN_LO, UP_HI, TOP_HI, DOWN_HI, KICK, FIN = range(12, 20)
# Raised decks on pillars (open underneath): a steep on-ramp, the deck, a
# descent off the end, a kicker on the deck, a broken span (a pit you must
# jump) and a drawbridge whose leaf lifts and lowers on a fixed cycle.
DECK_UP, DECK, DECK_DOWN, DECK_KICK, DECK_GAP, DRAW = range(20, 26)
# Skyway: a narrow high strip that only exists in the back lanes of a split
# column (never placed on its own): a ramp up from deck height, the strip,
# and a drop back down to deck height.
SKY_UP, SKY, SKY_DOWN = range(26, 29)
# Split columns: the back lanes (0 .. HIGH_LANES-1) ride one tile, the front
# lanes another. The split bridge: front lanes on the drawbridge deck, back
# lanes up on the skyway over it.
SPLIT_UP, SPLIT, SPLIT_DRAW, SPLIT_DOWN = range(29, 33)
SPLITS = {SPLIT_UP: (DECK, SKY_UP), SPLIT: (DECK, SKY), SPLIT_DRAW: (DRAW, SKY), SPLIT_DOWN: (DECK, SKY_DOWN)}
HIGH_LANES = 2
NONE = -1


def lane_tile(tile, lane):
    """The tile a lane actually rides: split columns differ between the back
    (high) lanes and the front lanes. lane None = the front lanes."""
    if tile in SPLITS:
        return SPLITS[tile][1 if lane is not None and lane < HIGH_LANES else 0]
    return tile

TILE_NAMES = {
    FLAT: "Flat", RAMP_S: "Ramp S", RAMP_L: "Ramp L", COOLANT: "Medium pad",
    MUD: "Mud", DEBRIS: "Debris", START: "Start", GAP: "Gap", WHOOPS: "Whoops",
    WATER: "Water",       # a lava pit on the Volcano theme
    PAD_S: "Small pad", PAD_L: "Large pad",
    UP_LO: "Rise", TOP_LO: "Mesa", DOWN_LO: "Descent", UP_HI: "Rise 2",
    TOP_HI: "High mesa", DOWN_HI: "Descent 2", KICK: "Mesa kicker", FIN: "Fin",
    DECK_UP: "Deck ramp", DECK: "Deck", DECK_DOWN: "Deck end", DECK_KICK: "Deck kicker",
    DECK_GAP: "Broken span", DRAW: "Drawbridge",
    SKY_UP: "Skyway ramp", SKY: "Skyway", SKY_DOWN: "Skyway drop",
    SPLIT_UP: "Split: deck / skyway ramp", SPLIT: "Split: deck / skyway",
    SPLIT_DRAW: "Split: drawbridge / skyway", SPLIT_DOWN: "Split: deck / skyway drop",
}
# Coolant / heat pads come in three sizes (COOLANT is the medium one). In
# one-button mode each adds this many heat bars; in classic mode any pad cools.
PAD_BARS = {PAD_S: 1, COOLANT: 2, PAD_L: 3}
PADS = tuple(PAD_BARS)
TERRAIN_TILES = (FLAT, RAMP_S, RAMP_L, START, GAP, WHOOPS,
                 UP_LO, TOP_LO, DOWN_LO, UP_HI, TOP_HI, DOWN_HI, KICK, FIN,
                 DECK_UP, DECK, DECK_DOWN, DECK_KICK, DECK_GAP, DRAW,
                 SPLIT_UP, SPLIT, SPLIT_DRAW, SPLIT_DOWN)
# Tiles you ride up and launch from (mouse-mode ramp lean, etc.).
RAMPS = (RAMP_S, RAMP_L, UP_LO, UP_HI, KICK, FIN, DECK_UP, DECK_KICK, SKY_UP)
# Holes you fall into (crash "pit"): the ground-level pit and the deck's broken span.
PITS = (GAP, DECK_GAP)
DECKS = (DECK_UP, DECK, DECK_DOWN, DECK_KICK, DECK_GAP, DRAW, SKY_UP, SKY, SKY_DOWN) + tuple(SPLITS)
SURFACE_TILES = (PAD_S, COOLANT, PAD_L, MUD, DEBRIS, WATER)

# --- ground materials ---------------------------------------------------------------
DIRT, GRASS, SAND = range(3)
MATERIAL_NAMES = {DIRT: "Dirt", GRASS: "Grass", SAND: "Sand"}
MATERIALS = (DIRT, GRASS, SAND)

# --- height profiles: polylines of (local_x, height) -----------------------------
PIT_DEPTH = -70
MESA_LO = 28
MESA_HI = 56
DECK_H = MESA_HI
SKY_H = DECK_H + 32


# Drawbridge cycle (ticks). The leaf is down (rideable) for most of the cycle,
# lifts, stays up (an open hole: fall in and you crash), then lowers again.
DRAW_PERIOD = 170
DRAW_MOVE = 24        # ticks to lift or lower the leaf
DRAW_UP = 24          # ticks fully up
DRAW_OPEN_AT = 0.45   # the hole counts as open while the leaf is lifted past this


def draw_lift(ticks, col):
    """0 (down) .. 1 (fully up) for the drawbridge in column `col` at race tick `ticks`.
    Each column runs its own phase so two bridges don't move in step."""
    t = (ticks + col * 53) % DRAW_PERIOD
    if t < DRAW_MOVE:
        return t / DRAW_MOVE
    t -= DRAW_MOVE
    if t < DRAW_UP:
        return 1.0
    t -= DRAW_UP
    if t < DRAW_MOVE:
        return 1.0 - t / DRAW_MOVE
    return 0.0


def draw_open(ticks, col):
    return draw_lift(ticks, col) > DRAW_OPEN_AT


def _whoops():
    pts = []
    for x in range(0, TILE_W + 1, 4):
        pts.append((x, 6 * (1 - math.cos(2 * math.pi * 2 * x / TILE_W)) / 2))
    return pts

PROFILES = {
    FLAT:   [(0, 0), (TILE_W, 0)],
    START:  [(0, 0), (TILE_W, 0)],
    RAMP_S: [(0, 0), (50, 22), (58, 22), (76, 0), (TILE_W, 0)],
    RAMP_L: [(0, 0), (54, 44), (62, 44), (78, 0), (TILE_W, 0)],
    GAP:    [(0, 0), (2, -70), (TILE_W - 2, -70), (TILE_W, 0)],
    WHOOPS: _whoops(),
    # Plateaus. Rises climb over most of the column; descents stay level for a
    # short lip, then slope down: at speed the bike flies off the lip and the
    # slope is the landing (match it for a PERFECT).
    UP_LO:   [(0, 0), (60, MESA_LO), (TILE_W, MESA_LO)],
    TOP_LO:  [(0, MESA_LO), (TILE_W, MESA_LO)],
    DOWN_LO: [(0, MESA_LO), (16, MESA_LO), (TILE_W, 0)],
    UP_HI:   [(0, MESA_LO), (60, MESA_HI), (TILE_W, MESA_HI)],
    TOP_HI:  [(0, MESA_HI), (TILE_W, MESA_HI)],
    DOWN_HI: [(0, MESA_HI), (16, MESA_HI), (TILE_W, MESA_LO)],
    # A small kicker sitting on a low plateau.
    KICK:    [(0, MESA_LO), (48, MESA_LO + 22), (56, MESA_LO + 22), (74, MESA_LO), (TILE_W, MESA_LO)],
    # A tall, steep spike: hit it with speed or get bucked.
    FIN:     [(0, 0), (44, 40), (50, 40), (TILE_W, 0)],
    # Decks: a steep (~38 deg) on-ramp that flings you up onto the deck, a
    # descent like the mesa ones, a kicker on the deck, and a broken span.
    DECK_UP:   [(0, 0), (72, DECK_H), (TILE_W, DECK_H)],
    DECK:      [(0, DECK_H), (TILE_W, DECK_H)],
    DECK_DOWN: [(0, DECK_H), (16, DECK_H), (TILE_W, 0)],
    DECK_KICK: [(0, DECK_H), (50, DECK_H + 15), (58, DECK_H + 15), (62, DECK_H), (TILE_W, DECK_H)],
    DECK_GAP:  [(0, DECK_H), (2, PIT_DEPTH), (TILE_W - 2, PIT_DEPTH), (TILE_W, DECK_H)],
    DRAW:      [(0, DECK_H), (TILE_W, DECK_H)],
    SKY_UP:    [(0, DECK_H), (60, SKY_H), (TILE_W, SKY_H)],
    SKY:       [(0, SKY_H), (TILE_W, SKY_H)],
    SKY_DOWN:  [(0, SKY_H), (16, SKY_H), (TILE_W, DECK_H)],
}
# A split column's own profile is its front lanes' (edge chaining, editor, minimap).
for _t, (_lo, _hi) in SPLITS.items():
    PROFILES[_t] = PROFILES[_lo]


def edge_heights(tile):
    """(entry height, exit height) of a terrain tile at its column edges."""
    prof = PROFILES[tile]
    return prof[0][1], prof[-1][1]


def _sample(profile, lx):
    for (x0, h0), (x1, h1) in zip(profile, profile[1:]):
        if x0 <= lx <= x1:
            if x1 == x0:
                return h1
            return h0 + (h1 - h0) * (lx - x0) / (x1 - x0)
    return profile[-1][1]


class Track:
    def __init__(self, terrain, surface=None, material=None, laps=1,
                 name="Track", theme="valley", meta=None):
        self.terrain = list(terrain)
        n = len(self.terrain)
        self.surface = surface or [[NONE] * n for _ in range(LANES)]
        self.material = material or [DIRT] * n
        self.laps = laps
        self.name = name
        self.theme = theme
        self.meta = meta or {}
        self.rebuild()

    # -- geometry ------------------------------------------------------------
    @property
    def ncols(self):
        return len(self.terrain)

    def rebuild(self):
        """Recompute per-pixel heights after any change to terrain. Tracks with
        split columns keep a second height table for the back (high) lanes."""
        self.length = self.ncols * TILE_W
        self.has_split = any(t in SPLITS for t in self.terrain)
        self._h = self._heights(None)
        self._h_up = self._heights(0) if self.has_split else self._h

    def _heights(self, lane):
        hs = []
        for t in self.terrain:
            prof = PROFILES[lane_tile(t, lane)]
            hs.extend(_sample(prof, lx) for lx in range(TILE_W))
        return hs

    def tile(self, col, lane=None):
        """The terrain tile lane `lane` rides in column col (None = front lanes)."""
        return lane_tile(self.terrain[col], lane)

    def col_at(self, x):
        return int(x // TILE_W) % self.ncols

    def ground(self, x, lane=None):
        """Ground height (px, up is positive) at track position x in `lane`
        (only split columns differ per lane; None = the front lanes)."""
        hs = self._h_up if lane is not None and lane < HIGH_LANES else self._h
        x = x % self.length
        i = int(x)
        f = x - i
        h0 = hs[i]
        h1 = hs[(i + 1) % self.length]
        return h0 + (h1 - h0) * f

    def slope(self, x, lane=None):
        # One-sided near pit walls so a landing on the lip reads as flat ground.
        here_gap = self.terrain_at(x, lane) in PITS
        a, b = x - 2, x + 2
        if not here_gap and self.terrain_at(a, lane) in PITS:
            a = x
        if not here_gap and self.terrain_at(b, lane) in PITS:
            b = x
        if b == a:
            return 0.0
        return (self.ground(b, lane) - self.ground(a, lane)) / (b - a)

    def terrain_at(self, x, lane=None):
        return lane_tile(self.terrain[self.col_at(x)], lane)

    def surface_at(self, lane, x):
        return self.surface[lane][self.col_at(x)]

    def material_at(self, x):
        return self.material[self.col_at(x)]

    # -- serialisation ------------------------------------------------------------
    def to_dict(self):
        return {
            "v": 1, "name": self.name, "theme": self.theme, "laps": self.laps,
            "terrain": list(self.terrain), "surface": [list(l) for l in self.surface],
            "material": list(self.material), "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d):
        n = len(d["terrain"])
        surface = d.get("surface") or [[NONE] * n for _ in range(LANES)]
        material = d.get("material") or [DIRT] * n
        return cls(d["terrain"], surface, material, d.get("laps", 1),
                   d.get("name", "Track"), d.get("theme", "valley"),
                   d.get("meta", {}))

    def copy(self):
        return Track.from_dict(self.to_dict())


# One char per terrain tile (track strings, share codes, generator segments).
# Plateau tiles: u/t/d rise/top/descent at the low level, U/T/D at the high
# level, k kicker on a low plateau, f fin. Decks: o on-ramp, b deck, e deck
# end (descent), K deck kicker, x broken span, z drawbridge. Split bridge
# (front lanes deck, back lanes skyway): r skyway ramp, y skyway over deck,
# Z skyway over the drawbridge, n skyway drop.
TERRAIN_CHARS = {".": FLAT, "s": RAMP_S, "L": RAMP_L, "g": GAP, "w": WHOOPS, "S": START,
                 "u": UP_LO, "t": TOP_LO, "d": DOWN_LO, "U": UP_HI, "T": TOP_HI,
                 "D": DOWN_HI, "k": KICK, "f": FIN,
                 "o": DECK_UP, "b": DECK, "e": DECK_DOWN, "K": DECK_KICK, "x": DECK_GAP, "z": DRAW,
                 "r": SPLIT_UP, "y": SPLIT, "Z": SPLIT_DRAW, "n": SPLIT_DOWN}


def make_track(spec, laps=2, name="Static", theme="valley"):
    """Build a track from a compact string, one char per column.

    terrain chars: see TERRAIN_CHARS
    Lane overlays are passed as {lane: "string"} via make_track_layers.
    """
    return Track([TERRAIN_CHARS[c] for c in spec], laps=laps, name=name, theme=theme)


def apply_layer(track, lane, layer):
    """Overlay chars on a lane: 'k' / 'c' / 'K' small / medium / large pad,
    'm' mud, 'd' debris, 'p' water, else nothing."""
    m = {"c": COOLANT, "k": PAD_S, "K": PAD_L, "m": MUD, "d": DEBRIS, "p": WATER}
    for i, ch in enumerate(layer[: track.ncols]):
        if ch in m:
            track.surface[lane][i] = m[ch]
