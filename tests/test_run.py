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
    s = apply_upgrades(base_stats(), ["turbo_tune", "turbo_tune", "cool_head"])
    assert abs(s.heat_b - C.HEAT_B * 0.8 ** 2) < 1e-9 and abs(s.red_heat_mult - 0.65) < 1e-9


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
    # Rivals line up level with the player (no head start), so this seed
    # needs a clean ghost run; seed 11 lost its final by 2 ticks.
    r = RunState(seed=1)
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
    from track.tiles import PADS
    for seed in range(40):
        r = RunState(seed=seed)
        for i, h in enumerate(r.heats):
            if h.target.modifier == "no_coolant":
                r.heat_i = i
                r.prepare_heat()
                assert not any(x in PADS for l in h.track.surface for x in l)
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


# --- upgrades redesigned around the throttle modes -----------------------------------------
from bike import Bike, Controls
from run.upgrades import UPGRADES as UPS
from track.tiles import make_track


def _flat(n=200):
    return make_track("S" + "." * n, laps=1)


def _bike(ids, one=True):
    b = Bike(_flat(), apply_upgrades(base_stats(), ids))
    b.one_button = one
    return b


def test_offers_respect_the_throttle_mode():
    rng = random.Random(4)
    one_only = {u.id for u in UPS.values() if u.modes == ("one",)}
    assert {"warm_up", "heat_wrap", "supercharger", "pre_heater"} <= one_only
    seen = set()
    for _ in range(300):
        ids = {u.id for u in offer(rng, [], 3, "classic")}
        assert not ids & one_only
        seen |= {u.id for u in offer(rng, [], 3, "one")}
    assert one_only <= seen


def test_every_upgrade_changes_something_and_reads_per_mode():
    base = base_stats()
    for u in UPS.values():
        assert apply_upgrades(base, [u.id]) != base, u.id
        for m in u.modes:
            assert u.title(m) and u.text(m)
    assert UPS["cryo_pads"].title("one") == "Pad Lock" and UPS["cryo_pads"].title("classic") == "Cryo Pads"


def test_old_save_ids_are_ignored():
    assert apply_upgrades(base_stats(), ["no_such_upgrade", "big_bore"]).max_speed_a > C.SPEED_MAX_A


def ticks_until(b, cond, ctl=Controls(a=True), limit=3000):
    for t in range(limit):
        if cond(b):
            return t
        b.step(ctl)
    return limit


def test_warm_up_reaches_boost_sooner():
    slow = ticks_until(_bike([]), lambda b: b.temp >= C.ONE_BOOST_AT)
    fast = ticks_until(_bike(["warm_up"]), lambda b: b.temp >= C.ONE_BOOST_AT)
    assert fast < slow * 0.8


def test_heat_wrap_keeps_speed_after_letting_go():
    def speed_after_release(ids):
        b = _bike(ids)
        ticks_until(b, lambda b: b.temp >= 20)
        for _ in range(300):                     # 5 s off: plain drains out of boost
            b.step(Controls())
        return b.speed
    assert speed_after_release(["heat_wrap"]) > speed_after_release([])


def test_cool_head_stretches_the_red_window():
    def red_ticks(ids):
        b = _bike(ids); b.temp = C.ONE_SUPER_AT
        return ticks_until(b, lambda b: b.state != "ride")
    assert red_ticks(["cool_head"]) > red_ticks([]) * 1.3


def test_radiator_vents_once_per_race_in_both_modes():
    for one in (True, False):
        b = _bike(["radiator"], one); b.temp = C.TEMP_OVERHEAT - 0.01
        ev = b.step(Controls(a=True, b=True))
        assert ("vent",) in ev and b.state == "ride" and b.temp < C.TEMP_OVERHEAT - 1
        b.temp = C.TEMP_OVERHEAT - 0.01
        b.step(Controls(a=True, b=True))
        assert b.state in ("crash", "overheat")          # the one charge is spent


def test_supercharger_is_faster_in_the_red():
    def top(ids):
        b = _bike(ids); b.temp = C.ONE_SUPER_AT + 0.5
        for _ in range(200):
            b.temp = C.ONE_SUPER_AT + 0.5
            b.step(Controls(a=True))
        return b.speed
    assert top(["supercharger"]) >= top([]) + 2


def test_pre_heater_restarts_warm_after_a_crash():
    for ids, warm in (([], False), (["pre_heater"], True)):
        b = _bike(ids); b.temp = C.TEMP_OVERHEAT - 0.01
        b.step(Controls(a=True))
        assert b.state == "crash"
        ticks_until(b, lambda b: b.state == "ride", Controls())
        assert (0 < b.temp < C.ONE_BOOST_AT) == warm


def test_heat_sink_shortens_blow_ups():
    a, b = _bike([]), _bike(["heat_sink"])
    for x in (a, b):
        x.temp = C.TEMP_OVERHEAT - 0.01
        x.step(Controls(a=True))
    assert b.crash_total < a.crash_total


def test_quick_steer_changes_lanes_faster():
    def lane_ticks(ids):
        b = _bike(ids)
        b.step(Controls(lane_down=True))
        return ticks_until(b, lambda b: b.lane_pos == b.lane, Controls())
    assert lane_ticks(["quick_steer"]) < lane_ticks([])


def _land(b, err):
    """Drop the bike onto flat ground at a given nose angle error."""
    b.speed = 40; b.airborne = True; b.air_ticks = 60; b.h = b.track.ground(b.x) + 0.5
    b.vy = -3; b.angle = err
    for _ in range(5):
        if not b.airborne:
            break
        b.step(Controls())


def test_hype_landing_and_plush_forks():
    b = _bike(["hype_landing"]); b.temp = 12.0
    _land(b, 0.0)
    assert b.temp > 12.0                             # one-button: a heat kick
    c = _bike(["hype_landing"], one=False); c.temp = 20.0
    _land(c, 0.0)
    assert c.temp < 20.0                             # classic: a cool-down
    rough = (C.LAND_TOLERANCE + C.LAND_ROUGH) / 2
    plain, plush = _bike([]), _bike(["plush_forks"])
    for x in (plain, plush):
        x.temp = 20.0
        _land(x, rough)
    assert plush.temp > plain.temp
