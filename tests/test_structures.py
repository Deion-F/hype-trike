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


# --- biome bosses (a chase: bosses.BossChase) ------------------------------------------------
def test_boss_race_is_a_chase_with_minions():
    from bosses import BOSSES, START_GAP
    tr = make_track("S" + "." * 60, laps=1)
    for biome, info in BOSSES.items():
        race = Race(tr, rivals=3, rival_level=0.8, seed=11, countdown=False, boss=biome)
        ch = race.chase
        assert race.boss == biome and ch is not None and race.track is not tr
        assert ch.x == C.START_X + START_GAP and ch.hp == 3          # in view at the start
        assert len(race.rivals) == 3 and all(rb.stats.max_speed_b < C.SPEED_MAX_B for rb in race.rivals)
        assert len(race.trails) == 3 and all(t.kind == info["trail"] and t.k < 1 for t in race.trails)
    for _ in range(600):
        race.step(Controls(a=True))
    pv = race.chase.paver
    assert pv.built > pv.OPENING and tr.ncols == 61                    # lays its own; the reel is untouched
    assert pv.built * C.TILE_W <= race.chase.front                     # only under itself, never ahead
    assert Race(tr, rivals=3, seed=1, countdown=False).chase is None  # normal races: no boss


def _boss_race(biome, seed=4):
    tr = make_track("S" + "." * 200, laps=1)
    return Race(tr, base_stats(), rivals=3, rival_level=1.0, seed=seed, countdown=False, boss=biome)


def _place(race, x, lane=1):
    b = race.bike
    b.x, b.lane, b.lane_pos = float(x), lane, float(lane)
    b.h, b.airborne, b.speed, b.state = race.track.ground(b.x, lane), False, 40, "ride"
    return b


def _ram(race, setup=None):
    """Put the player on the rig's tail (after `setup`) and resolve the contact."""
    ch = race.chase
    t = race.time_ticks
    b = _place(race, ch.x - 4, race.bike.lane)
    if setup:
        setup(race, ch, b, t)
    out = []
    ch._contact(race, t, out)
    return out


WEAK_SETUPS = {
    "valley": lambda r, ch, b, t: (setattr(ch, "window_from", t - 60), setattr(ch, "window_until", t + 60),
                                   setattr(b, "lane", ch.lantern), setattr(b, "lane_pos", float(ch.lantern))),
    "desert": lambda r, ch, b, t: (setattr(b, "airborne", True), setattr(b, "h", b.h + 30)),
    "night": lambda r, ch, b, t: (setattr(b, "lane", ch.lantern), setattr(b, "lane_pos", float(ch.lantern))),
    "stadium": lambda r, ch, b, t: setattr(ch, "spot_until", t + 10),
    "lava": lambda r, ch, b, t: (setattr(b, "_one_button", True), setattr(b, "temp", C.ONE_OVERHEAT_AT + 1)),
}


def test_ramming_the_rig_without_its_weak_point_bonks_you():
    from bosses import BOSSES, CONTACT
    for biome in BOSSES:
        race = _boss_race(biome)
        ch = race.chase
        if biome == "night":
            race.bike.lane = race.bike.lane_pos = (ch.lantern + 1) % C.LANES
        out = _ram(race)
        b = race.bike
        assert any(e[:2] == ("boss", "bonk") and e[2].startswith(ch.weak) for e in out) and ch.hp == 3, biome
        assert b.x <= ch.x - CONTACT and b.speed < 40              # thrown back, slower: it can't be passed


def test_a_bonk_sends_the_boss_off_screen_like_the_start():
    from bosses import FLEE_GAP, INTRO_SPEED, INTRO_TICKS
    race = _boss_race("valley")
    for _ in range(INTRO_TICKS + 5):
        race.step(Controls())
    ch = race.chase
    ch.speed = ch.cruise
    _ram(race)                                                      # on the ground: a bonk
    assert ch.flee_until > race.time_ticks
    top, attacks = 0.0, 0
    for _ in range(400):
        b = race.bike
        b.speed = 0                                                 # you sit still after the knock
        attacks += sum(1 for e in race.step(Controls()) if e[0] == "boss" and e[1] == "bomb")
        top = max(top, ch.speed)
        if ch.gap(b) >= FLEE_GAP:
            break
    assert top >= INTRO_SPEED - 1 and ch.gap(race.bike) >= FLEE_GAP and attacks == 0
    race.step(Controls())
    assert ch.flee_until <= race.time_ticks                         # out of sight: back to cruising


def test_every_weak_point_takes_a_hit():
    from bosses import BOSSES
    for biome in BOSSES:
        race = _boss_race(biome)
        out = _ram(race, WEAK_SETUPS[biome])
        assert ("boss", "hit", 2) in out and race.chase.hp == 2, (biome, out)
        assert race.chase.surge_until > race.time_ticks             # it surges away to be chased again


def test_three_hits_wreck_it_and_win_the_race():
    race = _boss_race("stadium")
    race.step(Controls(a=True))
    for _ in range(3):
        _ram(race, WEAK_SETUPS["stadium"])
    assert race.chase.outcome == "won"
    ev = race.step(Controls(a=True))
    assert any(e[0] == "finish" for e in ev) and race.finished and race.beat_boss() is True


def test_falling_too_far_behind_loses():
    from bosses import LOSE_GAP
    race = _boss_race("valley")
    race.step(Controls(a=True))
    race.chase.x = race.bike.x + LOSE_GAP + 10
    ev = race.step(Controls(a=True))
    assert ("boss", "escaped") in ev and race.finished and race.beat_boss() is False


def test_minions_block_you_from_behind_in_their_lane():
    race = _boss_race("desert")
    race.step(Controls(a=True))
    x = race.chase.x - 3 * C.TILE_W                                 # behind the rig
    b = _place(race, x, 2)
    m = race.add_minion(2, x + 12, 30)
    m.speed = 30
    out = []
    race.chase._minions(race, race.time_ticks, out)
    assert ("boss", "minion_bump") in out and b.x <= m.x - 19 and b.speed < 40
    b = _place(race, x, 1)                                          # another lane: ride on by
    out = []
    race.chase._minions(race, race.time_ticks, out)
    assert ("boss", "minion_bump") not in out


def test_the_boss_lays_its_own_pieces_when_you_are_close():
    from track.tiles import RAMP_L, DEBRIS, MUD
    race = _boss_race("desert")
    pv = race.chase.paver
    start = pv.built
    pv.want_helper = True
    pv.lay_until((start + 12) * C.TILE_W, True)
    assert RAMP_L in race.track.terrain[start:pv.built] and pv.helper_end is not None
    race = _boss_race("night")
    pv = race.chase.paver
    pv.lantern, start = 2, pv.built
    pv.want_helper = True
    pv.lay_until((start + 12) * C.TILE_W, True)
    row = start + (pv.helper_end - start) - 6                       # the corridor's barrier column
    lanes = [race.track.surface[l][row] for l in range(C.LANES)]
    assert lanes[2] != DEBRIS and lanes.count(DEBRIS) == 3          # every lane but the lantern's
    race = _boss_race("valley")                                     # the Baron: mud, but not the hatch lane
    pv = race.chase.paver
    pv.lantern, start = 1, pv.built
    pv.want_helper = True
    pv.lay_until((start + 12) * C.TILE_W, True)
    row = pv.helper_end - 6
    lanes = [race.track.surface[l][row] for l in range(C.LANES)]
    assert lanes[1] != MUD and lanes.count(MUD) == 3


def test_hatch_needs_its_lane_and_the_shield_up():
    race = _boss_race("valley")
    ch = race.chase
    t = race.time_ticks
    wrong = (ch.lantern + 1) % C.LANES
    _place(race, ch.x - 4, ch.lantern)
    assert not ch.weak_open(race.bike, t)                          # shield down
    ch.window_from, ch.window_until = t - 60, t + 60
    assert ch.weak_open(race.bike, t)                              # lifted, right lane
    _place(race, ch.x - 4, wrong)
    assert not ch.weak_open(race.bike, t)                          # lifted, wrong lane


def test_the_boss_holds_back_while_you_recover_from_a_crash():
    from bosses import RECOVER_K, FLEE_GAP
    race = _boss_race("night")
    race.step(Controls())
    ch = race.chase
    ch.x = race.bike.x + FLEE_GAP + 200                             # off screen ahead
    ch.speed = ch.cruise
    race.bike._crash([], "nose")
    for _ in range(80):
        race.step(Controls())
    assert ch.speed <= ch.cruise * RECOVER_K + 0.01


def test_every_boss_uses_its_attack():
    from bosses import BOSSES
    for biome in BOSSES:
        race = _boss_race(biome)
        ch = race.chase
        fired = set()
        for _ in range(1500):
            b = race.bike
            if ch.gap(b) > 3 * C.TILE_W or ch.gap(b) < C.TILE_W:     # stay close behind it
                _place(race, ch.x - 2 * C.TILE_W, b.lane)
            fired |= {e[1] for e in race.step(Controls(a=True)) if e[0] == "boss"}
        expect = {"valley": "bomb", "desert": "devil", "night": "blackout", "stadium": "pyro",
                  "lava": "eruption"}[biome]
        assert expect in fired and "minion" in fired, (biome, fired)


def test_boss_hazards_hit_the_player():
    from bosses import Hazard
    race = _boss_race("desert")
    t = race.time_ticks
    b = _place(race, 900, 1)
    hz = Hazard("devil", b.x, 1, t - 40, 30, 200)
    hz.dir = 1
    race.chase.hazards = [hz]
    out = []
    race.chase._attacks(race, t, out)
    assert ("boss", "shoved") in out and b.lane == 2
    for kind in ("pyro", "lava"):
        race = _boss_race("stadium" if kind == "pyro" else "lava")
        b = _place(race, 900, 1); b.one_button = True; b.temp = 10.0
        race.chase.hazards = [Hazard(kind, b.x, 1, race.time_ticks - 60, 45, 100)]
        race.chase._attacks(race, race.time_ticks, [])
        assert b.temp > 10.0 + C.HEAT_BAR
    race = _boss_race("valley")
    b = _place(race, 900, 1)
    race.chase.hazards = [Hazard("mud", b.x + 5, 1, race.time_ticks - 60, 50, 180)]
    assert race.chase.mud_under(b, race.time_ticks)


def test_only_a_hot_rider_catches_the_boss():
    """Up close the later bosses outpace the warm band: a rider who keeps to warm
    never catches them, one who rides overheating does (real run tracks, a good AI)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from tuning import make_pilot, TIERS
    from run.manager import RunState
    from track.validator import GhostAI
    r = RunState(seed=3)
    for i in (8, 11):                                   # Night and Stadium bosses (the first ones are kinder)
        r.heat_i = i
        h = r.prepare_heat()
        caught = {}
        for name, keep in (("warm", C.ONE_HOT_AT - 0.5), ("overheating", C.ONE_OVERHEAT_AT + 0.5)):
            skill, bl, mi = TIERS["good"]
            pilot = make_pilot(GhostAI(turbo=True, turbo_temp=24, skill=skill, blunder=bl, miss=mi, seed=i),
                               "one", skill)
            race = Race(h.track, r.stats_for_heat(h), rivals=3, rival_level=h.rival_level, seed=h.seed,
                        countdown=False, boss=h.biome)
            b = race.bike
            b.one_button = True
            caught[name] = False
            while race.time_ticks < 60 * 60 and not race.finished:
                c = pilot.controls(b)
                if b.state == "ride" and not b.airborne:
                    c.a, c.b = b.temp < keep, False
                race.step(c)
                caught[name] |= race.time_ticks > 300 and race.chase.engaged
        assert caught == {"warm": False, "overheating": True}, (h.biome, caught)


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


def test_boss_chase_replays_exactly():
    import json
    import replay as rp
    from track.validator import GhostAI
    from bosses import hunter_controls
    tr = make_track("S" + "." * 40, laps=1)
    race = Race(tr, base_stats(), rivals=3, rival_level=0.7, seed=5, boss="lava")
    race.bike.one_button = True
    rec = rp.Recorder(race, "flame", {"kind": "test"}, {"throttle_mode": "one"})
    ai = GhostAI(seed=2)
    seen = 0
    while not race.finished and race.time_ticks < 60 * 90:
        ctl = hunter_controls(race, ai.controls(race.bike))
        rec.tick(ctl, race.step(ctl))
        seen = max(seen, sum(len(tr.points) for tr in race.trails))
    assert seen > 0 and race.chase.paver.built > 40
    data = json.loads(json.dumps(rec.finish({"finished": race.finished})))
    assert data["summary"]["boss"]["biome"] == "lava"
    again = rp.resimulate(data)
    assert again.boss == "lava" and again.track.terrain == race.track.terrain
    assert abs(again.bike.x - race.bike.x) < 1e-6 and again.chase.hp == race.chase.hp
    assert len(again.rivals) == len(race.rivals)


def test_hex_tightens_the_landing_window():
    tr = make_track("S" + "." * 60, laps=1)
    for mult, ok in ((1.0, True), (0.7, False)):
        b = Bike(tr, base_stats()); b.speed = 40
        b.x = 600.0; b.airborne = True; b.air_ticks = 30; b.h = tr.ground(b.x) + 0.5; b.vy = -1
        b.angle = -(C.LAND_TOLERANCE * 0.85)
        b.land_mult = mult
        ev = b.step(Controls())
        assert (("land",) in ev or ("rough",) in ev) and ((("land",) in ev) == ok)


def test_minion_trails_are_weaker():
    b_full, b_minion = _in_trail("fire"), _in_trail("fire")
    b_minion.trail_k = 0.5
    for x in (b_full, b_minion):
        for _ in range(20):
            x.step(Controls(a=False))
    assert 14.0 < b_minion.temp < b_full.temp


def test_a_chase_loops_its_track_and_the_boss_paves_over_it_up_close():
    from track.generator import generate
    from track.tiles import FLAT
    reel = generate(7, depth=2, length=90).track
    race = Race(reel, base_stats(), rivals=3, rival_level=0.5, seed=7, countdown=False, boss="night")
    pv = race.chase.paver
    pv.lay_until(3 * reel.ncols * C.TILE_W, False)   # far from you: it just loops the reel
    assert pv.built >= 3 * reel.ncols
    assert all(race.track.terrain[c] == reel.terrain[c % reel.ncols] for c in range(pv.built))
    race = Race(reel, base_stats(), rivals=3, rival_level=0.5, seed=7, countdown=False, boss="night")
    pv = race.chase.paver
    start = pv.built
    pv.lay_until((start + 20) * C.TILE_W, True)    # engaged: its own pieces
    mine = pv.built + len(pv.queue)                 # (the rest of its last piece is still queued)
    pv.lay_until((mine + 40) * C.TILE_W, False)    # far again: flat until the loop's next segment, then the loop
    back = [c for c in range(mine, pv.built) if race.track.terrain[c] != FLAT]
    assert back and all(race.track.terrain[c] == reel.terrain[c % reel.ncols] for c in range(back[0], pv.built))
    assert pv._seg_start(back[0] % reel.ncols) or race.track.terrain[back[0] - 1] == FLAT


def test_chained_descents_are_one_slope():
    from track.tiles import DOWN_LO
    tr = make_track("S...uUTTTDd......", laps=1)
    hs = [tr.ground(9 * C.TILE_W + x) for x in range(16, 2 * C.TILE_W - 16)]
    steps = [round(a - b, 3) for a, b in zip(hs, hs[1:])]
    assert max(steps) - min(steps) < 0.05                       # no flat lip half way down
    single = make_track("S...utttd......", laps=1)
    assert single.profile_at(8) != tr.profile_at(10) and single.terrain[8] == DOWN_LO   # a lone one keeps its lip


def test_landing_on_a_kink_can_match_either_side():
    tr = make_track("S...utttd......", laps=1)
    b = Bike(tr, base_stats())
    x = 9 * C.TILE_W                                            # where the descent meets the flat
    b.x = x
    assert abs(b._landing_slope(x, 0.0)) < 1.0                  # flat-angled: judged against the flat
    assert b._landing_slope(x, -24.0) < -20.0                   # slope-angled: judged against the slope
