"""Raised decks (overpass, broken bridge, drawbridge), complex-structure
frequency by round, and modifier picks leaning harder in later heats."""
import collections

from bike import Bike, Controls, base_stats
from editor.io import decode, encode
from race import Race
from run.manager import MODIFIER_HARDNESS, MODIFIER_HEATS, modifier_weights
from track.generator import LIBRARY, complex_weight, generate
from track.tiles import DRAW, DECK_GAP, draw_open, make_track
from track.validator import validate

VEHICLES = ("dirt", "trike", "scrambler", "sprinter")
DECK_SEGS = {"overpass": "obbbbbbe", "broken bridge": "obbbbbKxbbbe", "drawbridge": "obbbbbbzbbe"}


def _spec(seg, pre):
    return "S" + "." * (4 + pre) + ".." + seg + "......."


def test_deck_segments_clear_for_every_vehicle_at_any_position():
    # the drawbridge's phase depends on its column, so slide it along the track
    for name, seg in DECK_SEGS.items():
        for v in VEHICLES:
            for pre in range(0, 12, 3) if name != "drawbridge" else range(0, 20):
                r = validate(make_track(_spec(seg, pre), laps=2), base_stats(v))
                assert r["ok"], (name, v, pre, r["crashes"])


def test_broken_bridge_needs_speed():
    st = base_stats("dirt")
    st.max_speed_a = 32
    r = validate(make_track(_spec(DECK_SEGS["broken bridge"], 0), laps=1), st)
    assert ("pit" in [c for c, _ in r["crashes"]])


def test_open_drawbridge_drops_you_in():
    tr = make_track(_spec(DECK_SEGS["drawbridge"], 0), laps=1)
    col = tr.terrain.index(DRAW)
    b = Bike(tr, base_stats("dirt"))
    b.x = col * 80 + 2
    b.h = tr.ground(b.x)
    b.speed = 30
    t = next(t for t in range(400) if draw_open(t + 1, col))
    b.ticks = t
    ev = b.step(Controls(a=True))
    assert ("crash", "pit") in ev


def test_no_complex_structures_on_first_map_and_more_later():
    cx = {s.name for s in LIBRARY if s.complex}
    assert {"overpass", "broken bridge", "drawbridge"} <= cx
    assert complex_weight(0) == 0
    assert all(complex_weight(d + 1) > complex_weight(d) for d in range(5))
    per_depth = []
    for depth in (0, 1, 4):
        n = 0
        for seed in range(8):
            segs = generate(seed * 11 + 3, depth=depth).track.meta["segments"]
            n += sum(1 for i, s in enumerate(segs) if s in cx and (i == 0 or segs[i - 1] != s))
        per_depth.append(n)
    assert per_depth[0] == 0
    assert per_depth[0] < per_depth[1] < per_depth[2]


def test_deck_hazards_survive_generation():
    kept = collections.Counter()
    for seed in range(12):
        t = generate(seed * 13 + 1, depth=4).track
        kept["x"] += DECK_GAP in t.terrain
        kept["z"] += DRAW in t.terrain
    assert kept["x"] > 0 and kept["z"] > 0


def test_share_code_keeps_deck_tiles():
    tr = make_track(_spec(DECK_SEGS["broken bridge"] + "obbbbbbzbbe", 0))
    assert decode(encode(tr)).terrain == tr.terrain


def test_later_modifier_heat_prefers_harder_modifiers():
    hardest = max(MODIFIER_HARDNESS, key=MODIFIER_HARDNESS.get)
    easiest = min(MODIFIER_HARDNESS, key=MODIFIER_HARDNESS.get)
    first, last = modifier_weights(MODIFIER_HEATS[0]), modifier_weights(MODIFIER_HEATS[-1])
    assert last[hardest] > first[hardest]
    assert first[easiest] > last[easiest]
    assert first[easiest] > first[hardest] and last[hardest] > last[easiest]
