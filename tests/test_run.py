"""Milestone 4: run loop, upgrades, permadeath, payout (spec §6.1-6.2)."""
import random

import config as C
from bike import base_stats
from race import Race
from run.manager import RunState, RUN_HEATS
from run.upgrades import UPGRADES, apply_upgrades, offer
from track.validator import GhostAI


def test_upgrades_stack_multiplicatively():
    s = apply_upgrades(base_stats(), ["big_bore", "big_bore"])
    assert abs(s.max_speed_a - C.SPEED_MAX_A * 1.04 ** 2) < 1e-9
    s = apply_upgrades(base_stats(), ["cool_head", "turbo_tune"])
    assert abs(s.heat_b - C.HEAT_B * 0.85 * 0.8) < 1e-9


def test_upgrades_do_not_mutate_base():
    b = base_stats()
    apply_upgrades(b, ["all_terrain", "big_bore"])
    assert b == base_stats()


def test_offer_three_distinct_and_respects_caps():
    rng = random.Random(1)
    for _ in range(50):
        o = offer(rng, [], 3)
        assert len({u.id for u in o}) == 3
    capped = ["heat_sink", "heat_sink"]
    for _ in range(50):
        assert "heat_sink" not in [u.id for u in offer(rng, capped, 3)]


def test_upgrades_visibly_change_behaviour():
    s0 = base_stats(); s1 = apply_upgrades(s0, ["big_bore", "big_bore", "big_bore"])
    from track.tiles import make_track
    from bike import Bike, Controls
    t = make_track("S" + "." * 200, laps=1)
    a, b = Bike(t, s0), Bike(t, s1)
    for _ in range(600):
        a.step(Controls(a=True)); b.step(Controls(a=True))
    assert b.speed > a.speed


def test_run_has_six_heats_and_final_is_a_win_target():
    r = RunState(seed=5)
    assert len(r.heats) == RUN_HEATS == 6
    assert r.heats[-1].target.kind == "place" and r.heats[-1].target.value == 1


def test_failing_a_heat_ends_the_run():
    r = RunState(seed=3)
    r.prepare_heat()
    r.record({"finished": False, "time": 0, "position": 4, "perfect": 0, "distance": 100}, base_stats())
    assert r.status == "lost" and r.pending_offer is None


def test_full_run_can_be_won_and_pays_out():
    r = RunState(seed=11)
    ai = GhostAI(turbo=True, turbo_temp=24)
    while r.status == "active":
        h = r.prepare_heat()
        st = r.stats_for_heat(h)
        race = Race(h.track, st, rivals=h.rivals, rival_level=h.rival_level, seed=h.seed, countdown=False)
        while not race.finished and race.time_ticks < 60 * 300:
            race.step(ai.controls(race.bike))
        res = {"finished": race.finished, "time": race.time_ticks, "position": race.position(),
               "perfect": race.bike.stats_counters["perfect"], "distance": race.bike.x, "forgiven": 0}
        r.record(res, st)
        if r.status == "active":
            assert len(r.pending_offer) == 3
            r.choose(r.pending_offer[0].id)
    assert r.status == "won"
    total, parts, mult = r.payout()
    assert total > 0 and parts["victory"] > 0


def test_lost_run_pays_less_than_won():
    won = RunState(seed=2); lost = RunState(seed=2)
    for st, n in ((won, 6), (lost, 1)):
        for i in range(n):
            st.results.append({"heat": i, "met": True})
        st.status = "won" if n == 6 else "lost"
    assert won.payout()[0] > lost.payout()[0]


def test_modifiers_apply():
    r = RunState(seed=1)
    for h in r.heats:
        if h.target.modifier == "double_heat":
            s = r.stats_for_heat(h)
            assert abs(s.heat_b - 2 * C.HEAT_B) < 1e-9
    # no_coolant heats generate with no pads
    from track.tiles import COOLANT
    for seed in range(40):
        r = RunState(seed=seed)
        for i, h in enumerate(r.heats):
            if h.target.modifier == "no_coolant":
                r.heat_i = i
                r.prepare_heat()
                assert not any(x == COOLANT for l in h.track.surface for x in l)
                return


def test_second_wind_is_once_per_run():
    r = RunState(seed=4, start_upgrades=["second_wind"])
    assert r.stats_for_heat().crash_forgives == 1
    r.forgives_used = 1
    assert r.stats_for_heat().crash_forgives == 0


def test_rivals_get_faster_and_cleaner_each_round():
    from race import rival_setup
    r = RunState(seed=3)
    levels = [h.rival_level for h in r.heats]
    assert levels == sorted(levels) and levels[0] == 0 and levels[-1] == 1
    prev = None
    for lv in levels:
        stats, ai = rival_setup(lv, 1, 3)
        cur = (stats["max_speed_a"], ai["skill"], -ai["blunder"], -ai["miss"])
        if prev:
            assert all(c >= p for c, p in zip(cur, prev)) and cur != prev
        prev = cur
    first, ai0 = rival_setup(0.0, 1, 3)
    assert first["max_speed_a"] < C.SPEED_MAX_A and ai0["blunder"] > 0 and ai0["miss"] > 0


def test_first_map_has_no_whoops():
    from track.generator import generate
    from track.tiles import WHOOPS
    for seed in range(12):
        assert WHOOPS not in generate(seed, depth=0).track.terrain


def test_every_heat_is_a_race_with_rivals():
    for seed in range(6):
        for h in RunState(seed=seed).heats:
            assert h.rivals == 3 and h.target.kind == "place"


def test_time_trial_mode_is_solo_against_par():
    import main as M
    from ui.menus import TitleScene
    app = M.App()
    sc = TitleScene(app); app.set_scene(sc)
    assert any(it["label"] == "TIME TRIAL" for it in sc.menu.items)
    sc.time_trial()
    rs = app.scene
    assert not rs.race.rivals and rs.target.kind == "time" and rs.target.value > 0
