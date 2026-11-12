"""Procedural tracks by constraint-based segment assembly (spec §5.3).

1. A library of hand-authored segments with metadata (difficulty, runway needed
   before them, expected turbo heat, which hazards go where).
2. Segments are picked by weighted difficulty for the run depth, and only when
   their entry requirement (clear runway to build speed) is met.
3. Coolant pads are inserted when the expected heat since the last pad gets
   close to the overheat margin. Jumps cost less heat because the engine
   doesn't heat in the air.
4. The finished track is ghost-validated with the base bike on throttle A.
   Failing segments are softened (gaps filled, debris removed) and the track
   is re-checked. If that fails, it regenerates from a derived seed.

Segments can also build elevated structures from plateau tiles (see
track.tiles.TERRAIN_CHARS): tabletops, two-tier step-ups, kickers on a mesa,
rows of steep fins. Every segment starts and ends at ground level.

Later depths add ground-material zones (grass, sand) where the unlockable
vehicles grip better (decision 0.4).
"""
import random

import config as C
from track.tiles import (Track, FLAT, START, GAP, COOLANT, MUD, DEBRIS, WATER, NONE,
                         DIRT, GRASS, SAND, PAD_S, PAD_L, PADS, TERRAIN_CHARS, edge_heights)

T = TERRAIN_CHARS


class Segment:
    def __init__(self, name, terrain, diff, runway=0, hazards=(), weight=1.0,
                 min_depth=0, heat_discount=0.0):
        self.name = name
        self.terrain = terrain          # terrain chars
        self.diff = diff                # 1 (easy) .. 5 (hard)
        self.runway = runway            # clear columns needed before (to be at speed)
        self.hazards = hazards          # (col_offset, kind, lanes_min, lanes_max)
        self.weight = weight
        self.min_depth = min_depth
        self.heat_discount = heat_discount  # columns spent airborne (no heat)

    @property
    def ncols(self):
        return len(self.terrain)


LIBRARY = [
    # --- easy --------------------------------------------------------------
    Segment("straight", "....", 1, weight=0.6),
    Segment("bump", "..s..", 1, heat_discount=2),
    Segment("double bump", ".s...s..", 1, heat_discount=4),
    Segment("big air", "..L....", 1, runway=2, heat_discount=4),
    # Whoops (bumpy runs) are hard: none on the first map, and rare after that.
    Segment("whoops", "..wwww..", 2, weight=0.45, min_depth=1),
    Segment("mud patch", "......", 1, hazards=((2, MUD, 1, 2), (3, MUD, 1, 2))),
    Segment("barrier", "......", 2, hazards=((3, DEBRIS, 1, 2),)),
    # Water puddles (lava pits on the Volcano theme): ride round them or splash through.
    Segment("puddles", "......", 1, weight=0.8, hazards=((1, WATER, 1, 2), (4, WATER, 1, 2))),
    Segment("splashdown", "..s.....", 2, heat_discount=2, weight=0.7,
            hazards=((4, WATER, 1, 2), (5, WATER, 1, 2)), min_depth=1),
    # --- medium ----------------------------------------------------------------
    Segment("pit hop", "..sg....", 2, runway=3, heat_discount=3, min_depth=0),
    Segment("pit jump", "..L.g....", 2, runway=3, heat_discount=4, min_depth=0),
    Segment("triple", ".s...s...s...", 3, heat_discount=6, min_depth=1),
    Segment("tabletop pair", "..LL.....", 3, runway=2, heat_discount=5, min_depth=1),
    Segment("long whoops", ".wwwwwwww..", 3, weight=0.35, min_depth=2),
    Segment("slalom", "........", 3, hazards=((1, DEBRIS, 1, 2), (4, DEBRIS, 1, 2), (7, DEBRIS, 1, 2)),
            min_depth=1),
    Segment("landing zone", "..L......", 3, runway=2, heat_discount=4,
            hazards=((5, DEBRIS, 1, 2), (6, MUD, 1, 2)), min_depth=1),
    # --- hard --------------------------------------------------------------------
    Segment("canyon", "..Lgg.....", 4, runway=4, heat_discount=5, min_depth=2),
    Segment("wide canyon", "..L.gg.....", 4, runway=5, heat_discount=5, min_depth=3),
    Segment("rhythm gap", ".wwww.L.g....", 4, runway=2, heat_discount=4, min_depth=2, weight=0.5),
    Segment("gauntlet", ".s..L.g...s..", 5, runway=4, heat_discount=8,
            hazards=((3, MUD, 1, 1), (9, DEBRIS, 1, 2)), min_depth=3),
    Segment("mud jump", "....L.g....", 4, runway=2, heat_discount=4,
            hazards=((0, MUD, 2, 3), (1, MUD, 2, 3)), min_depth=3),
    # --- structures (plateaus, step-ups, fins) ---------------------------------
    # u/t/d: rise / top / descent of a low mesa; U/T/D the same one level up;
    # k: kicker on a low mesa; f: steep fin. Columns indexes below are offsets.
    Segment("tabletop", "..utttd...", 2, runway=2, heat_discount=2, weight=1.1),
    Segment("fin", "..f....", 2, runway=2, heat_discount=2),
    Segment("long mesa", "..utttttd...", 2, heat_discount=2, weight=0.8,
            hazards=((4, MUD, 1, 2),), min_depth=1),
    Segment("step-up", "..utttUTTDd...", 3, runway=2, heat_discount=4, min_depth=1, weight=1.2),
    Segment("fin row", ".f.....f.....f.....", 3, runway=2, heat_discount=5, min_depth=1),
    Segment("mesa jump", "..L.uttd...", 3, runway=3, heat_discount=4, min_depth=1),
    Segment("mesa kicker", "..uttkttd...", 3, runway=2, heat_discount=4, min_depth=1),
    Segment("muddy mesa", "..utttttd...", 3, heat_discount=2, min_depth=2,
            hazards=((3, MUD, 1, 2), (5, DEBRIS, 1, 2))),
    Segment("twin peaks", "..uUTDtUTDd....", 4, runway=2, heat_discount=6, min_depth=2),
    Segment("stair kicker", "..utkUTTDd....", 4, runway=3, heat_discount=5, min_depth=3),
    Segment("skyway", "..uUTTTTDd....", 4, runway=2, heat_discount=4, min_depth=2,
            hazards=((4, DEBRIS, 1, 2), (6, MUD, 1, 2))),
    Segment("fin gauntlet", ".ff.....f.....ff......", 4, runway=3, heat_discount=7, min_depth=2, weight=0.7),
    Segment("mesa canyon", "..utttd.g.....", 4, runway=4, heat_discount=5, min_depth=3, weight=0.7),
    Segment("summit", "..utUTTDtkd...f....", 5, runway=3, heat_discount=8, min_depth=3, weight=0.7,
            hazards=((5, MUD, 1, 2),)),
]

THEME_BY_DEPTH = ["valley", "desert", "night", "stadium", "desert", "night", "stadium", "valley"]

HEAT_PER_COL_TURBO = 14 * C.HEAT_B     # ~1 degree per column on full turbo
HEAT_MARGIN = C.TEMP_OVERHEAT - C.TEMP_STABLE_A - 2.0


class GenResult:
    def __init__(self, track, attempts, softened, validation):
        self.track = track
        self.attempts = attempts
        self.softened = softened
        self.validation = validation


def target_difficulty(depth):
    return 1.2 + depth * 0.65


def length_for(depth):
    return 46 + depth * 6


def _pick(rng, depth, runway, diff_target, last_name):
    cands = []
    for s in LIBRARY:
        if s.min_depth > depth or s.runway > runway or s.name == last_name:
            continue
        # prefer segments near the target difficulty
        w = s.weight * (2.0 ** (-abs(s.diff - diff_target)))
        cands.append((s, w))
    total = sum(w for _, w in cands)
    r = rng.random() * total
    for s, w in cands:
        r -= w
        if r <= 0:
            return s
    return cands[-1][0]


def generate(seed, depth=0, modifiers=(), validate_with=None, max_attempts=8):
    """Build a validated track. Returns GenResult."""
    from track.validator import validate
    for attempt in range(max_attempts):
        rng = random.Random((seed * 1_000_003 + attempt * 7919) & 0xFFFFFFFF)
        track = _assemble(rng, depth, modifiers)
        track.meta.update({"seed": seed, "depth": depth, "attempt": attempt,
                           "modifiers": list(modifiers)})
        softened = 0
        riders = _riders(validate_with)
        for _ in range(8):
            res = None
            for st in riders:
                res = validate(track, st)
                if not res["ok"]:
                    break
            if res["ok"]:
                return GenResult(track, attempt + 1, softened, res)
            for _, col in res["crashes"]:
                softened += _soften(track, col)
            if not res["crashes"]:      # timed out (e.g. lots of mud): soften everywhere
                break
            track.rebuild()
        # fall through: new attempt with a derived seed
    # Last resort: a gentle track that always validates.
    track = _assemble(random.Random(seed), 0, ("gentle",) + tuple(modifiers))
    return GenResult(track, max_attempts + 1, 0, validate(track, _riders(validate_with)[-1]))


def _riders(validate_with):
    """Always validate with the base dirt bike, plus any extra stats given."""
    from bike import base_stats
    riders = [base_stats("dirt")]
    if validate_with is None:
        return riders
    if not isinstance(validate_with, (list, tuple)):
        validate_with = [validate_with]
    return riders + [s for s in validate_with if s is not None]


def _assemble(rng, depth, modifiers):
    n_target = length_for(depth)
    diff = target_difficulty(depth)
    if "gentle" in modifiers:
        diff = 1.0
    terrain = ["S", ".", ".", ".", "."]
    surface = [[NONE] * len(terrain) for _ in range(C.LANES)]
    seg_of_col = [None] * len(terrain)
    runway = 4
    heat = 0.0
    last = None
    no_coolant = "no_coolant" in modifiers
    while len(terrain) < n_target:
        seg = _pick(rng, depth if "gentle" not in modifiers else 0, runway, diff, last)
        if "gentle" in modifiers and seg.diff > 1:
            continue
        start = len(terrain)
        terrain.extend(seg.terrain)
        for lane in range(C.LANES):
            surface[lane].extend([NONE] * seg.ncols)
        seg_of_col.extend([seg.name] * seg.ncols)
        for off, kind, lo, hi in seg.hazards:
            col = start + off
            k = rng.randint(lo, min(hi, C.LANES - 1))   # always leave a lane free
            for lane in rng.sample(range(C.LANES), k):
                surface[lane][col] = kind
        last = seg.name
        # runway: clear columns at the end of this segment
        tail = 0
        for i in range(len(terrain) - 1, start - 1, -1):
            clear = terrain[i] == "." and all(surface[l][i] != MUD for l in range(C.LANES))
            if not clear:
                break
            tail += 1
        runway = tail if tail < seg.ncols else runway + tail
        # heat budget -> coolant pads
        heat += (seg.ncols - seg.heat_discount) * HEAT_PER_COL_TURBO
        if not no_coolant and heat >= HEAT_MARGIN * rng.uniform(0.75, 1.0):
            heat = 0.0 if _place_coolant(rng, terrain, surface, start) else heat
    if "sticky" in modifiers:
        for c in range(6, len(terrain)):
            if rng.random() < 0.35:
                for lane in rng.sample(range(C.LANES), 2):
                    free = sum(1 for l in range(C.LANES) if surface[l][c] == NONE or surface[l][c] in PADS)
                    if surface[lane][c] == NONE and free > 1:
                        surface[lane][c] = MUD
    # finishing straight back to the start line
    terrain.extend(["."] * 3)
    for lane in range(C.LANES):
        surface[lane].extend([NONE] * 3)
    track = Track([T[c] for c in terrain], surface, None, laps=2,
                  name=_name(rng, depth), theme=THEME_BY_DEPTH[depth % len(THEME_BY_DEPTH)])
    _materials(rng, track, depth, modifiers)
    # which library segment each column came from (recordings / tuning reports)
    track.meta["segments"] = [s or "runway" for s in seg_of_col] + ["finish"] * 3
    track.rebuild()
    return track


def _place_coolant(rng, terrain, surface, start):
    cols = [i for i in range(start, len(terrain))
            if terrain[i] == "." and all(surface[l][i] == NONE for l in range(C.LANES))]
    if not cols:
        return False
    col = rng.choice(cols)
    for lane in rng.sample(range(C.LANES), rng.randint(1, 2)):
        r = rng.random()               # pad size: small / medium / large
        surface[lane][col] = PAD_S if r < 0.4 else COOLANT if r < 0.75 else PAD_L
    return True


def _materials(rng, track, depth, modifiers):
    """Grass from depth 2, sand from depth 3; more coverage deeper."""
    mats = []
    if depth >= 2 or "grass" in modifiers:
        mats.append(GRASS)
    if depth >= 3 or "sand" in modifiers:
        mats.append(SAND)
    if not mats:
        return
    zones = 1 + min(3, depth // 2)
    n = track.ncols
    for _ in range(zones):
        m = rng.choice(mats)
        length = rng.randint(6, 10 + depth * 2)
        start = rng.randint(6, max(7, n - length - 2))
        for i in range(start, min(n - 1, start + length)):
            track.material[i] = m


def _soften(track, col):
    """Make the area around a crash column easier. Returns #changes."""
    n = track.ncols
    changes = 0
    for c in range(col - 3, col + 2):
        c %= n
        if track.terrain[c] == GAP:
            track.terrain[c] = FLAT
            changes += 1
        for lane in range(C.LANES):
            if track.surface[lane][c] in (DEBRIS, MUD, WATER):
                track.surface[lane][c] = NONE
                changes += 1
        if track.material[c] != DIRT:
            track.material[c] = DIRT
            changes += 1
    if changes == 0:
        # Nothing obvious (e.g. ramp into ramp): flatten the crash column, or
        # the whole elevated structure around it so no wall is left behind.
        for c in range(col - 2, col + 1):
            c %= n
            if track.terrain[c] in (FLAT, START):
                continue
            for s in _structure(track, c):
                track.terrain[s] = FLAT
                changes += 1
            break
    return changes


def _structure(track, col):
    """Columns of the elevated structure containing col (just col for a
    tile that starts and ends at ground level)."""
    n = track.ncols
    lo = hi = col
    while edge_heights(track.terrain[lo])[0] != 0 and lo > 0:
        lo -= 1
    while edge_heights(track.terrain[hi])[1] != 0 and hi < n - 1:
        hi += 1
    return range(lo, hi + 1)


_ADJ = ["Dusty", "Rattle", "Thunder", "Gravel", "Hyper", "Crooked", "Sunset", "Mad",
        "Rocket", "Twisted", "Red", "Shadow", "Wild", "Bouncy", "Iron", "Neon"]
_NOUN = ["Gulch", "Ridge", "Run", "Hollow", "Canyon", "Flats", "Bowl", "Pass",
         "Circuit", "Dunes", "Valley", "Mile", "Ramps", "Basin", "Loop", "Trail"]


def _name(rng, depth):
    return f"{rng.choice(_ADJ)} {rng.choice(_NOUN)}"
