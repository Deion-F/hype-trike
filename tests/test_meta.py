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


def test_buy_requires_coins_and_unlocks():
    p = Profile.load(fresh_storage())
    assert not shop.buy(p, "vehicle", "trike")
    p.earn(1000)
    assert shop.buy(p, "vehicle", "trike")
    assert p.currency == 1000 - shop.PRICES["vehicle"]["trike"]
    assert not shop.buy(p, "vehicle", "trike")         # can't buy twice
    assert Profile.load(Storage()).owns("vehicles", "trike")


def test_vehicle_unlock_changes_starting_experience():
    p = Profile.load(fresh_storage())
    p.earn(1000)
    shop.buy(p, "vehicle", "trike")
    shop.select(p, "vehicle", "trike")
    r = RunState(seed=1, vehicle=p.selected["vehicle"])
    s = r.stats_for_heat()
    assert s.vehicle == "trike" and s.land_tolerance > RunState(seed=1).stats_for_heat().land_tolerance


def test_starter_kit_levels_apply_to_runs_and_cost_more_each_time():
    from meta.kit import KIT, MAX_LEVEL
    p = Profile.load(fresh_storage())
    p.earn(5000)
    spent = []
    for _ in range(MAX_LEVEL):
        before = p.currency
        assert shop.buy(p, "kit", "gyro")
        spent.append(before - p.currency)
    assert spent == sorted(spent) and shop.kit_level(p, "gyro") == MAX_LEVEL
    assert not shop.buy(p, "kit", "gyro")                 # maxed
    r = RunState(seed=2, kit_levels=p.data["kit_levels"])
    assert abs(r.stats_for_heat().pitch_rate - RunState(seed=2).stats_for_heat().pitch_rate * 1.2) < 1e-9
    poor = Profile.load(fresh_storage())
    assert not shop.buy(poor, "kit", "gyro") and shop.kit_level(poor, "gyro") == 0


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


def test_bike_tuning_starts_lower_and_levels_up_to_full_per_vehicle():
    from bike import base_stats
    from meta.bike_tune import TUNE, apply_tune, price
    from meta.kit import MAX_LEVEL
    full = base_stats("dirt")
    zero = apply_tune(full, {})
    assert zero.max_speed_a < full.max_speed_a and zero.accel_interval > full.accel_interval
    assert zero.max_speed_a >= full.max_speed_a * 0.9                 # still a reasonable bike
    maxed = apply_tune(full, {t: MAX_LEVEL for t in TUNE})
    for f in ("max_speed_a", "max_speed_b", "accel_interval", "heat_a", "heat_b", "pitch_rate", "land_tolerance"):
        assert abs(getattr(maxed, f) - getattr(full, f)) < 1e-9, f
    assert apply_tune(full, None) == full                                # rivals / sims: full stats
    for t in TUNE:
        prices = [price("dirt", t, l) for l in range(MAX_LEVEL)]
        assert prices == sorted(prices) and price("dirt", t, MAX_LEVEL) is None
        assert price("sprinter", t, 0) > price("dirt", t, 0)
    p = Profile.load(fresh_storage())
    p.earn(5000)
    assert shop.buy_tune_level(p, "dirt", "top_speed")
    assert not shop.buy_tune_level(p, "sprinter", "top_speed")          # not owned
    assert p.bike_levels("dirt") == {"top_speed": 1} and p.bike_levels("trike") == {}
    r = RunState(seed=1, bike_levels=p.bike_levels("dirt"))
    assert zero.max_speed_a < r.stats_for_heat().max_speed_a < full.max_speed_a
