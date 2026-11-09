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


def test_starting_kit_applies_upgrade():
    p = Profile.load(fresh_storage())
    p.earn(1000)
    shop.buy(p, "kit", "gyro")
    shop.select(p, "kit", "gyro")
    assert p.selected["start_upgrade"] == "gyro"
    r = RunState(seed=2, start_upgrades=[p.selected["start_upgrade"]])
    assert r.stats_for_heat().pitch_rate > RunState(seed=2).stats_for_heat().pitch_rate


def test_cannot_select_unowned():
    p = Profile.load(fresh_storage())
    assert not shop.select(p, "vehicle", "sprinter")
    assert p.selected["vehicle"] == "dirt"


def test_theme_rotation_applies_to_runs():
    p = Profile.load(fresh_storage())
    p.earn(1000)
    shop.buy(p, "theme", "night")          # buying turns a theme on
    themes = shop.active_themes(p)
    assert "night" in themes
    r = RunState(seed=3, themes=themes)
    seen = set()
    for i in range(len(themes)):
        r.heat_i = i
        seen.add(r.prepare_heat().track.theme)
    assert seen == set(themes)


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
