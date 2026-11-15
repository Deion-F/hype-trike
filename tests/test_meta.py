import json
"""Milestone 5: meta-progression (spec §6.3). Acceptance: currency survives an
app restart; at least one unlock changes the starting experience."""
import os
import tempfile

from meta import shop
from meta.profile import Profile, Storage
from run.manager import RunState


def fresh_storage():
    os.environ["HYPE_DATA_DIR"] = tempfile.mkdtemp(prefix="hype-meta-")
    return Storage()


def test_currency_survives_restart():
    st = fresh_storage()
    p = Profile.load(st)
    p.earn(123)
    p.save()
    p2 = Profile.load(Storage())          # "restart": new storage object, same dir
    assert p2.currency == 123 and p2.lifetime_currency == 123


def test_corrupt_save_falls_back_to_defaults():
    st = fresh_storage()
    st.write("{not json")
    p = Profile.load(Storage())
    assert p.currency == 0 and p.vehicles == ["dirt"]


def test_memory_fallback_when_storage_unavailable():
    st = fresh_storage()
    st.kind = "memory"
    p = Profile.load(st)
    p.earn(5)
    assert p.save() is False                # not persisted, but no crash
    assert Profile.load(st).currency == 5   # still readable this session


def test_coins_buy_cosmetics_only():
    p = Profile.load(fresh_storage())
    assert not shop.buy(p, "livery", "ocean")
    p.earn(1000)
    assert shop.buy(p, "livery", "ocean")
    assert p.currency == 1000 - shop.PRICES["livery"]["ocean"]
    assert not shop.buy(p, "livery", "ocean")          # can't buy twice
    assert Profile.load(Storage()).owns("liveries", "ocean")
    assert not shop.buy(p, "vehicle", "trike")         # bikes aren't for sale
    assert not shop.buy(p, "kit", "gyro")
    assert not shop.buy_upgrade(p, "dirt", "top_speed")   # upgrades take XP, not coins
    assert p.currency == 1000 - shop.PRICES["livery"]["ocean"]


def test_vehicles_unlock_by_clearing_biomes():
    p = Profile.load(fresh_storage())
    assert shop.check_vehicle_unlocks(p) == []
    p.data["best_biome"] = 2
    assert shop.check_vehicle_unlocks(p) == ["trike", "scrambler"]
    assert shop.check_vehicle_unlocks(p) == []
    assert shop.select(p, "vehicle", "trike")
    r = RunState(seed=1, vehicle=p.selected["vehicle"])
    s = r.stats_for_heat()
    assert s.vehicle == "trike" and s.land_tolerance > RunState(seed=1).stats_for_heat().land_tolerance


def test_bike_xp_buys_that_bikes_upgrades_only():
    from meta.bike_tune import MAX_LEVEL
    p = Profile.load(fresh_storage())
    assert not shop.buy_upgrade(p, "dirt", "air")         # no XP yet
    p.earn_xp("dirt", 5000)
    spent = []
    for _ in range(MAX_LEVEL):
        before = p.bike_xp("dirt")
        assert shop.buy_upgrade(p, "dirt", "air")
        spent.append(before - p.bike_xp("dirt"))
    assert spent == sorted(spent) and p.bike_levels("dirt")["air"] == MAX_LEVEL
    assert not shop.buy_upgrade(p, "dirt", "air")         # maxed
    assert p.data["bike_xp_total"]["dirt"] == 5000 and p.currency == 0
    p.data["vehicles"].append("trike")
    assert not shop.buy_upgrade(p, "trike", "air")        # the trike has its own (empty) XP
    r = RunState(seed=2, bike_levels=p.bike_levels("dirt"))
    assert r.stats_for_heat().pitch_rate > RunState(seed=2).stats_for_heat().pitch_rate


def test_deeper_races_earn_more_xp_and_runs_bank_it():
    from meta.bike_tune import xp_for_race
    xs = [xp_for_race(d) for d in range(6)]
    assert xs == sorted(xs) and xs[0] > 0 and len(set(xs)) == 6
    assert xp_for_race(2, boss=True) > xp_for_race(2)
    assert 0 < xp_for_race(2, met=False) < xp_for_race(2)
    r = RunState(seed=3)
    r.record({"finished": True, "position": 1, "time": 100}, r.stats_for_heat())
    assert r.xp == xp_for_race(0)


def test_old_saves_keep_their_tuning_and_kit_as_bike_upgrades():
    p = Profile({"currency": 0, "vehicles": ["dirt", "trike"], "kit_levels": {"gyro": 5, "sponsor": 2},
                 "bike_levels": {"dirt": {"air": 5, "top_speed": 5}}}, fresh_storage())
    assert "kit_levels" not in p.data and p.data["progression_v"] == 2
    dirt, trike = p.bike_levels("dirt"), p.bike_levels("trike")
    assert dirt["air"] == 5 and dirt["top_speed"] >= 3          # full tune + gyro -> top air
    assert trike.get("air") == 2 and "top_speed" not in trike    # the kit applied to every owned bike
    assert p.currency > 0                                         # Sponsor Deal refunded
    assert Profile(p.data, fresh_storage()).bike_levels("dirt") == dirt


def test_old_starting_upgrades_are_refunded_once():
    p = Profile({"currency": 0, "start_upgrades": ["gyro", "sponsor"],
                 "selected": {"start_upgrade": "gyro"}}, fresh_storage())
    assert p.currency == 140 + 200 and "start_upgrade" not in p.selected
    assert Profile(p.data, fresh_storage()).currency == p.currency


def test_cannot_select_unowned():
    p = Profile.load(fresh_storage())
    assert not shop.select(p, "vehicle", "sprinter")
    assert p.selected["vehicle"] == "dirt"


def test_biomes_are_not_sold_and_old_theme_purchases_are_refunded():
    assert "theme" not in shop.PRICES
    p = Profile({"currency": 10, "themes": ["valley", "night", "lava"], "theme_rotation": ["night"]},
                fresh_storage())
    assert p.currency == 10 + 150 + 250
    assert "themes" not in p.data and "theme_rotation" not in p.data
    again = Profile(p.data, fresh_storage())          # refunded only once
    assert again.currency == p.currency


def test_unlocks_are_sidegrades_not_strict_upgrades():
    from bike import base_stats
    from track.tiles import DIRT
    base = base_stats("dirt")
    for v in ("trike", "scrambler", "sprinter"):
        s = base_stats(v)
        worse = (s.max_speed_a < base.max_speed_a or s.heat_b > base.heat_b
                 or s.land_tolerance < base.land_tolerance or s.grip[DIRT] < base.grip[DIRT]
                 or s.pitch_rate < base.pitch_rate)
        assert worse, f"{v} should trade something away"


def test_old_saves_move_to_one_button_throttle_once():
    from meta.profile import Profile
    p = Profile({"settings": {"throttle_mode": "classic"}})
    assert p.settings["throttle_mode"] == "one" and p.settings["settings_v"] == 3
    again = Profile(json.loads(json.dumps(p.data)) | {"settings": {**p.settings, "throttle_mode": "classic"}})
    assert again.settings["throttle_mode"] == "classic"    # a later choice sticks
    assert Profile().settings["throttle_mode"] == "one"


def test_bike_upgrades_start_lower_and_level_past_stock_per_vehicle():
    from bike import base_stats
    from meta.bike_tune import UPGRADES, apply_tune, price, stat_bars, MAX_LEVEL
    full = base_stats("dirt")
    zero = apply_tune(full, {})
    assert zero.max_speed_a < full.max_speed_a and zero.accel_interval > full.accel_interval
    assert zero.max_speed_a >= full.max_speed_a * 0.9                 # still a reasonable bike
    maxed = apply_tune(full, {t: MAX_LEVEL for t in UPGRADES})
    assert maxed.max_speed_a > full.max_speed_a and maxed.accel_interval < full.accel_interval
    assert apply_tune(full, None) == full                                # rivals / sims: catalogue
    for t in UPGRADES:
        prices = [price("dirt", t, l) for l in range(MAX_LEVEL)]
        assert prices == sorted(prices) and price("dirt", t, MAX_LEVEL) is None
        assert price("sprinter", t, 0) > price("dirt", t, 0)
    # each upgrade raises exactly its own stat bar, on every vehicle
    for v in ("dirt", "trike", "scrambler", "sprinter"):
        for t in UPGRADES:
            lo = dict((u, f) for u, _, f in stat_bars(apply_tune(base_stats(v), {t: 1})))
            hi = dict((u, f) for u, _, f in stat_bars(apply_tune(base_stats(v), {t: 2})))
            assert hi[t] > lo[t], (v, t)
            assert all(abs(hi[u] - lo[u]) < 1e-9 for u in hi if u != t), (v, t)
