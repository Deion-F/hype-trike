"""Milestone 4: run loop, upgrades, permadeath, payout (spec §6.1-6.2)."""
import random

import config as C
from bike import base_stats
from race import Race
from run.manager import RunState, RUN_HEATS, BIOMES, RACES_PER_BIOME, is_boss, biome_of
from meta.kit import apply_kit
from run.upgrades import UPGRADES, apply_upgrades, offer
from track.validator import GhostAI


def test_upgrades_stack_multiplicatively():
    s = apply_upgrades(base_stats(), ["big_bore", "big_bore"])
    assert abs(s.max_speed_a - C.SPEED_MAX_A * 1.04 ** 2) < 1e-9
    s = apply_upgrades(base_stats(), ["turbo_tune", "turbo_tune"])
    assert abs(s.heat_b - C.HEAT_B * 0.8 ** 2) < 1e-9


def test_upgrades_do_not_mutate_base():
    b = base_stats()
    apply_upgrades(b, ["paddle_tyres", "big_bore"])
    assert b == base_stats()


def test_offer_three_distinct_and_respects_caps():
    rng = random.Random(1)
    for _ in range(50):
        o = offer(rng, [], 3)
        assert len({u.id for u in o}) == 3
    capped = ["blow_off", "blow_off"]
    for _ in range(50):
        assert "blow_off" not in [u.id for u in offer(rng, capped, 3)]


def test_upgrades_visibly_change_behaviour():
    s0 = base_stats(); s1 = apply_upgrades(s0, ["big_bore", "big_bore", "big_bore"])
    from track.tiles import make_track
    from bike import Bike, Controls
    t = make_track("S" + "." * 200, laps=1)
    a, b = Bike(t, s0), Bike(t, s1)
    for _ in range(600):
        a.step(Controls(a=True)); b.step(Controls(a=True))
    assert b.speed > a.speed


def test_run_is_five_biomes_of_two_races_and_a_boss():
    r = RunState(seed=5)
    assert len(r.heats) == RUN_HEATS == 15 and RACES_PER_BIOME == 3
    assert BIOMES == ("valley", "desert", "night", "stadium", "lava")
    for h in r.heats:
        assert h.biome == BIOMES[h.index // 3]
        assert h.boss == (h.index % 3 == 2)
        if h.boss:                                  # bosses must be won ...
            assert h.target.kind == "place" and h.target.value == 1
        else:                                       # ... normal races only need a podium
            assert h.target.value >= 2


def test_bosses_are_harder_than_their_biome_races():
    r = RunState(seed=5)
    for b in range(len(BIOMES)):
        n1, n2, boss = r.heats[3 * b: 3 * b + 3]
        assert boss.depth == n1.depth + 1 == n2.depth + 1
        assert boss.rival_level > n2.rival_level >= n1.rival_level


def test_each_race_is_themed_by_its_biome():
    r = RunState(seed=3)
    for i in (0, 4, 8, 14):
        r.heat_i = i
        assert r.prepare_heat().track.theme == BIOMES[biome_of(i)]


def test_boss_win_offers_elite_upgrades():
    r = RunState(seed=7)
    for i in range(RUN_HEATS - 1):
        tiers = {u.tier for u in r.offer_after(i)}
        assert tiers == ({"elite"} if is_boss(i) else {"normal"})
    for mode in ("one", "classic"):                 # 3 picks to choose from even at the 4th boss win
        elite = [u for u in UPGRADES.values() if u.tier == "elite" and mode in u.modes]
        assert len(elite) - 3 >= 3
    # Clearing a boss moves you into the next biome
    r = RunState(seed=7)
    r.heat_i = 2
    r.prepare_heat()
    r.record({"finished": True, "time": 1, "position": 1, "perfect": 0, "distance": 10}, base_stats())
    assert r.status == "active" and all(u.tier == "elite" for u in r.pending_offer)
    r.choose(r.pending_offer[0].id)
    assert r.heat.biome == "desert" and r.biomes_cleared() == 1


def test_elite_upgrades_beat_their_regular_counterparts():
    b = base_stats()
    assert apply_upgrades(b, ["works_engine"]).max_speed_a > apply_upgrades(b, ["big_bore", "big_bore"]).max_speed_a
    pro = apply_upgrades(b, ["pro_suspension"])
    assert pro.rough_loss_mult < apply_upgrades(b, ["plush_forks"]).rough_loss_mult
    assert pro.land_saves > apply_upgrades(b, ["crumple_zone"]).land_saves


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
    for st, n in ((won, RUN_HEATS), (lost, 1)):
        for i in range(n):
            st.results.append({"heat": i, "met": True})
        st.status = "won" if n == RUN_HEATS else "lost"
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
    for lv in sorted(set(levels)):
        stats, ai, heat = rival_setup(lv, 1, 3)
        cur = (stats["max_speed_a"], ai["skill"], -ai["blunder"], -ai["miss"])
        if prev:
            assert all(c >= p for c, p in zip(cur, prev)) and cur != prev
        prev = cur
    first, ai0, heat0 = rival_setup(0.0, 1, 3)
    assert first["max_speed_a"] < C.SPEED_MAX_A and ai0["blunder"] > 0 and ai0["miss"] > 0
    assert heat0[0] < C.ONE_BOOST_AT                         # first-round rivals never boost
    assert all(rival_setup(1.0, i, 3)[2][0] - rival_setup(1.0, i, 3)[2][1] >= C.ONE_BOOST_AT
               for i in range(3))                            # final-round rivals ride the boost band
    assert all(rival_setup(lv, i, 3)[2][0] < C.ONE_SUPER_AT for lv in (0, .5, 1) for i in range(3))


def test_rivals_get_a_random_kit_within_the_difficulty_budget():
    from race import Race, RIVAL_KIT_MAX
    from track.tiles import make_track
    tr = make_track("S" + "." * 40, laps=1)
    for lv in (0.0, 0.5, 1.0):
        race = Race(tr, rivals=3, rival_level=lv, seed=9, countdown=False)
        for kit, rb in zip(race.rival_kits, race.rivals):
            assert sum(kit.values()) == round(RIVAL_KIT_MAX * lv) and "sponsor" not in kit
            assert rb.one_button and rb.temp == 0.0
        if lv == 1.0:
            assert len({tuple(sorted(k.items())) for k in race.rival_kits}) > 1     # each one differs
    a = Race(tr, rivals=3, rival_level=1.0, seed=9, countdown=False).rival_kits
    assert a == Race(tr, rivals=3, rival_level=1.0, seed=9, countdown=False).rival_kits   # replayable


def test_rival_heat_flame_tells_their_speed():
    from race import Race
    from track.tiles import make_track
    race = Race(make_track("S" + "." * 200, laps=1), rivals=3, rival_level=1.0, seed=3, countdown=False)
    for _ in range(900):
        race.step(Controls())
    for rb in race.rivals:
        assert rb.boost_level == 1 and rb.speed > rb.stats.max_speed_a   # boosting, and it shows


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


def _bike(ids, one=True, kit=None):
    b = Bike(_flat(), apply_upgrades(apply_kit(base_stats(), kit), ids))
    b.one_button = one
    return b


def test_offers_respect_the_throttle_mode():
    rng = random.Random(4)
    one_only = {u.id for u in UPS.values() if u.modes == ("one",) and u.tier == "normal"}
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


def test_kit_cool_head_stretches_the_red_window():
    def red_ticks(kit):
        b = _bike([], kit=kit); b.temp = C.ONE_SUPER_AT
        return ticks_until(b, lambda b: b.state != "ride")
    assert red_ticks({"cool_head": 5}) > red_ticks({"cool_head": 2}) > red_ticks({})
    assert red_ticks({"cool_head": 5}) > red_ticks({}) * 1.3


def test_blow_off_valve_vents_once_per_race_in_both_modes():
    for one in (True, False):
        b = _bike(["blow_off"], one); b.temp = C.TEMP_OVERHEAT - 0.01
        ev = b.step(Controls(a=True, b=True))
        assert ("vent",) in ev and b.state == "ride" and b.temp < C.TEMP_OVERHEAT - 1
        b.temp = C.TEMP_OVERHEAT - 0.01
        b.step(Controls(a=True, b=True))
        assert b.state in ("crash", "overheat")          # the one charge is spent


def test_supercharger_is_faster_in_the_red():
    def top(ids):
        b = _bike(ids); b.temp = C.TEMP_OVERHEAT - 1.0       # deep in the overheating zone
        for _ in range(200):
            b.temp = C.TEMP_OVERHEAT - 1.0
            b.step(Controls(a=True))
        return b.speed
    assert top(["supercharger"]) >= top([]) + 2


def test_overheating_scales_with_depth_and_turns_faster():
    def top(temp):
        b = _bike([]); b.temp = temp
        for _ in range(300):
            b.temp = temp
            b.step(Controls(a=True))
        return b.speed
    edge, mid, deep = (C.ONE_SUPER_AT + 0.2, (C.ONE_SUPER_AT + C.TEMP_OVERHEAT) / 2, C.TEMP_OVERHEAT - 0.3)
    boost = top(C.ONE_SUPER_AT - 1)
    assert boost < top(edge) < top(mid) < top(deep)          # deeper = faster
    b = _bike([]); b.temp = deep
    k = b.overheat_depth()
    assert k > 0.9 and b._accel_interval() < b.stats.accel_interval
    b.temp = C.ONE_SUPER_AT - 1
    assert b.overheat_depth() is None and b._accel_interval() == b.stats.accel_interval
    for temp, faster in ((C.ONE_SUPER_AT - 1, False), (edge, True), (deep, True)):
        b = _bike([]); b.temp = temp
        b.airborne, b.h, b.vy, b.angle = True, b.track.ground(b.x) + 100, 3.0, 0.0
        b.step(Controls(left=True))
        assert (b.angle > b.stats.pitch_rate * 1.1) == faster, temp


def test_pre_heater_restarts_warm_after_a_crash():
    for ids, warm in (([], False), (["pre_heater"], True)):
        b = _bike(ids); b.temp = C.TEMP_OVERHEAT - 0.01
        b.step(Controls(a=True))
        assert b.state == "crash"
        ticks_until(b, lambda b: b.state == "ride", Controls())
        assert (0 < b.temp < C.ONE_BOOST_AT) == warm


def test_kit_radiator_shortens_blow_ups():
    a, b = _bike([]), _bike([], kit={"radiator": 3})
    for x in (a, b):
        x.temp = C.TEMP_OVERHEAT - 0.01
        x.step(Controls(a=True))
    assert b.crash_total < a.crash_total


def test_kit_quick_steer_changes_lanes_faster():
    def lane_ticks(kit):
        b = _bike([], kit=kit)
        b.step(Controls(lane_down=True))
        return ticks_until(b, lambda b: b.lane_pos == b.lane, Controls())
    assert lane_ticks({"quick_steer": 5}) < lane_ticks({})


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


# --- run upgrades redesigned so none repeats a Starter Kit item -------------------------
def test_no_run_upgrade_repeats_a_kit_item():
    from meta.kit import KIT
    kit_names = {it.name for it in KIT.values()}
    for u in UPGRADES.values():
        assert u.id not in KIT and u.title("one") not in kit_names and u.title("classic") not in kit_names, u.id
    # ... and no run upgrade touches a stat a kit item levels up
    base = base_stats()
    kit_fields = set()
    for it in KIT:
        a, b = vars(base), vars(apply_kit(base, {it: 5}))
        kit_fields |= {k for k in a if a[k] != b[k]}
    for u in UPGRADES.values():
        a, b = vars(base), vars(apply_upgrades(base, [u.id]))
        assert not {k for k in a if a[k] != b[k]} & kit_fields, u.id


def test_kit_levels_climb_to_the_old_full_value_and_cost_more_each_level():
    from meta.kit import KIT, MAX_LEVEL
    b = base_stats()
    assert apply_kit(b, {"gyro": 0}).pitch_rate == b.pitch_rate
    assert abs(apply_kit(b, {"gyro": MAX_LEVEL}).pitch_rate - b.pitch_rate * 1.2) < 1e-9
    assert apply_kit(b, {"gyro": 1}).pitch_rate < apply_kit(b, {"gyro": 2}).pitch_rate
    assert abs(apply_kit(b, {"soft_shocks": MAX_LEVEL}).land_tolerance - b.land_tolerance * 1.2) < 1e-9
    for it in KIT.values():
        prices = [it.price(l) for l in range(MAX_LEVEL)]
        assert prices == sorted(prices) and len(set(prices)) == MAX_LEVEL and it.price(MAX_LEVEL) is None


def test_hang_time_turns_airtime_into_speed():
    plain, hang = _bike([]), _bike(["hang_time"])
    for b in (plain, hang):
        _land(b, 0.0)
    assert hang.speed > plain.speed


def test_crumple_zone_saves_one_crash_landing_per_race():
    b = _bike(["crumple_zone"])
    _land(b, -(C.LAND_ROUGH_NOSE + 15))
    assert b.state == "ride" and b.stats_counters["rough"] == 1
    _land(b, -(C.LAND_ROUGH_NOSE + 15))
    assert b.state == "crash"


def test_adrenaline_slows_the_red_after_a_perfect_landing():
    def red_ticks(ids):
        b = _bike(ids)
        _land(b, 0.0)
        b.temp = C.ONE_SUPER_AT
        return ticks_until(b, lambda b: b.state != "ride")
    assert red_ticks(["adrenaline"]) > red_ticks([])


def test_comeback_accelerates_faster_after_a_crash():
    def speed_after(ids):
        b = _bike(ids); b.temp = C.TEMP_OVERHEAT - 0.01
        b.step(Controls(a=True))
        ticks_until(b, lambda b: b.state == "ride", Controls())
        for _ in range(60):
            b.step(Controls(a=True))
        return b.speed
    assert speed_after(["comeback"]) > speed_after([])          # one-button: warms up faster
    def classic_speed_after(ids):
        b = _bike(ids, one=False); b.speed = 30
        b._crash([], "nose")
        ticks_until(b, lambda b: b.state == "ride", Controls())
        for _ in range(60):
            b.step(Controls(a=True))
        return b.speed
    assert classic_speed_after(["comeback"]) > classic_speed_after([])


def test_slipstream_needs_a_rival_just_ahead():
    a, b = _bike(["slipstream"]), _bike(["slipstream"])
    b.drafting = True
    for x in (a, b):
        x.temp = 20.0
        for _ in range(400):
            x.temp = 20.0
            x.step(Controls(a=True))
    assert b.speed > a.speed


def test_line_choice_kicks_speed_on_a_finished_lane_change():
    b = _bike(["line_choice"]); b.speed = 30.0; b.temp = 20.0
    b.step(Controls(a=True, lane_down=True))
    before = b.speed
    ticks_until(b, lambda b: b.lane_pos == b.lane)
    assert b.speed >= before + 1


def test_barrier_buster_smashes_one_barrier():
    from track.tiles import DEBRIS
    tr = make_track("S" + "." * 30, laps=1)
    tr.surface[1][4] = tr.surface[1][8] = DEBRIS
    b = Bike(tr, apply_upgrades(base_stats(), ["barrier_buster"]))
    b.speed = 35
    evs = []
    while b.x < 10 * C.TILE_W and b.state == "ride":
        b.speed = 35
        evs += b.step(Controls(a=True))
    assert ("smash",) in evs and ("crash", "debris") in evs


def test_prize_money_and_bounty_pay_for_wins():
    def total(ids):
        r = RunState(seed=2, start_upgrades=ids)
        r.results = [{"heat": 0, "met": True, "position": 1}, {"heat": 1, "met": True, "position": 3},
                     {"heat": 2, "met": True, "position": 1}]
        return r.payout()[1]["heats"]
    assert total(["prize_money"]) == total([]) + 2 * 15
    assert total(["bounty_hunter"]) == total([]) + 60
