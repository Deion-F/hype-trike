"""Tile vocabulary (spec §5.2), ground materials, and the Track model.

A track is a list of columns, each TILE_W pixels wide.
  * terrain[col]   - column-wide shape tile (flat, ramps, gap, whoops, start)
  * surface[l][col]- per-lane surface tile (coolant, mud, debris) or NONE
  * material[col]  - ground material (dirt, grass, sand) for vehicle grip
Height profiles are precomputed per pixel so physics lookups are cheap and the
simulation stays deterministic.
"""
import math

from config import TILE_W, LANES

# --- tile IDs (spec §5.2) ------------------------------------------------------
FLAT, RAMP_S, RAMP_L, COOLANT, MUD, DEBRIS, START, GAP, WHOOPS = range(9)
NONE = -1

TILE_NAMES = {
    FLAT: "Flat", RAMP_S: "Ramp S", RAMP_L: "Ramp L", COOLANT: "Coolant",
    MUD: "Mud", DEBRIS: "Debris", START: "Start", GAP: "Gap", WHOOPS: "Whoops",
}
TERRAIN_TILES = (FLAT, RAMP_S, RAMP_L, START, GAP, WHOOPS)
SURFACE_TILES = (COOLANT, MUD, DEBRIS)

# --- ground materials ---------------------------------------------------------------
DIRT, GRASS, SAND = range(3)
MATERIAL_NAMES = {DIRT: "Dirt", GRASS: "Grass", SAND: "Sand"}
MATERIALS = (DIRT, GRASS, SAND)

# --- height profiles: polylines of (local_x, height) -----------------------------
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
}
PIT_DEPTH = -70


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
        """Recompute per-pixel heights after any change to terrain."""
        self.length = self.ncols * TILE_W
        hs = []
        for t in self.terrain:
            prof = PROFILES[t]
            hs.extend(_sample(prof, lx) for lx in range(TILE_W))
        self._h = hs

    def col_at(self, x):
        return int(x // TILE_W) % self.ncols

    def ground(self, x):
        """Ground height (px, up is positive) at track position x."""
        x = x % self.length
        i = int(x)
        f = x - i
        h0 = self._h[i]
        h1 = self._h[(i + 1) % self.length]
        return h0 + (h1 - h0) * f

    def slope(self, x):
        # One-sided near pit walls so a landing on the lip reads as flat ground.
        here_gap = self.terrain_at(x) == GAP
        a, b = x - 2, x + 2
        if not here_gap and self.terrain_at(a) == GAP:
            a = x
        if not here_gap and self.terrain_at(b) == GAP:
            b = x
        if b == a:
            return 0.0
        return (self.ground(b) - self.ground(a)) / (b - a)

    def terrain_at(self, x):
        return self.terrain[self.col_at(x)]

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


def make_track(spec, laps=2, name="Static", theme="valley"):
    """Build a track from a compact string, one char per column.

    terrain chars: '.' flat  's' small ramp  'L' large ramp  'g' gap
                   'w' whoops 'S' start
    Lane overlays are passed as {lane: "string"} via make_track_layers.
    """
    m = {".": FLAT, "s": RAMP_S, "L": RAMP_L, "g": GAP, "w": WHOOPS, "S": START}
    return Track([m[c] for c in spec], laps=laps, name=name, theme=theme)


def apply_layer(track, lane, layer):
    """Overlay chars on a lane: 'c' coolant  'm' mud  'd' debris, else nothing."""
    m = {"c": COOLANT, "m": MUD, "d": DEBRIS}
    for i, ch in enumerate(layer[: track.ncols]):
        if ch in m:
            track.surface[lane][i] = m[ch]
