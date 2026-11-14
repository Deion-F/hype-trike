"""Raised decks (overpass, broken bridge, drawbridge, split bridge), complex-structure
frequency by round, and modifier picks leaning harder in later heats."""
import collections

import config as C

from bike import Bike, Controls, base_stats
from editor.io import decode, encode
from race import Race
from run.manager import MODIFIER_HARDNESS, MODIFIER_HEATS, modifier_weights
from track.generator import LIBRARY, complex_weight, generate
from track.tiles import DRAW, DECK_GAP, SPLIT_DRAW, draw_open, make_track
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
    assert {"overpass", "broken bridge", "split bridge"} <= cx
    assert "drawbridge" not in cx                  # replaced by the split bridge
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
        kept["z"] += SPLIT_DRAW in t.terrain       # the split bridge's drawbridge
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


# --- split bridge: front lanes deck + drawbridge, back lanes skyway ----------------------
SPLIT_SEG = "oryyyZyne"


def _split_track():
    from track.tiles import SPLIT_DRAW
    tr = make_track(_spec(SPLIT_SEG, 0), laps=1)
    return tr, tr.terrain.index(SPLIT_DRAW)


def _on(tr, lane, col, lx=10):
    b = Bike(tr, base_stats("dirt"), lane=lane)
    b.x = col * 80 + lx
    b.h = tr.ground(b.x, lane)
    b.speed = 30
    return b


def test_split_bridge_lanes_ride_different_heights():
    from track.tiles import SKY_H, DECK_H
    tr, col = _split_track()
    x = col * 80 + 40
    assert tr.ground(x, 0) == tr.ground(x, 1) == SKY_H
    assert tr.ground(x, 2) == tr.ground(x, 3) == DECK_H
    assert tr.ground(x) == DECK_H                  # no lane: the front lanes
    plain = make_track(_spec(DECK_SEGS["overpass"], 0))
    assert not plain.has_split and plain._h_up is plain._h


def test_skyway_rides_over_an_open_drawbridge_and_the_deck_drops_you_in():
    tr, col = _split_track()
    t = next(t for t in range(400) if draw_open(t + 1, col))
    sky, deck = _on(tr, 1, col, 2), _on(tr, 2, col, 2)
    sky.ticks = deck.ticks = t
    assert ("crash", "pit") not in sky.step(Controls(a=True)) and sky.state == "ride"
    assert ("crash", "pit") in deck.step(Controls(a=True))


def test_cannot_climb_onto_the_skyway_sideways_but_can_drop_off_it():
    from track.tiles import DECK_H
    tr, col = _split_track()
    b = _on(tr, 2, col - 2)
    b.step(Controls(a=True, lane_up=True))
    for _ in range(20):
        b.step(Controls(a=True))
    assert b.lane == 2 and b.lane_index == 2 and b.state == "ride"
    b = _on(tr, 1, col - 2)
    b.step(Controls(a=True, lane_down=True))
    air = False
    for _ in range(40):
        b.step(Controls(a=True))
        air = air or b.airborne
    assert air and b.lane_index == 2 and not b.airborne and abs(b.h - tr.ground(b.x, 2)) < 1
    assert b.h <= DECK_H + 1


def test_split_bridge_clears_for_every_vehicle_from_any_lane():
    from race import Race
    from track.validator import GhostAI
    for v in VEHICLES:
        for lane in range(4):
            for pre in range(0, 12, 4):
                tr = make_track(_spec(SPLIT_SEG, pre), laps=1)
                race = Race(tr, base_stats(v), lane=lane, countdown=False)
                ai = GhostAI()
                crashes = []
                while not race.finished and race.time_ticks < 60 * 60:
                    crashes += [e for e in race.step(ai.controls(race.bike)) if e[0] == "crash"]
                assert race.finished and not crashes, (v, lane, pre, crashes)


def test_share_code_keeps_split_tiles():
    tr = make_track(_spec(SPLIT_SEG, 0))
    assert decode(encode(tr)).terrain == tr.terrain


# --- biome bosses ---------------------------------------------------------------------------
def test_best_rival_is_promoted_to_the_biome_boss():
    from bosses import BOSSES, boss_score
    tr = make_track("S" + "." * 60, laps=1)
    for biome, info in BOSSES.items():
        race = Race(tr, rivals=3, rival_level=0.8, seed=11, countdown=False, boss=biome)
        scores = [boss_score(rb.stats, k) for rb, k in zip(race.rivals, race.rival_kits)]
        assert race.boss == biome and scores[race.boss_i] == max(scores)
        boss = race.rivals[race.boss_i]
        assert boss.stats.vehicle == info["vehicle"]
        mine = [tr for tr in race.trails if tr.owner == race.boss_i][0]
        assert mine.kind == info["trail"] and mine.k == 1.0
        minions = [tr for tr in race.trails if tr.owner != race.boss_i]
        assert len(minions) == 2 and all(tr.kind == info["trail"] and tr.k < 1 and tr.life < mine.life
                                         for tr in minions)
    assert Race(tr, rivals=3, seed=1, countdown=False).boss is None       # normal races: no boss


def _in_trail(kind, one=True, temp=14.0):
    from bosses import BossTrail
    tr = make_track("S" + "." * 60, laps=1)
    b = Bike(tr, base_stats("dirt")); b.one_button = one
    b.x = 600.0; b.h = tr.ground(b.x); b.speed = 40; b.temp = temp
    trail = BossTrail(kind, 0)
    trail.points.append((b.x, b.lane_index, 0))
    assert trail.hits(b)
    b.trail = kind
    return b


def test_boss_trails_hit_the_player():
    b = _in_trail("fire")
    for _ in range(30):
        b.step(Controls(a=False))
    assert b.temp > 14.0                                   # fire heats you even off the throttle
    b = _in_trail("fire", temp=31.5)
    ev = []
    for _ in range(10):
        ev += b.step(Controls(a=False))
    assert ("explode",) in ev                              # ... and blows you up in the red
    b = _in_trail("smoke"); b.step(Controls(a=False)); assert b.temp < 14.0 - 0.3
    b = _in_trail("sand"); b.step(Controls(a=True)); assert b.temp <= 14.0
    b = _in_trail("oil"); b.step(Controls(a=True)); assert b.wobble > 0
    b = _in_trail("mud"); b.temp = 20.0
    for _ in range(200):
        b.temp = 20.0
        b.step(Controls(a=True))
    assert b.speed <= b.stats.mud_speed + 0.01


def test_boss_race_drops_a_trail_and_replays_exactly():
    import json
    import replay as rp
    from track.validator import GhostAI
    tr = make_track("S" + "." * 40, laps=1)
    race = Race(tr, base_stats(), rivals=3, rival_level=0.7, seed=5, boss="lava")
    race.bike.one_button = True
    rec = rp.Recorder(race, "flame", {"kind": "test"}, {"throttle_mode": "one"})
    ai = GhostAI(seed=2)
    seen = 0
    while not race.finished and race.time_ticks < 60 * 90:
        ctl = ai.controls(race.bike)
        rec.tick(ctl, race.step(ctl))
        seen = max(seen, sum(len(tr.points) for tr in race.trails))
    assert seen > 0
    data = json.loads(json.dumps(rec.finish({"finished": race.finished})))
    again = rp.resimulate(data)
    assert again.boss == "lava" and again.rival_finish == race.rival_finish
    assert abs(again.bike.x - race.bike.x) < 1e-6



def _boss_race(biome, seed=4):
    tr = make_track("S" + "." * 200, laps=1)
    return Race(tr, base_stats(), rivals=3, rival_level=1.0, seed=seed, countdown=False, boss=biome)


def _place(race, x, lane=1):
    b = race.bike
    b.x, b.lane, b.lane_pos = float(x), lane, float(lane)
    b.h, b.airborne, b.speed, b.state = race.track.ground(b.x, lane), False, 40, "ride"
    return b


def test_every_boss_uses_its_powers():
    from bosses import BOSSES
    for biome in BOSSES:
        race = _boss_race(biome)
        boss = race.rivals[race.boss_i]
        fired = set()
        for _ in range(1500):
            b = race.bike
            if abs(b.x - boss.x) > 60:                    # stay near the boss
                _place(race, boss.x + 50, b.lane)
            fired |= {e[1] for e in race.step(Controls(a=True)) if e[0] == "boss"}
        expect = {"valley": "bomb", "desert": "devil", "night": "blackout", "stadium": "pyro",
                  "lava": "eruption"}[biome]
        assert expect in fired, (biome, fired)


def test_boss_hazards_hit_the_player():
    from bosses import Hazard
    race = _boss_race("desert")
    t = race.time_ticks
    b = _place(race, 900, 1)
    race.brain.hazards = [Hazard("devil", b.x, 1, t - 40, 30, 200)]
    race.brain.hazards[0].dir = 1
    ev = race.brain.update(race, race.rivals[race.boss_i], [], [])
    assert ("boss", "shoved") in ev and b.lane == 2
    for kind in ("pyro", "lava"):
        race = _boss_race("stadium" if kind == "pyro" else "lava")
        b = _place(race, 900, 1); b.one_button = True; b.temp = 10.0
        race.brain.hazards = [Hazard(kind, b.x, 1, race.time_ticks - 60, 45, 100)]
        race.brain.update(race, race.rivals[race.boss_i], [], [])
        assert b.temp > 10.0 + C.HEAT_BAR
    race = _boss_race("valley")
    b = _place(race, 900, 1)
    race.brain.hazards = [Hazard("mud", b.x + 5, 1, race.time_ticks - 60, 50, 180)]
    assert race.brain.mud_under(b, race.time_ticks)


def test_boss_auras():
    race = _boss_race("night")
    boss = race.rivals[race.boss_i]
    b = _place(race, boss.x + 40)
    race.brain.player_mods(race, boss)
    assert b.land_mult < 1.0                                  # Hex: tighter landings near it
    _place(race, boss.x + 600)
    race.brain.player_mods(race, boss)
    assert b.land_mult == 1.0
    race = _boss_race("lava")
    boss = race.rivals[race.boss_i]
    _place(race, boss.x + 40)
    race.brain.player_mods(race, boss)
    assert race.bike.heat_aura > 0                            # Heat Wave
    race = _boss_race("desert")
    boss = race.rivals[race.boss_i]
    b = _place(race, boss.x + 60, boss.lane_index)
    race.brain.player_mods(race, boss)
    assert b.heat_aura < 0                                    # Sandblast from behind you
    b.airborne = True
    race.brain.player_mods(race, boss)
    assert b.heat_aura == 0                                   # jump out of it


def test_hex_tightens_the_landing_window():
    tr = make_track("S" + "." * 60, laps=1)
    for mult, ok in ((1.0, True), (0.7, False)):
        b = Bike(tr, base_stats()); b.speed = 40
        b.x = 600.0; b.airborne = True; b.air_ticks = 30; b.h = tr.ground(b.x) + 0.5; b.vy = -1
        b.angle = -(C.LAND_TOLERANCE * 0.85)
        b.land_mult = mult
        ev = b.step(Controls())
        assert (("land",) in ev or ("rough",) in ev) and ((("land",) in ev) == ok)


def test_showstopper_crowd_and_baron_quake():
    race = _boss_race("stadium")
    boss = race.rivals[race.boss_i]
    b = _place(race, boss.x + 40)
    s0, sb = b.speed, boss.speed
    ev = race.brain.update(race, boss, [("perfect",)], [("perfect",)])
    assert ("boss", "crowd_you") in ev and b.speed > s0 and boss.speed > sb
    race = _boss_race("valley")
    boss = race.rivals[race.boss_i]
    b = _place(race, boss.x + 40)
    race.brain._boss_air = 30
    ev = race.brain.update(race, boss, [], [("land",)])
    assert ("boss", "quake") in ev and b.wobble > 0


def test_minion_trails_are_weaker():
    b_full, b_minion = _in_trail("fire"), _in_trail("fire")
    b_minion.trail_k = 0.5
    for x in (b_full, b_minion):
        for _ in range(20):
            x.step(Controls(a=False))
    assert 14.0 < b_minion.temp < b_full.temp
