"""Milestone 1: the feel contract (spec §3.1)."""
import config as C
from bike import Bike, Controls, base_stats
from race import Race
from track.static import static_track, material_demo_track
from track.tiles import make_track, apply_layer
from track.validator import validate


def flat(n=200):
    return make_track("S" + "." * n, laps=1)


def run(bike, ctl, ticks):
    evs = []
    for _ in range(ticks):
        evs += bike.step(ctl)
    return evs


def test_speed_starts_at_zero_and_caps_on_A():
    b = Bike(flat())
    assert b.speed == 0
    run(b, Controls(a=True), 600)
    assert b.speed == C.SPEED_MAX_A == 46


def test_A_adds_one_and_B_adds_two_per_step():
    a = Bike(flat()); bb = Bike(flat())
    run(a, Controls(a=True), C.ACCEL_INTERVAL)
    run(bb, Controls(b=True), C.ACCEL_INTERVAL)
    assert a.speed == 1 and bb.speed == 2


def test_turbo_cap_is_higher():
    b = Bike(flat())
    run(b, Controls(b=True), 200)
    assert C.SPEED_MAX_A < b.speed <= C.SPEED_MAX_B


def test_temperature_starts_8_settles_17_on_A():
    b = Bike(flat(400))
    assert b.temp == 8
    run(b, Controls(a=True), 1200)
    assert b.temp == C.TEMP_STABLE_A == 17
    assert b.state == "ride"


def test_turbo_overheats_at_32_and_stalls():
    b = Bike(flat(800))
    for t in range(600):
        if ("overheat",) in b.step(Controls(b=True)):
            break
    assert b.state == "overheat" and b.temp == C.TEMP_OVERHEAT
    assert 4 * C.FPS < t < 7 * C.FPS      # several seconds of turbo from cold
    run(b, Controls(), C.OVERHEAT_TICKS + 5)
    assert b.state == "ride" and b.temp == C.TEMP_START


def test_coolant_resets_temperature():
    t = make_track("S" + "." * 60, laps=1)
    apply_layer(t, 1, "." * 40 + "c")
    b = Bike(t, lane=1)
    hot = Controls(b=True)
    for _ in range(2000):
        ev = b.step(hot)
        if ("coolant",) in ev:
            assert b.temp == C.TEMP_START
            return
        if b.state != "ride":
            b.state = "ride"; b.temp = 20
    raise AssertionError("never reached coolant")


def test_level_landing_keeps_speed_bad_landing_crashes():
    t = make_track("S...L" + "." * 30, laps=1)
    # level-ish landing: ghost steering
    r = validate(t)
    assert r["ok"]
    # nose-down landing: hold right all the way
    b = Bike(t, lane=1)
    evs = []
    for _ in range(600):
        evs += b.step(Controls(a=True, right=b.airborne))
        if b.state == "crash":
            break
    assert any(e[0] == "crash" for e in evs)


def test_crash_costs_time_then_recovers():
    t = make_track("S...L" + "." * 30, laps=1)
    b = Bike(t, lane=1)
    for _ in range(600):
        b.step(Controls(a=True, right=b.airborne))
        if b.state == "crash":
            break
    assert b.speed == 0
    run(b, Controls(), b.stats.crash_ticks + 1)
    assert b.state == "ride"


def test_lanes_clamp_to_four():
    b = Bike(flat(), lane=0)
    for _ in range(10):
        b.step(Controls(lane_down=True))
    run(b, Controls(), 40)
    assert b.lane == 3 and b.lane_pos == 3.0
    b.step(Controls(lane_down=True))
    assert b.lane == 3


def test_mud_slows():
    t = make_track("S" + "." * 80, laps=1)
    apply_layer(t, 1, "." * 20 + "m" * 30)
    b = Bike(t, lane=1)
    while b.x < 30 * C.TILE_W:
        b.step(Controls(a=True))
    assert b.speed <= C.MUD_SPEED


def test_lap_timing_and_finish():
    r = Race(make_track("S" + "." * 20, laps=2), countdown=False)
    while not r.finished and r.time_ticks < 5000:
        r.step(Controls(a=True))
    assert r.finished and len(r.lap_times) == 2


def test_static_tracks_solvable_by_every_vehicle():
    for tr in (static_track(), material_demo_track()):
        for v in ("dirt", "trike", "scrambler", "sprinter"):
            assert validate(tr, base_stats(v))["ok"], (tr.name, v)


def test_determinism():
    a = validate(static_track()); b = validate(static_track())
    assert a == b
