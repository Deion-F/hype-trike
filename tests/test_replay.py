"""Race recordings: exact replays and the tuning summary."""
import json
import os

import config as C
import replay as rp
from bike import base_stats
from race import Race
from track.generator import generate
from track.validator import GhostAI


def record_race(one_button, seed=7, depth=2, theme="valley"):
    track = generate(seed, depth).track
    track.theme = theme
    race = Race(track, base_stats(), rivals=3, rival_level=0.6, seed=seed)
    race.bike.one_button = one_button
    rec = rp.Recorder(race, "flame", {"kind": "test", "heat": 2}, {"throttle_mode": "one"})
    ai = GhostAI(turbo=True, turbo_temp=24, seed=3)
    while not race.finished and race.time_ticks < 60 * 200:
        ctl = ai.controls(race.bike)
        rec.tick(ctl, race.step(ctl))
    return race, rec.finish({"finished": race.finished})


def test_replay_reproduces_the_race_exactly_in_both_modes():
    for one in (True, False):
        race, data = record_race(one)
        data = json.loads(json.dumps(data))          # through JSON, as on disk
        again = rp.resimulate(data)
        assert again.time_ticks == race.time_ticks
        assert abs(again.bike.x - race.bike.x) < 1e-6
        assert again.rival_finish == race.rival_finish
        assert [rb.x for rb in again.rivals] == [rb.x for rb in race.rivals]


def test_summary_has_the_tuning_numbers():
    race, data = record_race(True, theme="lava")
    s = data["summary"]
    assert s["finished"] and s["field"] == 4 and 1 <= s["position"] <= 4
    assert s["landings"] >= s["perfect"] >= 0 and abs(sum(s["boost_share"]) - 1) < 0.01
    assert len(s["rivals"]) == 3 and data["track"]["t"] == "lava"
    assert data["track"]["segments"] and len(data["track"]["segments"]) == len(data["track"]["g"])
    kinds = {e[2] for e in data["events"]}
    assert "go" in kinds and "finish" in kinds
    assert any(e[1] > 0 for e in data["events"])      # rival events are logged too


def test_rle_roundtrip_and_control_bits():
    vals = [0, 0, 1, 1, 1, 5, 0, 63, 63]
    assert rp.unrle(rp.rle(vals)) == vals
    for v in (0, 1, 2, 12, 48, 63):
        assert rp.ctl_bits(rp.bits_ctl(v)) == v


def test_save_and_list_newest_first(tmp_path):
    _, a = record_race(True, seed=1, depth=0)
    _, b = record_race(False, seed=2, depth=0)
    b["id"] = "z" + b["id"]                          # sorts after a: newer
    pa, pb = rp.save(a, str(tmp_path)), rp.save(b, str(tmp_path))
    assert os.path.exists(pa) and os.path.exists(pb)
    items = rp.list_recordings(str(tmp_path))
    assert [d["id"] for _, d in items] == [b["id"], a["id"]]


def test_race_scene_records_by_default_and_can_turn_off(tmp_path, monkeypatch):
    import pygame
    monkeypatch.setenv("HYPE_RECORDINGS_DIR", str(tmp_path))
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((640, 360))
    import main as M
    from ui.scene import RaceScene
    from track.tiles import make_track
    app = M.App()
    assert app.profile.settings["record_races"] is True
    sc = RaceScene(app, make_track("S" + "." * 12, laps=1), base_stats(), context={"kind": "practice"})
    sc.race.countdown = 0
    for _ in range(5):
        sc.update()
    sc.forfeit = True
    sc._finish()
    files = os.listdir(tmp_path)
    assert len(files) == 1
    with open(tmp_path / files[0]) as f:
        d = json.load(f)
    assert d["context"]["kind"] == "practice" and d["summary"]["forfeit"]
    app.profile.settings["record_races"] = False
    sc2 = RaceScene(app, make_track("S" + "." * 12, laps=1), base_stats())
    assert sc2.recorder is None
